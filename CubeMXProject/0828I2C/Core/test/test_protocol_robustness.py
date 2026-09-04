"""test_protocol_robustness.py -- 驗證三個協定/重連相關的修改，全部用
模擬的 transport／函式，不需要真的接 STM32：

    1. SEQ 對不上的過期回應會被 _recv_matching() 丟棄，不會被誤當成
       這次請求的答案
    2. 連續收到的 SEQ 都對不上時，最終會放棄並拋出 StaleResponseError
    3. build_frame() 對超過 FRAME_PAYLOAD_MAX 的 payload 會直接擋下來，
       而不是靜默送出、讓韌體端默默丟棄整個封包
    4. LoopRunner 在「重連成功、但底層裝置持續失敗」時，最終會停在
       MAX_RECONNECTS，不會無限重連下去；只要中間有成功過一次，
       reconnect_count 就會歸零重算
    5. LoopRunner 在「reconnect_fn() 本身持續丟例外」（例如 USB physically
       還沒插回去）時，一樣會重試到 MAX_RECONNECTS 次才放棄，不會像
       2026-09-04 修正前那樣丟一次例外就整個死掉——這是實際拔 USB 測試
       才踩到的 bug，第一版的測試沒有涵蓋到這個情境

用法：
    python test_protocol_robustness.py
"""

import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rtc3231.protocol import (
    build_frame, CMD_DATA_TIME, ID_PC, FRAME_PAYLOAD_MAX,
)
from rtc3231.ds3231 import DS3231
from rtc3231.exceptions import StaleResponseError, RtcTimeoutError, FrameError

import runner as runner_module


class FakeTransport:
    """模擬 SerialTransport，只實作測試需要的最小介面。
    recv() 依序吐出預先組好的 frame bytes，不需要真的開序列埠。
    """
    def __init__(self, responses):
        self._seq = 0
        self._responses = list(responses)
        self.sent = []

    def next_seq(self):
        s = self._seq
        self._seq = (self._seq + 1) & 0xFFFF
        return s

    def send(self, frame):
        self.sent.append(frame)

    def recv(self):
        return self._responses.pop(0)


def _time_payload():
    # 隨便一個合法的 7-byte GET_TIME payload，測試不在乎實際數值
    return bytes([0x07, 0xEA, 8, 30, 12, 0, 0])  # 2026-08-30 12:00:00


def _fake_ds3231(transport):
    """繞過 __init__（會真的去 auto_detect / 開序列埠），手動組一個
    可以拿來測試的 DS3231 實例。"""
    rtc = object.__new__(DS3231)
    rtc._transport = transport
    rtc._device_id = 0x02
    rtc._port = "FAKE"
    return rtc


def test_seq_matching_discards_stale():
    print("[1] SEQ 過期回應應該被丟棄，採信真正對得上的那個...")
    stale = build_frame(0x02, ID_PC, CMD_DATA_TIME, 5, _time_payload(), 0)   # 上一次(seq=5)遲來的回應
    fresh = build_frame(0x02, ID_PC, CMD_DATA_TIME, 6, _time_payload(), 0)   # 這次(seq=6)真正的回應
    rtc = _fake_ds3231(FakeTransport([stale, fresh]))

    cmd, seq, payload, flags = rtc._recv_matching(6, "GET_TIME")
    assert seq == 6, f"應該拿到 seq=6 的回應，實際拿到 seq={seq}"
    assert cmd == CMD_DATA_TIME
    print("    PASS -- stale response(seq=5)被正確丟棄，拿到 seq=6 的真正回應\n")


def test_seq_matching_gives_up_after_max_stale():
    print("[2] 連續收到的 SEQ 都對不上時，應該放棄並拋出 StaleResponseError...")
    frames = [
        build_frame(0x02, ID_PC, CMD_DATA_TIME, s, _time_payload(), 0)
        for s in (100, 101, 102, 103)   # 全部都不是我們要的 6，數量 = _MAX_STALE_RESPONSES+1
    ]
    rtc = _fake_ds3231(FakeTransport(frames))

    try:
        rtc._recv_matching(6, "GET_TIME")
        raise AssertionError("應該要拋出 StaleResponseError，但沒有")
    except StaleResponseError as e:
        print(f"    PASS -- 正確放棄並拋出 StaleResponseError -> {e}\n")


def test_payload_size_guard():
    print("[3] build_frame() 應該擋下超過 FRAME_PAYLOAD_MAX 的 payload...")
    ok_payload = bytes(FRAME_PAYLOAD_MAX)          # 剛好 32 bytes，應該成功
    build_frame(ID_PC, 0x02, CMD_DATA_TIME, 0, ok_payload, 0)
    print(f"    PASS -- {FRAME_PAYLOAD_MAX} bytes payload 正常建包")

    too_big = bytes(FRAME_PAYLOAD_MAX + 1)          # 33 bytes，應該報錯
    try:
        build_frame(ID_PC, 0x02, CMD_DATA_TIME, 0, too_big, 0)
        raise AssertionError(f"{FRAME_PAYLOAD_MAX + 1} bytes payload 應該要被擋下來，但沒有")
    except ValueError as e:
        print(f"    PASS -- {FRAME_PAYLOAD_MAX + 1} bytes payload 正確被擋下 -> {e}\n")


def test_loop_runner_reconnect_cap_gives_up():
    print("[4a] 裝置持續壞掉（重連後還是失敗）時，應該剛好重連 MAX_RECONNECTS 次就放棄...")
    runner_module.time.sleep = lambda _: None   # 測試不用真的等 0.5 秒 * 一堆次

    reconnect_calls = {"count": 0}

    def always_fail(rtc):
        raise RtcTimeoutError("模擬持續逾時")

    def fake_reconnect():
        reconnect_calls["count"] += 1
        # 模擬「重連本身沒有拋例外」，但底層裝置其實還是壞的，
        # 所以下一次 func() 呼叫還是會繼續失敗

    lr = runner_module.LoopRunner()
    lr._stop_event = threading.Event()   # 不 set，讓迴圈靠 MAX_RECONNECTS 自然結束
    lr._loop(always_fail, lambda v: "", lambda db, rtc, v: None, None, None,
              reconnect_fn=fake_reconnect)

    expected = runner_module.LoopRunner.MAX_RECONNECTS
    actual = reconnect_calls["count"]
    assert actual == expected, f"預期剛好重連 {expected} 次就放棄，實際重連了 {actual} 次"
    print(f"    PASS -- 連續失敗且重連後仍持續失敗時，剛好重連 {actual} 次後放棄，不會無限重連\n")


def test_loop_runner_reconnect_cap_resets_on_success():
    print("[4b] 重連後如果有成功過，reconnect_count 應該歸零重算，不會提早被舊次數卡住...")
    runner_module.time.sleep = lambda _: None

    threshold = runner_module.LoopRunner.MAX_RECONNECTS
    target = threshold + 2   # 只要證明「能穿過 MAX_RECONNECTS 這個次數」就夠了，不用測到天長地久

    reconnect_calls = {"count": 0}
    state = {"just_reconnected": False}
    lr = runner_module.LoopRunner()
    lr._stop_event = threading.Event()

    def flaky_then_fail(rtc):
        # 模擬情境：每次重連後緊接著成功一次，然後又開始持續失敗
        # （fail_count 要連續累積到 MAX_RETRY 次才會再次觸發重連）。
        if state["just_reconnected"]:
            state["just_reconnected"] = False
            return object()   # 隨便一個回傳值，on_result 是 no-op 不會用到
        raise RtcTimeoutError("模擬持續逾時")

    def fake_reconnect():
        reconnect_calls["count"] += 1
        state["just_reconnected"] = True
        if reconnect_calls["count"] >= target:
            # 已經證明「總重連次數可以超過 MAX_RECONNECTS」，主動喊停，
            # 避免這個測試案例因為每次重連都成功而真的無窮跑下去
            lr._stop_event.set()

    lr._loop(flaky_then_fail, lambda v: "", lambda db, rtc, v: None, None, None,
              reconnect_fn=fake_reconnect)

    actual = reconnect_calls["count"]
    assert actual >= target, (
        f"重連後如果有成功過，counter 應該歸零重算，"
        f"總重連次數應該可以超過 {threshold}，但實際只有 {actual} 次就停了"
    )
    print(f"    PASS -- 重連後穿插成功時，總共重連了 {actual} 次"
          f"（> MAX_RECONNECTS={threshold}），沒有被錯誤地提早擋下來\n")


def test_loop_runner_retries_reconnect_on_exception():
    print("[5] reconnect_fn() 本身持續丟例外時（例如 USB 真的還沒插回去），"
          "應該還是重試到 MAX_RECONNECTS 次，不是丟一次例外就整個放棄...")
    print("    （這正是實際拔 USB 測試時踩到的那個 bug：修正前這裡永遠只會是 1）")
    runner_module.time.sleep = lambda _: None

    reconnect_attempts = {"count": 0}

    def always_fail(rtc):
        raise RtcTimeoutError("模擬持續逾時")

    def reconnect_always_raises():
        reconnect_attempts["count"] += 1
        raise FrameError("模擬 USB 還沒插回去，掃過所有候選 port 都連不到裝置")

    lr = runner_module.LoopRunner()
    lr._stop_event = threading.Event()
    lr._stop_event.wait = lambda timeout=None: False   # 不用真的等 RECONNECT_RETRY_DELAY

    lr._loop(always_fail, lambda v: "", lambda db, rtc, v: None, None, None,
              reconnect_fn=reconnect_always_raises)

    expected = runner_module.LoopRunner.MAX_RECONNECTS
    actual = reconnect_attempts["count"]
    assert actual == expected, (
        f"reconnect_fn() 持續丟例外時，應該剛好重試 {expected} 次才放棄，"
        f"實際只試了 {actual} 次"
    )
    print(f"    PASS -- reconnect_fn() 持續丟例外時，正確重試了 {actual} 次才放棄"
          f"（不是像修正前那樣試一次就死）\n")


if __name__ == "__main__":
    test_seq_matching_discards_stale()
    test_seq_matching_gives_up_after_max_stale()
    test_payload_size_guard()
    test_loop_runner_reconnect_cap_gives_up()
    test_loop_runner_reconnect_cap_resets_on_success()
    test_loop_runner_retries_reconnect_on_exception()
    print("=== 全部驗證通過 ===")