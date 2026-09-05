"""test_phase5.py -- 第5階驗收：I2C 讀寫 DS3231 失敗時，確認韌體正確回應
CMD_ERR、FLAG_IS_ERROR 有設、錯誤碼是 ERR_I2C_FAILURE，而且連續多次失敗
不會把整顆 MCU 卡死。

跟 test_phase3.py / test_phase4.py 不一樣的地方：那兩支測試觸發的錯誤都
只靠送「合法但故意設計成會出錯」的封包就能重現（例如故意送太短的
payload），封包本身完全合法，會出錯的是韌體去讀寫 DS3231 這個動作本身
——這沒辦法單純靠改封包內容觸發，需要你在跑這支腳本之前，先手動製造
一次真的 I2C 失敗，沒辦法像其他測試一樣完全自動化。

最簡單的做法：暫時拔掉 DS3231 模組跟 STM32 之間 I2C 的其中一條線（SDA
或 SCL 任一條都可以，不用兩條都拔），STM32 板子本身不用重開機、也不用
拔 USB，只要那條線斷開的狀態下再送 GET_TIME/GET_TEMP/SET_TIME 就夠了。

!! 重要 !!：下面刻意連續送三個指令（GET_TIME -> GET_TEMP -> SET_TIME）
都在「還沒插回線」的狀態下送出，不是測完一個就插回去重測——這是故意
設計成這樣的，因為 2026-09-04 實測時真的踩到一個比「沒回錯誤碼」更嚴重
的問題：第一次 GET_TIME 正確回了 CMD_ERR/ERR_I2C_FAILURE，但緊接著送
GET_TEMP 卻整個逾時沒回應，代表韌體的 while(1) main loop 被卡死了
（HAL_I2C_Mem_Read/Write 原本用 HAL_MAX_DELAY，I2C 週邊卡進 BUSY 狀態
後就永遠不返回）。這支測試如果只單獨測一個指令、每次都重新插拔線，
反而測不出這個問題——一定要在同一個「斷線」狀態下連續送好幾個指令，
才能驗證韌體是不是真的不會被卡死。

後續追查發現：上面那個「卡死」問題只有拔 SCL 才會發生，拔 SDA 不會
——SDA 斷開時 I2C 硬體偵測到的是乾淨的 NACK（無應答），DS3231_I2C_
TIMEOUT_MS 保護得到；SCL 斷開會讓 STM32 卡在等待 clock stretching
結束，這是硬體層級的等待，不受那個 timeout 保護，main loop 真的會
整個卡死，需要另一道防線（IWDG）才能救回來，不需要拔 USB。

所以這支腳本請用「拔 SDA」來驗證（驗證的是 ERR_I2C_FAILURE 回報本身
正不正確）；「拔 SCL」造成整個卡死、靠 IWDG 自動重置這件事，另外寫在
test_phase6.py 裡驗證，因為那支測試的等待時間長很多（要等 IWDG 真的
觸發重置），混在一起會讓這支測試變得又慢又難懂。

跟 test_firmware.py / test_phase3.py / test_phase4.py 一致：直接用
transport.py + protocol.py 手動組包，不透過 DS3231 class——這裡要驗證
的是韌體端實際回傳的 raw bytes 對不對，跟 Python 端怎麼解讀（丟哪種
例外、要不要重試）是另一件事，那部分已經在 test_protocol_robustness.py
用模擬資料驗證過了。

用法：
    python test_phase5.py COMx
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rtc3231.transport import SerialTransport
from rtc3231.protocol import (
    build_frame, parse_frame,
    CMD_GET_TIME, CMD_GET_TEMP, CMD_SET_TIME, CMD_DATA_TIME, CMD_ERR,
    FLAG_IS_ERROR, ERR_I2C_FAILURE,
    ID_PC,
)
from rtc3231.exceptions import RtcTimeoutError, CrcError, FrameError

DEVICE_ID = 0x02


def _assert_i2c_error_response(raw: bytes, label: str) -> None:
    cmd, recv_seq, payload, flags = parse_frame(raw)
    print(f"    [{label}] 收到 CMD=0x{cmd:02X}, payload={payload.hex()}, FLAGS=0x{flags:02X}")

    assert cmd == CMD_ERR, f"[{label}] 預期 CMD_ERR(0x{CMD_ERR:02X})，收到 0x{cmd:02X}"
    assert (flags & FLAG_IS_ERROR) != 0, f"[{label}] FLAG_IS_ERROR 沒有被設定，FLAGS=0x{flags:02X}"
    assert len(payload) == 1, f"[{label}] 預期 payload 長度 1，收到 {len(payload)}"
    assert payload[0] == ERR_I2C_FAILURE, (
        f"[{label}] 預期錯誤碼 ERR_I2C_FAILURE(0x{ERR_I2C_FAILURE:02X})，"
        f"收到 0x{payload[0]:02X}——如果收到的其實是正常資料（CMD_DATA_*），"
        f"代表 I2C 線路其實沒有真的斷開，檢查一下拔的是不是正確的那條線"
    )
    print(f"    [{label}] 正確：CMD_ERR、FLAG_IS_ERROR 有設、錯誤碼是 ERR_I2C_FAILURE")


def test_get_time_i2c_failure(t):
    print("\n[GET_TIME，I2C 斷開 -> CMD_ERR / ERR_I2C_FAILURE]")
    seq = t.next_seq()
    t.send(build_frame(ID_PC, DEVICE_ID, CMD_GET_TIME, seq, b'', 0x01))
    _assert_i2c_error_response(t.recv(), "GET_TIME")


def test_get_temp_i2c_failure(t):
    print("\n[GET_TEMP，I2C 斷開 -> CMD_ERR / ERR_I2C_FAILURE]")
    seq = t.next_seq()
    t.send(build_frame(ID_PC, DEVICE_ID, CMD_GET_TEMP, seq, b'', 0x01))
    _assert_i2c_error_response(t.recv(), "GET_TEMP")


def test_set_time_i2c_failure(t):
    print("\n[SET_TIME，I2C 斷開 -> CMD_ERR / ERR_I2C_FAILURE]")
    payload = bytes([0x07, 0xEA, 9, 1, 12, 0, 0])   # 隨便一個合法的 7-byte 時間 payload
    seq = t.next_seq()
    t.send(build_frame(ID_PC, DEVICE_ID, CMD_SET_TIME, seq, payload, 0x01))
    _assert_i2c_error_response(t.recv(), "SET_TIME")


def test_recovers_after_reconnecting_i2c(t):
    print("\n[線接回去之後，GET_TIME 應該恢復正常]")
    seq = t.next_seq()
    t.send(build_frame(ID_PC, DEVICE_ID, CMD_GET_TIME, seq, b'', 0x01))
    cmd, recv_seq, payload, flags = parse_frame(t.recv())
    print(f"    收到 CMD=0x{cmd:02X}")
    assert cmd == CMD_DATA_TIME, (
        f"接回線之後 GET_TIME 應該要恢復正常，卻收到 0x{cmd:02X}"
        f"——檢查線是不是真的接好了"
    )
    print("    正確：接回線之後 GET_TIME 恢復正常，I2C 沒有被剛才的失敗狀態卡住")


def main():
    if len(sys.argv) != 2:
        print(f"用法: python {sys.argv[0]} COMx")
        sys.exit(1)

    port = sys.argv[1]
    print(f"開啟 {port}（boot_delay 預設 2 秒，等開機完成）...")
    t = SerialTransport(port)
    print("OK")

    try:
        input(
            "\n請先暫時拔掉 DS3231 模組跟 STM32 之間 I2C 的 SDA 或 SCL 任一條線"
            "（不用拔 USB，STM32 本身繼續跑），拔著的狀態下按 Enter 繼續..."
        )

        test_get_time_i2c_failure(t)
        test_get_temp_i2c_failure(t)
        test_set_time_i2c_failure(t)
        print("\n=== 錯誤情境驗收通過（CMD_ERR / FLAG_IS_ERROR / ERR_I2C_FAILURE 皆正確） ===")

        input("\n請把剛才拔掉的線接回去，接好之後按 Enter 繼續驗證恢復正常...")
        test_recovers_after_reconnecting_i2c(t)

        print("\n=== 第5階驗收全部通過 ===")

    except AssertionError as e:
        print(f"\n*** 驗收失敗: {e} ***")
        sys.exit(1)
    except (RtcTimeoutError, CrcError, FrameError) as e:
        print(f"\n*** 通訊失敗: {e} ***")
        print("如果是逾時，先確認板子本身還活著（LED有沒有反應）、USB連線正常")
        print("——這支測試只故意弄斷I2C，不該連UART/USB都斷掉。")
        sys.exit(1)
    finally:
        t.close()


if __name__ == "__main__":
    main()