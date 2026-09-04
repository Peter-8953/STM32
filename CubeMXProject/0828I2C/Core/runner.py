"""runner.py: 背景執行緒每秒執行一次指令，區分可重試錯誤與致命錯誤
（對應文件 6.1 節）。

錯誤處理策略：
    CrcError / RtcTimeoutError  -- 暫時性錯誤，重試最多 MAX_RETRY 次
    其他 Exception              -- 不明錯誤，直接停止，不亂重試
    連續失敗達上限               -- 自動停止迴圈，回到 prompt

2026-09-04：LoopRunner 新增 MAX_RECONNECTS，見 _loop() 說明——原本
「連續失敗滿 MAX_RETRY 次就重連一次」這件事本身沒有總次數上限，USB
如果持續不穩定，理論上會無限重連下去；run_once() 不需要對應的修改，
因為它本來就已經用 reconnected_once 限制整個呼叫最多重連一次。
"""

import threading
import time
from datetime import datetime

from rtc3231.exceptions import CrcError, RtcTimeoutError


def _ts() -> str:
    """時間戳記字串，用來讓使用者自己判斷：訊息之間的實際間隔，
    到底是程式邏輯真的每秒才重試一次，還是終端機顯示被延遲、
    畫面看起來擠在一起但背後其實有照間隔執行。"""
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def run_once(command: dict, db, rtc, max_retry: int = 3, reconnect_fn=None) -> bool:
    """執行一次指令（含重試），不進入每秒輪詢迴圈。

    給像 `sync` 這種「做一次就該結束」的指令用，跟 LoopRunner 的差別
    只在於：成功一次就直接回傳，不會像 temp/time 那樣持續每秒重跑。

    reconnect_fn：連續失敗達 max_retry 次時嘗試重連一次（通常是
    `rtc.reconnect`），成功的話再給一次機會完整跑到底；失敗或沒
    提供 reconnect_fn，就直接回傳 False。

    回傳 True 表示成功，False 表示重試達上限或遇到不明錯誤而放棄。
    """
    fail_count = 0
    reconnected_once = False
    while True:
        try:
            value = command["func"](rtc)
            command["on_result"](db, rtc, value)
            print(command["format"](value))
            return True
        except (CrcError, RtcTimeoutError) as e:
            fail_count += 1
            print(f"[{_ts()}] [retry {fail_count}/{max_retry}] {e}", flush=True)
            if fail_count >= max_retry:
                if reconnect_fn is not None and not reconnected_once:
                    print(f"[{_ts()}] 連續失敗 {max_retry} 次，嘗試重新連線...", flush=True)
                    try:
                        reconnect_fn()
                    except Exception as reconnect_err:
                        print(f"[{_ts()}] 重新連線失敗：{reconnect_err}", flush=True)
                        return False
                    print(f"[{_ts()}] 重新連線成功，繼續執行", flush=True)
                    fail_count = 0
                    reconnected_once = True   # 只給一次重連機會，避免無窮迴圈
                    continue
                print(f"[{_ts()}] 連續失敗 {max_retry} 次，已放棄", flush=True)
                return False
        except Exception as e:
            print(f"[{_ts()}] 未預期錯誤：{e}", flush=True)
            return False


class LoopRunner:
    MAX_RETRY = 3

    # 連續失敗滿 MAX_RETRY 次會觸發一次重連（見 _loop()）；這個數字是
    # 「這個 run() 生命週期內最多重連幾次」的總上限——避免 USB 持續
    # 不穩定（例如排線接觸不良）時，重連→立刻又失敗→再重連→...
    # 無限循環下去，永遠不會真的停下來讓使用者發現問題。
    #
    # 這個上限不是從程式一啟動就單純累加到底：只要中間有任何一次
    # func() 成功執行過，就代表前面的重連是有效的、連線目前是健康的，
    # reconnect_count 會歸零重新算（見 _loop() 成功分支）。所以這個
    # 上限真正限制的是「連續重連都換不回哪怕一次成功」的情況，而不是
    # 「這次執行期間總共重連次數」——一個偶爾斷線但大部分時間正常的
    # USB 連線，不會因為累積次數而被誤判放棄。
    MAX_RECONNECTS = 5

    # 每次重連嘗試失敗後，等這麼久再試下一次——見 _attempt_reconnect()。
    # 避免瘋狂重試，也給使用者一點反應時間（例如真的把 USB 插回去）。
    RECONNECT_RETRY_DELAY = 2.0

    def __init__(self):
        self._thread = None
        self._stop_event = threading.Event()

    def start(self, command: dict, db, rtc, reconnect_fn=None) -> None:
        """啟動背景執行緒，跑 COMMANDS 字典裡的一個項目。

        reconnect_fn：連續失敗達 MAX_RETRY 次時會呼叫這個函式嘗試
        重新連線（通常是 `rtc.reconnect`）。成功的話 fail_count 歸零、
        繼續迴圈；失敗或沒提供 reconnect_fn，才真的停止。

        如果已經有執行緒在跑，呼叫端應該先 stop() 再 start()，
        這裡不做自動處理，避免同時有兩條執行緒搶同一個 transport。
        """
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop,
            args=(command["func"], command["format"], command["on_result"], db, rtc, reconnect_fn),
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """要求背景執行緒停止，並等待它真的結束再回傳。"""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _attempt_reconnect(self, reconnect_fn, reconnect_count: int) -> tuple[bool, int]:
        """嘗試重新連線，最多到 MAX_RECONNECTS 次為止。

        2026-09-04 修正：原本的寫法是「reconnect_fn() 只要丟例外（最常見：
        USB 真的還沒插回去，reconnect() 掃過所有候選 port 都連不到，直接
        raise FrameError），就立刻整個 break、放棄」——這代表 MAX_RECONNECTS
        對「USB 物理上真的斷開」這個最常見的情境完全沒有作用：畫面上會印出
        「第 1/5 次」，但其實只試了這一次，不會有第 2~5 次的機會。這是實測
        拔 USB 才發現的，因為當時的測試只模擬了「reconnect_fn() 順利 return，
        但底層裝置其實還是壞的」這種情況，沒有模擬「reconnect_fn() 直接丟
        例外」——這是兩種不同的失敗方式，前者原本的邏輯就有正確處理，
        後者才是真正漏掉的。

        修正後：reconnect_fn() 丟例外只算「這次嘗試沒成功」，不會讓整個
        迴圈立刻死掉，休息 RECONNECT_RETRY_DELAY 秒再試下一次，直到用滿
        MAX_RECONNECTS 次或真的重連成功為止。用 Event.wait 而不是
        time.sleep 來等待，這樣使用者這時候呼叫 stop()，可以提早被喚醒，
        不用乾等整段 delay 過完。

        回傳 (是否成功, 用到目前為止的 reconnect_count)。
        """
        while reconnect_count < self.MAX_RECONNECTS:
            if self._stop_event.is_set():
                return False, reconnect_count
            reconnect_count += 1
            print(
                f"[{_ts()}] 嘗試重新連線...（第 {reconnect_count}/{self.MAX_RECONNECTS} 次）",
                flush=True,
            )
            try:
                reconnect_fn()
            except Exception as reconnect_err:
                print(f"[{_ts()}] 重新連線失敗：{reconnect_err}", flush=True)
                if reconnect_count < self.MAX_RECONNECTS:
                    if self._stop_event.wait(self.RECONNECT_RETRY_DELAY):
                        return False, reconnect_count   # 等待期間被要求停止
                continue
            print(f"[{_ts()}] 重新連線成功，繼續執行", flush=True)
            return True, reconnect_count
        return False, reconnect_count

    def _loop(self, func, format_fn, on_result, db, rtc, reconnect_fn=None):
        fail_count = 0
        reconnect_count = 0   # 見 MAX_RECONNECTS 說明
        while not self._stop_event.is_set():
            try:
                value = func(rtc)           # 回傳 dataclass
                on_result(db, rtc, value)   # 直接傳 dataclass，用欄位名稱取值
                print(f"\r{format_fn(value)}", end="", flush=True)
                # 修改後可以換行print(format_fn(value), flush=True)
                fail_count = 0
                reconnect_count = 0   # 這次成功了，代表連線目前是健康的，重連 counter 歸零重算
            except (CrcError, RtcTimeoutError) as e:
                fail_count += 1
                # 改用 \n（獨立成行）而非 \r（互相覆蓋），這樣才看得到
                # 逐次重試的過程；加時間戳記方便你自己核對實際間隔。
                print(f"[{_ts()}] [retry {fail_count}/{self.MAX_RETRY}] {e}", flush=True)
                if fail_count >= self.MAX_RETRY:
                    if reconnect_fn is None:
                        print(f"[{_ts()}] 連續失敗 {self.MAX_RETRY} 次，已停止", flush=True)
                        break
                    print(f"[{_ts()}] 連續失敗 {self.MAX_RETRY} 次，開始嘗試重新連線", flush=True)
                    reconnected, reconnect_count = self._attempt_reconnect(reconnect_fn, reconnect_count)
                    if not reconnected:
                        if self._stop_event.is_set():
                            print(f"[{_ts()}] 收到停止要求，中止重連", flush=True)
                        else:
                            print(
                                f"[{_ts()}] 已經連續重連 {self.MAX_RECONNECTS} 次仍失敗，"
                                f"不再嘗試，已停止",
                                flush=True,
                            )
                        break
                    fail_count = 0
                    # 這次不 sleep，立刻重試一次，讓使用者馬上看到恢復正常
                    continue
            except Exception as e:
                print(f"[{_ts()}] 未預期錯誤：{e}", flush=True)
                break
            time.sleep(0.5)