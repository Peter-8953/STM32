"""SerialTransport: 只管序列埠 bytes 進出，不知道 CMD 意義。

職責邊界：
    知道   -- 序列埠、bytes、SEQ
    不知道 -- CMD 是什麼、Arduino 是什麼、auto_detect 邏輯（那是 detect.py 的事）

SEQ 序號狀態由這個 class 維護：每個 SerialTransport 實例各自獨立，
未來多台 Arduino 對應多個 transport 實例時，序號天然不互相干擾。
"""

import time

import serial

from .exceptions import RtcTimeoutError


class SerialTransport:
    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 1.0,
                 boot_delay: float = 2.0):
        """boot_delay：開啟序列埠後要等待的秒數。開啟序列埠時（Windows/
        多數作業系統）會透過 DTR 訊號重置 Arduino，重置後 bootloader
        需要約 1~2 秒才會跳進使用者程式、開始監聽 UART。這段等待放
        在這裡（而不是只在 auto_detect 裡處理），確保不管是自動搜尋
        還是直接指定 port（例如 SerialTransport("COM3")），都不會因為
        序列埠剛開啟、Arduino 還沒開機完成，就送出請求導致逾時。
        如果確定對方不是剛重置過的 Arduino（例如已經連續使用一段
        時間），可以傳 boot_delay=0 跳過這個等待。

        baudrate：預設 115200（2026-08-21 從 9600 改過來），要跟韌體
        端 main.c 的 uart_init() 呼叫值一致，兩邊對不上會直接變亂碼，
        不會有清楚的錯誤訊息，只會一直卡在 RtcTimeoutError。韌體端
        改到 115200 時同時啟用了 U2X0 倍速模式（見 uart_hal.c），
        單純只改這個數字、韌體端沒對應處理的話是不能用的。
        """
        self._seq = 0
        self._serial = serial.Serial(port, baudrate, timeout=timeout)
        if boot_delay:
            time.sleep(boot_delay)

    def next_seq(self) -> int:
        """回傳下一個要用的 SEQ，並讓內部計數器 +1（uint16 滾回 0）。"""
        s = self._seq
        self._seq = (self._seq + 1) & 0xFFFF
        return s

    def send(self, frame: bytes) -> None:
        try:
            self._serial.write(frame)
        except (serial.SerialException, OSError) as e:
            # Windows 上 USB 序列埠瞬斷（例如電源管理睡眠、排線鬆動）
            # 常見會丟 PermissionError/OSError，統一轉成 RtcTimeoutError，
            # 讓 runner.py 既有的 MAX_RETRY 重試機制也能涵蓋這種情況，
            # 不用因為底層 I/O 錯誤的型別不同就被歸類到「不明錯誤」而直接放棄。
            raise RtcTimeoutError(f"寫入序列埠失敗（裝置可能已斷線）：{e}") from e

    def recv(self) -> bytes:
        """依 LEN 欄位算長度讀出一個完整封包，三段讀法：

        ① 等 SOF（不累積垃圾 byte）
        ② 固定 header（VER+SRC+DST+CMD+SEQ(2)+LEN = 7 bytes）
        ③ 依 LEN 讀 PAYLOAD + FLAGS(1) + CRC(2)

        任一步驟逾時都拋 RtcTimeoutError，由上層（LoopRunner /
        auto_detect）決定要不要重試。
        """
        self._wait_sof()
        header = self._read_exact(7)
        payload_len = header[6]
        rest = self._read_exact(payload_len + 3)
        return b'\xAA\x55' + header + rest

    def _wait_sof(self) -> None:
        """只保留最後兩個 byte，不累積垃圾（F8），天然免疫 payload
        裡剛好出現 0xAA 0x55 的情況（那個問題交給 LEN-based 讀法
        本身處理，這裡只負責找到下一個真正的封包開頭）。
        """
        prev = b'\x00'
        while True:
            try:
                b = self._serial.read(1)
            except (serial.SerialException, OSError) as e:
                raise RtcTimeoutError(f"讀取序列埠失敗（裝置可能已斷線）：{e}") from e
            if not b:
                raise RtcTimeoutError("等待 SOF 超時")
            if prev == b'\xAA' and b == b'\x55':
                return
            prev = b

    def _read_exact(self, n: int) -> bytes:
        buf = b''
        while len(buf) < n:
            try:
                chunk = self._serial.read(n - len(buf))
            except (serial.SerialException, OSError) as e:
                raise RtcTimeoutError(f"讀取序列埠失敗（裝置可能已斷線）：{e}") from e
            if not chunk:
                raise RtcTimeoutError(f"讀取超時，預期 {n} bytes，已讀 {len(buf)}")
            buf += chunk
        return buf

    def close(self) -> None:
        self._serial.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()