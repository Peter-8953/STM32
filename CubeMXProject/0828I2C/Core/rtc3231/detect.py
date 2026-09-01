"""auto_detect(): 掃描序列埠，找到會回應 GET_ID 的那個 Arduino。

F9：獨立成這個模組，不放進 transport.py —— transport.py 只管
bytes 進出，不知道 CMD 的語意；auto_detect() 需要組 GET_ID 封包、
判斷回應是不是 DATA_ID，這些屬於協定層邏輯，職責邊界要分開。
"""

import serial.tools.list_ports

from .transport import SerialTransport
from .protocol import (
    build_frame, parse_frame,
    CMD_GET_ID, CMD_DATA_ID,
    ID_PC, ID_BROADCAST,
    FLAG_NEED_ACK,
)
from .exceptions import FrameError, RtcTimeoutError, CrcError


def auto_detect(timeout: float = 0.5) -> str:
    """掃描所有序列埠，逐一送 GET_ID，第一個回 DATA_ID 的就是 Arduino。

    DST 用 ID_BROADCAST（0x00）—— auto_detect 階段還不知道對方的
    裝置 ID，且 0xFF 是保留值，依規範禁止用於 DST（F2 修正）。

    開啟序列埠後的開機等待時間由 SerialTransport 本身處理（見
    transport.py 的 boot_delay 參數），這裡不用重複處理。

    任何一個 port 連線失敗或逾時，都當作「這不是我們要找的裝置」
    直接跳過、試下一個 port，不會讓整個掃描中斷。
    """
    for p in serial.tools.list_ports.comports():
        t = None
        try:
            t = SerialTransport(p.device, timeout=timeout)
            seq = t.next_seq()
            frame = build_frame(ID_PC, ID_BROADCAST, CMD_GET_ID, seq, b'', FLAG_NEED_ACK)
            t.send(frame)
            cmd, _, _, _ = parse_frame(t.recv())
            if cmd == CMD_DATA_ID:
                return p.device
        except (RtcTimeoutError, CrcError, FrameError, OSError):
            # F1：這裡刻意只接 RtcTimeoutError，不是內建 TimeoutError，
            # 否則 serial.Serial() 連線失敗拋出的內建 TimeoutError
            # 會直接漏網、讓整個 auto_detect() 崩潰。
            continue
        finally:
            if t:
                t.close()

    raise FrameError("找不到 Arduino，請確認韌體已燒錄且 USB 已連接")


def auto_detect_all(timeout: float = 0.5) -> list:
    """掃描所有序列埠，回傳「全部」有回應 GET_ID 的 port（不是只回傳第一個）。

    給多台 Arduino 對一台電腦的情境用：auto_detect() 找到第一個就
    停止，這個函式則是掃完整輪，把每個真的有回應的 port 都收集起來。

    回傳值是 port 字串的 list（例如 ["COM3", "COM5"]），順序依照
    `serial.tools.list_ports.comports()` 回傳的順序，不保證跟裝置
    實際的 device_id 大小順序一致。

    跟 auto_detect() 一樣，任何一個 port 連線失敗或逾時都直接跳過，
    不會讓整個掃描中斷；如果完全沒找到裝置，回傳空 list（不像
    auto_detect() 會拋 FrameError，因為「找不到任何裝置」在多裝置
    情境下不一定是錯誤，呼叫端可能只是想確認目前有幾台在線）。
    """
    found = []
    for p in serial.tools.list_ports.comports():
        t = None
        try:
            t = SerialTransport(p.device, timeout=timeout)
            seq = t.next_seq()
            frame = build_frame(ID_PC, ID_BROADCAST, CMD_GET_ID, seq, b'', FLAG_NEED_ACK)
            t.send(frame)
            cmd, _, _, _ = parse_frame(t.recv())
            if cmd == CMD_DATA_ID:
                found.append(p.device)
        except (RtcTimeoutError, CrcError, FrameError, OSError):
            continue
        finally:
            if t:
                t.close()

    return found