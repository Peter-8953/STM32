"""test_phase3.py -- 第3階驗收：依序測試 CMD_GET_ID、CMD_GET_TEMP、
CMD_SET_TIME（緊接著用 GET_TIME 確認真的寫進 DS3231，不是只回 ACK 裝忙）。

跟 test_firmware.py 用同樣的手法：直接用 transport.py + protocol.py
手動組封包。第3階韌體已經接上 CMD_GET_ID 了，理論上 DS3231 class 的
auto_detect() 現在可以動，但這裡刻意保持跟 test_firmware.py 一致的
手動組包風格，方便兩份腳本對照著看、也方便先跑這份再決定要不要
改用更高層的介面。

假設這個檔案跟 test_firmware.py 放在同一層，用同樣的 sys.path 手法。

用法：
    python test_phase3.py COMx
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rtc3231.transport import SerialTransport
from rtc3231.protocol import (
    build_frame, parse_frame,
    CMD_GET_TIME, CMD_SET_TIME, CMD_GET_TEMP, CMD_GET_ID,
    CMD_DATA_TIME, CMD_DATA_TEMP, CMD_DATA_ID, CMD_ACK,
    ID_PC,
)
from rtc3231.exceptions import RtcTimeoutError, CrcError, FrameError

# main.c 裡目前寫死的 MY_DEVICE_ID（見 main.c 的 USER CODE BEGIN PD）。
# 跟 test_firmware.py 用同一個常數，如果之後改了那個define，這裡也要改。
DEVICE_ID = 0x02


def test_get_id(t):
    print("\n[GET_ID]")
    seq = t.next_seq()
    t.send(build_frame(ID_PC, DEVICE_ID, CMD_GET_ID, seq, b'', 0x01))
    raw = t.recv()
    cmd, recv_seq, payload, flags = parse_frame(raw)
    print(f"    收到 CMD=0x{cmd:02X}, SEQ={recv_seq}, payload={payload.hex()}")

    assert cmd == CMD_DATA_ID, f"預期 CMD_DATA_ID(0x{CMD_DATA_ID:02X})，收到 0x{cmd:02X}"
    assert recv_seq == seq, f"SEQ 對不起來：送出 {seq}，收到 {recv_seq}"
    assert len(payload) == 1, f"預期 payload 長度 1，收到 {len(payload)}"
    assert payload[0] == DEVICE_ID, f"預期裝置 ID 0x{DEVICE_ID:02X}，收到 0x{payload[0]:02X}"
    print(f"    裝置 ID = 0x{payload[0]:02X}，正確")


def test_get_temp(t):
    print("\n[GET_TEMP]")
    seq = t.next_seq()
    t.send(build_frame(ID_PC, DEVICE_ID, CMD_GET_TEMP, seq, b'', 0x01))
    raw = t.recv()
    cmd, recv_seq, payload, flags = parse_frame(raw)
    print(f"    收到 CMD=0x{cmd:02X}, SEQ={recv_seq}, LEN={len(payload)}")

    assert cmd == CMD_DATA_TEMP, f"預期 CMD_DATA_TEMP(0x{CMD_DATA_TEMP:02X})，收到 0x{cmd:02X}"
    assert recv_seq == seq
    assert len(payload) == 9, f"預期 payload 長度 9，收到 {len(payload)}"

    temp_int = payload[0] if payload[0] < 128 else payload[0] - 256   # MSB 是兩補數有號值
    temp_frac = payload[1]
    year = (payload[2] << 8) | payload[3]
    month, day, hour, minute, sec = payload[4], payload[5], payload[6], payload[7], payload[8]

    print(f"    溫度 = {temp_int}.{temp_frac:02d} °C")
    print(f"    時間 = {year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{sec:02d}")
    print("    !! 溫度小數(0/25/50/75)編碼還是待確認假設，先看數字合不合理就好 !!")


def test_set_time_roundtrip(t):
    print("\n[SET_TIME -> GET_TIME round trip]")
    # 故意選一個跟現在時間差很多的日期，確定讀回來不是巧合對到現在時間
    year, month, day, hour, minute, sec = (2031, 3, 15, 9, 20, 5)
    payload = bytes([(year >> 8) & 0xFF, year & 0xFF, month, day, hour, minute, sec])

    seq = t.next_seq()
    t.send(build_frame(ID_PC, DEVICE_ID, CMD_SET_TIME, seq, payload, 0x01))
    raw = t.recv()
    cmd, recv_seq, resp_payload, flags = parse_frame(raw)
    print(f"    SET_TIME 收到 CMD=0x{cmd:02X}, SEQ={recv_seq}")
    assert cmd == CMD_ACK, f"預期 CMD_ACK(0x{CMD_ACK:02X})，收到 0x{cmd:02X}"
    assert recv_seq == seq

    time.sleep(0.2)

    seq2 = t.next_seq()
    t.send(build_frame(ID_PC, DEVICE_ID, CMD_GET_TIME, seq2, b'', 0x01))
    raw2 = t.recv()
    cmd2, recv_seq2, payload2, flags2 = parse_frame(raw2)
    assert cmd2 == CMD_DATA_TIME, f"預期 CMD_DATA_TIME，收到 0x{cmd2:02X}"

    r_year = (payload2[0] << 8) | payload2[1]
    r_month, r_day, r_hour, r_minute, r_sec = payload2[2], payload2[3], payload2[4], payload2[5], payload2[6]
    print(f"    GET_TIME 讀回 = {r_year:04d}-{r_month:02d}-{r_day:02d} {r_hour:02d}:{r_minute:02d}:{r_sec:02d}")

    assert (r_year, r_month, r_day, r_hour, r_minute) == (year, month, day, hour, minute), \
        "GET_TIME 讀回的時間跟剛剛 SET_TIME 寫入的對不起來，SET_TIME 可能沒有真的寫進 DS3231"
    assert abs(r_sec - sec) <= 2, f"秒數差太多：寫入 {sec}，讀回 {r_sec}（容許 <=2 秒的往返延遲誤差）"
    print("    寫入/讀回一致 -> SET_TIME 確認真的寫進 DS3231，不是裝忙")


def main():
    if len(sys.argv) != 2:
        print(f"用法: python {sys.argv[0]} COMx")
        sys.exit(1)

    port = sys.argv[1]
    print(f"開啟 {port}（boot_delay 預設 2 秒，等開機完成）...")
    t = SerialTransport(port)
    print("OK")

    try:
        test_get_id(t)
        test_get_temp(t)
        test_set_time_roundtrip(t)
        print("\n=== 第3階驗收通過（GET_ID / GET_TEMP / SET_TIME round trip） ===")
        print("提醒：SET_TIME 測試把 DS3231 時間改成了 2031-03-15，測完記得")
        print("再送一次正確時間的 SET_TIME 改回來，或直接不管它，反正之後")
        print("測的時候會再看到不合理的年份就知道是這次測試留下的痕跡。")
    except AssertionError as e:
        print(f"\n*** 驗收失敗: {e} ***")
        sys.exit(1)
    except (RtcTimeoutError, CrcError, FrameError) as e:
        print(f"\n*** 通訊失敗: {e} ***")
        sys.exit(1)
    finally:
        t.close()


if __name__ == "__main__":
    main()
