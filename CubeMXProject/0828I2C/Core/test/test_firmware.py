"""test_firmware.py -- 第2階驗收：對 STM32 送 GET_TIME，確認拿到正確格式的
CMD_DATA_TIME 回應。

刻意不用 DS3231 class 或 auto_detect()——這兩個的初始化都會先送
CMD_GET_ID 做握手，但第2階韌體的 dispatch 只認 CMD_GET_TIME（見計畫書
5.2 節），CMD_GET_ID 要等第3階才會接上，用 DS3231(port) 現在會卡在
__init__ 裡等一個永遠不會回應的 GET_ID。所以這裡直接用 transport.py +
protocol.py 這兩層，手動組 GET_TIME 封包，跳過 GET_ID 前置步驟。

假設這個檔案跟 test_db_integration.py 放在同一層（例如 tests/），
用同樣的 sys.path 手法找到 rtc3231 package；如果實際擺放位置不同，
改這裡的 sys.path.insert 那行就好。

用法：
    python test_firmware.py COMx
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rtc3231.transport import SerialTransport
from rtc3231.protocol import build_frame, parse_frame, CMD_GET_TIME, CMD_DATA_TIME, ID_PC
from rtc3231.exceptions import RtcTimeoutError, CrcError, FrameError

# main.c 裡目前寫死的 MY_DEVICE_ID（見 main.c 的 USER CODE BEGIN PD）。
# 如果之後改了那個常數，這裡也要跟著改。第2階的 dispatch 還沒有檢查
# DST 是不是自己，所以理論上填別的值也會回應，但填對的值比較符合協定
# 語意，也預留了之後第4階要驗證 DST 時不用改這支腳本。
DEVICE_ID = 0x02


def main():
    if len(sys.argv) != 2:
        print(f"用法: python {sys.argv[0]} COMx")
        sys.exit(1)

    port = sys.argv[1]

    print(f"[1] 開啟 {port}（boot_delay 預設 2 秒，等開機完成）...")
    t = SerialTransport(port)
    print("    OK")

    try:
        print("[2] 送出 GET_TIME...")
        seq = t.next_seq()
        frame = build_frame(ID_PC, DEVICE_ID, CMD_GET_TIME, seq, b'', 0x01)
        t.send(frame)

        print("[3] 等待回應...")
        raw = t.recv()
        cmd, recv_seq, payload, flags = parse_frame(raw)

        print(f"    收到 CMD=0x{cmd:02X}, SEQ={recv_seq}, LEN={len(payload)}, FLAGS=0x{flags:02X}")

        assert cmd == CMD_DATA_TIME, f"預期 CMD_DATA_TIME(0x{CMD_DATA_TIME:02X})，收到 0x{cmd:02X}"
        assert len(payload) == 7, f"預期 payload 長度 7，收到 {len(payload)}"
        assert recv_seq == seq, f"回應的 SEQ({recv_seq}) 跟請求的 SEQ({seq}) 對不起來"

        year = (payload[0] << 8) | payload[1]
        month, day, hour, minute, sec = payload[2], payload[3], payload[4], payload[5], payload[6]
        print(f"    解析出時間: {year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{sec:02d}")

        print("\n=== 第2階 GET_TIME 驗收通過 ===")

    except (RtcTimeoutError, CrcError, FrameError) as e:
        print(f"\n*** 失敗: {e} ***")
        print("如果完全沒反應，照順序排查：")
        print("  1. main.c 有沒有重新編譯、燒錄進板子（IAR 裡確認 build 是最新的）")
        print("  2. COM port 對不對（裝置管理員 / ls /dev/tty.* 確認）")
        print("  3. DTR 開機重置的假設是否成立——這是計畫書第2節特別點出來")
        print("     要實測的假設。如果懷疑是開機時機問題，把上面")
        print("     SerialTransport(port) 那行改成 SerialTransport(port, boot_delay=0)")
        print("     再試一次，排除是不是等待時間算錯的問題")
        sys.exit(1)
    finally:
        t.close()


if __name__ == "__main__":
    main()
