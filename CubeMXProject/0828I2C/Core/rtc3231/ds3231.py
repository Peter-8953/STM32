"""DS3231: 使用者唯一接觸的 class。

初始化時主動送 GET_ID 查詢裝置 ID（ID 從 Arduino 本身查來，
Python 端不維護對照表）。

F3：所有時間一律 UTC（datetime.now(timezone.utc)），DS3231 存 UTC。
F4：sync_from_pc() 確認回應 CMD 是 ACK，不是丟棄回傳值。
F5：所有方法回傳 dataclass，不用裸 tuple。

2026-09-04：所有讀回應的地方一律先過 _recv_matching()，核對 SEQ 跟這次
請求送出的值一致才採信，避免上一次逾時重試留下的過期回應被誤當成這次
的答案（見 _recv_matching() docstring）。這裡沒有沿用 F1/F2... 的編號，
因為不確定 F6、F7 是不是已經在你其他文件裡用掉了，怕跟既有編號撞在一起。
"""

from datetime import datetime, timezone

from .transport import SerialTransport
from .protocol import (
    build_frame, parse_frame,
    CMD_GET_ID, CMD_DATA_ID,
    CMD_GET_TIME, CMD_DATA_TIME,
    CMD_GET_TEMP, CMD_DATA_TEMP,
    CMD_SET_TIME, CMD_ACK,
    ID_PC, ID_BROADCAST,
    FLAG_NEED_ACK, FLAG_IS_ERROR, ERR_UNKNOWN_CMD, ERR_PAYLOAD_TOO_SHORT,
)
from .detect import auto_detect, auto_detect_all
from .exceptions import FrameError, DeviceError, StaleResponseError
from .models import TempReading, TimeReading, SyncResult


def _payload_to_datetime(payload: bytes) -> datetime:
    """把 7-byte 時間 payload（年高/年低/月/日/時/分/秒）轉成 UTC datetime。"""
    year = (payload[0] << 8) | payload[1]
    month, day, hour, minute, sec = payload[2], payload[3], payload[4], payload[5], payload[6]
    return datetime(year, month, day, hour, minute, sec, tzinfo=timezone.utc)


def _datetime_to_payload(dt: datetime) -> bytes:
    """把 datetime 轉成 7-byte payload，寫入 SET_TIME 用。"""
    return bytes((
        (dt.year >> 8) & 0xFF,
        dt.year & 0xFF,
        dt.month,
        dt.day,
        dt.hour,
        dt.minute,
        dt.second,
    ))


_ERR_MESSAGES = {
    ERR_UNKNOWN_CMD: "未知指令",
    ERR_PAYLOAD_TOO_SHORT: "payload 長度不足",
}


def _decode_error_code(payload: bytes) -> str:
    """把 CMD_ERR 的 payload[0] 錯誤碼轉成人看得懂的說明文字，對應
    protocol.py 的 ERR_* 常數（跟 main.c 的 ERR_* 巨集一致）。
    """
    if not payload:
        return "無錯誤碼"
    code = payload[0]
    return _ERR_MESSAGES.get(code, f"未知錯誤碼 {code:#04x}")


def _check_error(flags: int, payload: bytes, context: str) -> None:
    """如果回應的 FLAGS 有設 FLAG_IS_ERROR，代表 Arduino 明確、合法地
    回報這次請求失敗（不是封包本身有問題），丟出 DeviceError。

    這個檢查刻意放在每個方法『判斷 cmd 是否為預期值』之前：舊韌體
    （還沒補這次 FLAG_IS_ERROR 修改的板子）送 CMD_ERR 時 flags 仍是
    0x00，這裡會直接跳過、自然落到後面既有的『cmd 不符預期』檢查，
    行為跟修改前一致，新舊韌體都能正確處理，不用同時燒錄。
    """
    if flags & FLAG_IS_ERROR:
        raise DeviceError(f"Arduino 回報錯誤（{context}）：{_decode_error_code(payload)}")


class DS3231:
    # _recv_matching() 見下方說明：連續收到這麼多個 SEQ 不符的過期回應
    # 都放棄之後，才真的當成錯誤拋出。跟 runner.py 的 MAX_RETRY 是兩個
    # 不同層級的概念（那個是「送出請求後完全沒回應」要不要重送整個請求；
    # 這個是「已經收到回應了，但不是這次要的那個」要丟棄幾次），只是
    # 剛好都選了 3 這個量級。
    _MAX_STALE_RESPONSES = 3

    def __init__(self, port: str = None):
        resolved = port or auto_detect()
        self._port = resolved
        self._transport = SerialTransport(resolved)
        self._device_id = self._fetch_device_id()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self._transport.close()

    def _recv_matching(self, expected_seq: int, context: str):
        """讀一個回應封包，並確保 SEQ 真的等於 expected_seq（這次請求
        送出的 seq）才回傳；SEQ 對不上就視為過期回應，直接丟棄、繼續
        讀下一個。

        背景：在這個修改之前，這裡從來沒有核對過這件事，完全是靠
        「transport.recv() 讀到的下一個封包，就一定是這次請求的答案」
        這個假設——多數時候成立，但有一個具體會出事的情境：上一次
        請求逾時（RtcTimeoutError），runner.py 的重試邏輯送出了新的
        請求（新的 seq），但上一次真正的、遲來的回應這時候才姍姍來遲，
        排在這次 transport.recv() 讀取結果的最前面。沒有這層檢查的話，
        程式會直接把這個過期回應的內容（舊的溫度/時間值、舊的 seq）
        當成這次請求的答案，錯的資料就這樣寫進資料庫，而且完全不會
        有任何錯誤訊息——因為從封包格式、CRC 的角度看，這個過期回應
        本身完全合法，只是不是「這次」要的那個。

        處理方式：SEQ 對不上就丟棄、繼續讀下一個，最多丟棄
        _MAX_STALE_RESPONSES 次；連續這麼多次都對不上，才真的放棄，
        拋出 StaleResponseError（避免序列埠一直收到過期資料時無窮迴圈；
        這個例外刻意不在 runner.py 的重試清單裡，理由見
        exceptions.StaleResponseError 的 docstring）。

        回傳 parse_frame() 的四元組 (cmd, seq, payload, flags)，這裡的
        seq 保證等於 expected_seq，呼叫端不用再自己核對一次。
        """
        for _ in range(self._MAX_STALE_RESPONSES + 1):
            cmd, recv_seq, payload, flags = parse_frame(self._transport.recv())
            if recv_seq == expected_seq:
                return cmd, recv_seq, payload, flags
            # SEQ 不符：這是某次舊請求的過期回應，丟棄，不當成這次的答案，
            # 繼續讀下一個封包（迴圈自然繼續）。
        raise StaleResponseError(
            f"{context}：連續收到 {self._MAX_STALE_RESPONSES} 個 SEQ 不符的過期回應"
            f"（預期 {expected_seq}），放棄"
        )

    def _fetch_device_id(self) -> int:
        seq = self._transport.next_seq()
        frame = build_frame(ID_PC, ID_BROADCAST, CMD_GET_ID, seq, b'', FLAG_NEED_ACK)
        self._transport.send(frame)
        cmd, _, payload, flags = self._recv_matching(seq, "GET_ID")
        _check_error(flags, payload, "GET_ID")
        if cmd != CMD_DATA_ID:
            raise FrameError(f"預期 CMD_DATA_ID(0x13)，收到 {cmd:#04x}")
        return payload[0]

    @property
    def device_id(self) -> int:
        return self._device_id

    def reconnect(self) -> None:
        """關閉目前（可能已經壞掉）的連線，重新建立一個新的。

        用途：USB 瞬斷、電源管理睡眠導致底層 handle 失效時，光是
        重插 USB 沒有用（見多輪對話中實際遇到的情況）——舊的
        SerialTransport 物件還握著壞掉的 handle，需要真的建立一個
        新的 serial.Serial() 才能恢復。這個方法就是做這件事。

        重連策略：
            1. 先試著用原本記住的 port 重連（多數情況下 USB 重新
               枚舉會拿到同一個 COM 號碼）
            2. 如果那個 port 連不上了（重新枚舉換了號碼），改用
               auto_detect_all() 掃描所有候選 port

        多裝置安全性：候選 port 連上之後，一定要驗證回傳的
        device_id 是否跟原本這個 DS3231 實例綁定的 device_id 一致。
        如果不一致，代表連到的是「另一台正常運作的 Arduino」，不是
        我們原本要救回來的那台——必須跳過，不能誤用，否則在多裝置
        情境下會搶走別台的連線、造成混亂。

        全部候選都試過還是找不到吻合的裝置，拋出 FrameError。
        """
        expected_id = self._device_id

        try:
            self._transport.close()
        except Exception:
            pass   # 舊連線可能已經壞了，close() 本身失敗也沒關係，忽略即可

        candidates = [self._port]
        try:
            for p in auto_detect_all():
                if p not in candidates:
                    candidates.append(p)
        except Exception:
            pass   # 掃描本身失敗就算了，至少還有原本記住的 port 可以試

        last_error = None
        for candidate_port in candidates:
            new_transport = None
            try:
                new_transport = SerialTransport(candidate_port)
                self._transport = new_transport   # 暫時替換，_fetch_device_id 靠它送封包
                actual_id = self._fetch_device_id()
            except Exception as e:
                last_error = e
                if new_transport is not None:
                    try:
                        new_transport.close()
                    except Exception:
                        pass
                continue

            if actual_id != expected_id:
                # 這個 port 是別台裝置，不是我們原本要接回的那台，
                # 必須跳過，不能誤用（多裝置安全性）。
                try:
                    new_transport.close()
                except Exception:
                    pass
                last_error = FrameError(
                    f"{candidate_port} 回應的是 device_id={actual_id:#04x}，"
                    f"不是預期的 {expected_id:#04x}，跳過"
                )
                continue

            # 找到吻合的裝置，重連成功
            self._port = candidate_port
            return

        raise FrameError(
            f"重新連線失敗，找不到 device_id={expected_id:#04x} 的裝置：{last_error}"
        )

    @property
    def datetime(self) -> TimeReading:
        seq = self._transport.next_seq()
        frame = build_frame(ID_PC, self._device_id, CMD_GET_TIME, seq, b'', FLAG_NEED_ACK)
        self._transport.send(frame)
        cmd, recv_seq, payload, flags = self._recv_matching(seq, "GET_TIME")
        _check_error(flags, payload, "GET_TIME")
        if cmd != CMD_DATA_TIME:
            raise FrameError(f"預期 CMD_DATA_TIME(0x11)，收到 {cmd:#04x}")
        return TimeReading(
            datetime=_payload_to_datetime(payload),
            seq=recv_seq,
        )

    @property
    def temperature(self) -> TempReading:
        seq = self._transport.next_seq()
        frame = build_frame(ID_PC, self._device_id, CMD_GET_TEMP, seq, b'', FLAG_NEED_ACK)
        self._transport.send(frame)
        cmd, recv_seq, payload, flags = self._recv_matching(seq, "GET_TEMP")
        _check_error(flags, payload, "GET_TEMP")
        if cmd != CMD_DATA_TEMP:
            raise FrameError(f"預期 CMD_DATA_TEMP(0x12)，收到 {cmd:#04x}")
        temp_int = payload[0] if payload[0] < 128 else payload[0] - 256  # int8_t 轉回有號
        return TempReading(
            temperature=temp_int + payload[1] / 100,
            read_at=_payload_to_datetime(payload[2:]),
            seq=recv_seq,
        )

    def sync_from_pc(self) -> SyncResult:
        now = datetime.now(timezone.utc)   # F3：UTC 時間
        seq = self._transport.next_seq()
        frame = build_frame(
            ID_PC, self._device_id, CMD_SET_TIME,
            seq, _datetime_to_payload(now), FLAG_NEED_ACK,
        )
        self._transport.send(frame)
        cmd, recv_seq, payload, flags = self._recv_matching(seq, "SET_TIME")
        _check_error(flags, payload, "SET_TIME")
        if cmd != CMD_ACK:              # F4：驗 ACK CMD
            raise FrameError(f"校時失敗，預期 ACK(0x10)，收到 {cmd:#04x}")
        return SyncResult(seq=recv_seq)