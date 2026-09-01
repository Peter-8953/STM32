"""test_phase4.py -- 第4階驗收：故意觸發兩種錯誤情境，確認韌體正確回應
CMD_ERR、FLAG_IS_ERROR 有設、錯誤碼正確。

格式錯誤封包（SOF/VER/CRC/LEN 不符）會被安靜丟棄這件事，第1~3階的
模擬測試已經反覆驗證過很多次，這裡不再對實機重測，專注在第4階真正
新增的兩條路徑：未知指令、SET_TIME payload 太短。

用法：
    python test_phase4.py COMx
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rtc3231.transport import SerialTransport
from rtc3231.protocol import (
    build_frame, parse_frame,
    CMD_SET_TIME, CMD_ERR,
    FLAG_IS_ERROR, ERR_UNKNOWN_CMD, ERR_PAYLOAD_TOO_SHORT,
    ID_PC,
)
from rtc3231.exceptions import RtcTimeoutError, CrcError, FrameError

DEVICE_ID = 0x02


def test_unknown_cmd(t):
    print("\n[未知指令 -> CMD_ERR / ERR_UNKNOWN_CMD]")
    seq = t.next_seq()
    t.send(build_frame(ID_PC, DEVICE_ID, 0x77, seq, b'', 0x01))  # 0x77 不是任何已定義的 CMD
    raw = t.recv()
    cmd, recv_seq, payload, flags = parse_frame(raw)
    print(f"    收到 CMD=0x{cmd:02X}, SEQ={recv_seq}, payload={payload.hex()}, FLAGS=0x{flags:02X}")

    assert cmd == CMD_ERR, f"預期 CMD_ERR(0x{CMD_ERR:02X})，收到 0x{cmd:02X}"
    assert recv_seq == seq, f"SEQ 對不起來：送出 {seq}，收到 {recv_seq}"
    assert (flags & FLAG_IS_ERROR) != 0, f"FLAG_IS_ERROR 沒有被設定，FLAGS=0x{flags:02X}"
    assert len(payload) == 1, f"預期 payload 長度 1，收到 {len(payload)}"
    assert payload[0] == ERR_UNKNOWN_CMD, \
        f"預期錯誤碼 ERR_UNKNOWN_CMD(0x{ERR_UNKNOWN_CMD:02X})，收到 0x{payload[0]:02X}"
    print("    正確：CMD_ERR、FLAG_IS_ERROR 有設、錯誤碼是 ERR_UNKNOWN_CMD")


def test_set_time_short_payload(t):
    print("\n[SET_TIME payload 太短 -> CMD_ERR / ERR_PAYLOAD_TOO_SHORT]")
    seq = t.next_seq()
    short_payload = bytes([0x07, 0xDA, 0x0C])   # 只給3 bytes，規定要7 bytes
    t.send(build_frame(ID_PC, DEVICE_ID, CMD_SET_TIME, seq, short_payload, 0x01))
    raw = t.recv()
    cmd, recv_seq, payload, flags = parse_frame(raw)
    print(f"    收到 CMD=0x{cmd:02X}, SEQ={recv_seq}, payload={payload.hex()}, FLAGS=0x{flags:02X}")

    assert cmd == CMD_ERR, f"預期 CMD_ERR，收到 0x{cmd:02X}"
    assert recv_seq == seq
    assert (flags & FLAG_IS_ERROR) != 0, f"FLAG_IS_ERROR 沒有被設定，FLAGS=0x{flags:02X}"
    assert payload[0] == ERR_PAYLOAD_TOO_SHORT, \
        f"預期錯誤碼 ERR_PAYLOAD_TOO_SHORT(0x{ERR_PAYLOAD_TOO_SHORT:02X})，收到 0x{payload[0]:02X}"
    print("    正確：CMD_ERR、FLAG_IS_ERROR 有設、錯誤碼是 ERR_PAYLOAD_TOO_SHORT")


def main():
    if len(sys.argv) != 2:
        print(f"用法: python {sys.argv[0]} COMx")
        sys.exit(1)

    port = sys.argv[1]
    print(f"開啟 {port}（boot_delay 預設 2 秒，等開機完成）...")
    t = SerialTransport(port)
    print("OK")

    try:
        test_unknown_cmd(t)
        test_set_time_short_payload(t)
        print("\n=== 第4階驗收通過（CMD_ERR / FLAG_IS_ERROR / 錯誤碼皆正確） ===")
        print("備註：格式錯誤封包（SOF/VER/CRC/LEN）安靜丟棄的行為從第1~2階")
        print("就存在，模擬測試反覆驗證過，這裡沒有另外對實機重測。")
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
