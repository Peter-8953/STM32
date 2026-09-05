"""test_phase6.py -- 第6階驗收：獨立看門狗（IWDG）能在 main loop 真的
卡死時自動把整顆 MCU 重置，不需要人為拔插 USB。

背景：2026-09-04 實測發現拔掉 I2C 的 SCL 線（不是 SDA）會讓 STM32 的
I2C 週邊卡在等待 clock stretching 結束——這是硬體層級的等待，不受
rtc_driver.c 的 DS3231_I2C_TIMEOUT_MS 保護（那個保護得到的是 SDA 斷開
造成的乾淨 NACK，SDA 斷開的驗收見 test_phase5.py）。main() 的 while(1)
會整個卡死在 handle_get_time()/handle_get_temp()/handle_set_time()
裡面，回不去 recv_frame()，UART 完全沒有回應，之前只能靠拔 USB 觸發
DTR 重置來恢復。

IWDG 是最後一道防線：不管卡在哪裡、什麼原因，只要 while(1) 超過大約
4 秒沒有繞回去餵狗（見 main.c 的 MX_IWDG_Init() 說明），硬體就會自動
重置整顆 MCU，清掉包括 I2C 週邊在內的所有狀態。這支測試驗證：SCL 斷開
卡死之後，完全不去動 USB，board 也會自己恢復、重新開始回應 UART。

跟 test_phase5.py 不一樣：這裡刻意拔的是 SCL（不是 SDA），因為只有
SCL 斷開才會真的卡死 main loop；如果你剛才 test_phase5.py 是拔 SDA
在測，這裡要先接回去、換拔 SCL。另外這支測試單次要等到接近
RECOVERY_TIMEOUT_S 秒（IWDG ~4秒觸發 + board 重新開機時間），比其他
測試腳本慢很多，是正常現象，不是卡住。

用法：
    python test_phase6.py COMx
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rtc3231.transport import SerialTransport
from rtc3231.protocol import (
    build_frame, parse_frame,
    CMD_GET_TIME, CMD_ERR,
    FLAG_IS_ERROR, ERR_I2C_FAILURE,
    ID_PC,
)
from rtc3231.exceptions import RtcTimeoutError, CrcError, FrameError

DEVICE_ID = 0x02

# IWDG 大約 4 秒觸發重置（見 main.c 的 MX_IWDG_Init() 說明，LSI 振盪器
# 本身有公差，實際時間可能有落差），加上重開機時間，這裡給 10 秒寬限，
# 比其他測試腳本預設的 1 秒逾時長很多，是刻意的。
RECOVERY_TIMEOUT_S = 10.0


def main():
    if len(sys.argv) != 2:
        print(f"用法: python {sys.argv[0]} COMx")
        sys.exit(1)

    port = sys.argv[1]

    input(
        "\n請先確認 I2C 的『SCL』線（不是 SDA）目前是斷開的狀態——只有\n"
        "SCL 斷開才會真的卡死 main loop，SDA 斷開不會（那是 test_phase5.py\n"
        "在測的情境，不會用到這支腳本要驗證的 IWDG）。斷開之後按 Enter 繼續..."
    )

    print(f"開啟 {port}，這次用比較長的 timeout（{RECOVERY_TIMEOUT_S} 秒）...")
    t = SerialTransport(port, timeout=RECOVERY_TIMEOUT_S)
    print("OK")

    try:
        print("\n[送出 GET_TIME，board 預期會卡住，直到 IWDG 自動重置]")
        seq = t.next_seq()
        t.send(build_frame(ID_PC, DEVICE_ID, CMD_GET_TIME, seq, b'', 0x01))
        print(f"    已送出，最多等 {RECOVERY_TIMEOUT_S} 秒（正常需要幾秒鐘，不是立刻回應）...")

        raw = t.recv()
        cmd, recv_seq, payload, flags = parse_frame(raw)
        print(f"    收到 CMD=0x{cmd:02X}, payload={payload.hex()}, FLAGS=0x{flags:02X}")

        # IWDG 重置後 board 會重開機、dispatch loop 重新開始；這次再送的
        # GET_TIME 因為 SCL 還沒接回去，預期還是會遇到同樣的 I2C 問題、
        # 回 ERR_I2C_FAILURE——重點不是「這次成功讀到時間」，是「board
        # 真的有回應」，證明它自己重開機、UART 恢復正常了，不需要拔 USB。
        assert cmd == CMD_ERR, f"預期 CMD_ERR(0x{CMD_ERR:02X})，收到 0x{cmd:02X}"
        assert (flags & FLAG_IS_ERROR) != 0, f"FLAG_IS_ERROR 沒有被設定，FLAGS=0x{flags:02X}"
        assert len(payload) == 1 and payload[0] == ERR_I2C_FAILURE, (
            f"預期錯誤碼 ERR_I2C_FAILURE(0x{ERR_I2C_FAILURE:02X})，收到 payload={payload.hex()}"
        )

        print("\n=== 第6階驗收通過：board 卡死後，IWDG 在沒有人拔 USB 的")
        print("    情況下自動重置，UART 恢復回應 ===")

        input("\n測試完成，請把 SCL 線接回去，按 Enter 結束...")

    except RtcTimeoutError:
        print(f"\n*** {RECOVERY_TIMEOUT_S} 秒內都沒有任何回應 ***")
        print("IWDG 似乎沒有正確生效，檢查幾個可能：")
        print("  1. stm32g4xx_hal_conf.h 的 #define HAL_IWDG_MODULE_ENABLED")
        print("     是否真的取消註解了——這個檔案沒辦法幫你自動改，需要手動確認")
        print("  2. main.c / rtc_driver.c 的新版有沒有真的 Build 成功並燒錄進板子")
        print("  3. 確認拔的真的是 SCL，不是 SDA（SDA 斷開不會卡死 main loop，")
        print("     這支測試就沒有機會驗證到 IWDG，會一直等到逾時）")
        sys.exit(1)
    except (CrcError, FrameError) as e:
        print(f"\n*** 通訊失敗: {e} ***")
        sys.exit(1)
    finally:
        t.close()


if __name__ == "__main__":
    main()