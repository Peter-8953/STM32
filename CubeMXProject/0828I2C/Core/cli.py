"""cli.py: 主迴圈。內建指令 help / devices / use / reset / exit，
其他（temp/time/sync）查 COMMANDS 字典（對應文件 6.2 節，並擴充
支援多台 Arduino）。

Port 解析邏輯：
    - 如果環境變數 RTC_PORT 有設定 -> 只連那一個 port（單裝置模式，
      跟原本文件的行為一致）
    - 沒設定 -> 呼叫 auto_detect_all()，掃描並連上「所有」有回應的
      Arduino（多裝置模式）

多裝置時，指令一律作用在目前「選定」的裝置上（預設是第一個找到的），
用 `use <device_id>` 切換，`devices` 查看目前連上哪些。
"""

import contextlib
import os

from dotenv import load_dotenv

from rtc3231 import DS3231
from rtc3231.detect import auto_detect_all
from db.database import get_connection
from db.models import create_tables
from db import repository
from commands import COMMANDS
from runner import LoopRunner, run_once

load_dotenv()   # 讀取 .env（若存在），不會覆蓋已經手動設定好的環境變數


def print_help():
    print("  help       顯示這個說明")
    print("  devices    列出目前連上的所有裝置")
    print("  use <id>   切換目前操作的裝置（例如 use 0x02 或 use 2）")
    print("  reset      停止目前動作")
    print("  exit       離開程式")
    for name, cmd in COMMANDS.items():
        print(f"  {name:<10} {cmd['desc']}")


def connect_devices() -> dict:
    """建立所有裝置的連線，回傳 {device_id: DS3231 實例}。

    RTC_PORT 有設定時只連那一個 port；沒設定時掃描所有回應的 port。

    如果兩個 port 回應同一個 device_id（例如兩片 Arduino 燒錄時忘記
    改 MY_DEVICE_ID 常數，韌體裡都寫死同一個值），這裡會印出明確警告
    並主動關閉後面重複的那個連線——而不是讓它被字典悄悄覆蓋、變成
    沒人管、也沒被關閉的孤兒連線（這是實測時真的踩到的坑）。
    """
    port = os.environ.get("RTC_PORT")
    devices = {}

    if port:
        print(f"正在連接 {port} ...")
        rtc = DS3231(port=port)
        devices[rtc.device_id] = rtc
    else:
        print("正在掃描所有序列埠（auto_detect_all）...")
        ports = auto_detect_all()
        if not ports:
            raise RuntimeError("找不到任何 Arduino，請確認韌體已燒錄且 USB 已連接")
        for p in ports:
            print(f"  連接 {p} ...")
            rtc = DS3231(port=p)

            if rtc.device_id in devices:
                existing_port = devices[rtc.device_id]._transport._serial.port
                print(
                    f"    警告：{p} 的 device_id={rtc.device_id:#04x} "
                    f"跟已連接的 {existing_port} 重複！"
                )
                print(
                    f"    這台 Arduino 的韌體需要修改 main.c 的 "
                    f"MY_DEVICE_ID 常數並重新燒錄成不同的值，才能同時使用。"
                )
                print(f"    （已關閉 {p} 這個重複的連線，避免佔用序列埠）")
                rtc._transport.close()   # 避免連線洩漏：不能就這樣被字典覆蓋掉
                continue

            devices[rtc.device_id] = rtc

    return devices


def print_devices(devices: dict, active_id: int):
    for device_id, rtc in devices.items():
        marker = "*" if device_id == active_id else " "
        print(f"  {marker} device_id={device_id:#04x}  port={rtc._transport._serial.port}")


def main():
    with contextlib.ExitStack() as stack:
        devices = connect_devices()
        # 確保程式結束時，不管幾台裝置都會被正確關閉
        for rtc in devices.values():
            stack.enter_context(rtc)

        active_id = next(iter(devices))   # 預設選第一個找到的裝置

        print(f"已連接 {len(devices)} 台裝置：")
        print_devices(devices, active_id)

        db = get_connection()
        stack.callback(db.close)

        # 每次啟動都先確保資料庫結構是最新的（2026-08-23 新增）：
        # create_tables() 內部全部是 IF NOT EXISTS / 條件式 migration，
        # 設計成可以放心重複執行——資料庫已經是最新結構時這裡形同
        # no-op，不會動到任何既有資料；只有在 schema 真的落後時
        # （例如剛換上新版 db/models.py，但資料庫還沒套用過 migration）
        # 才會實際做事。這樣可以避免「換了程式碼但忘記手動跑 migration」
        # 導致 INSERT 時噴 "column does not exist" 這類錯誤。
        create_tables(db)

        for device_id, rtc in devices.items():
            repository.upsert_device(
                db,
                device_id=device_id,
                name=f"Arduino#{device_id:#04x}",
                port=rtc._transport._serial.port,
            )

        runner = LoopRunner()
        stack.callback(lambda: runner.stop() if runner.is_running() else None)

        print_help()

        while True:
            cmd_input = input("\n> ").strip()

            if cmd_input == "":
                continue

            elif cmd_input == "help":
                print_help()

            elif cmd_input == "devices":
                print_devices(devices, active_id)

            elif cmd_input.startswith("use "):
                arg = cmd_input[len("use "):].strip()
                try:
                    target_id = int(arg, 0)   # 支援 "0x02" 或 "2"
                except ValueError:
                    print(f"無法解析裝置 ID：{arg}")
                    continue
                if target_id not in devices:
                    print(f"沒有連接 device_id={target_id:#04x} 這台裝置，輸入 devices 查看目前連上哪些")
                    continue
                if runner.is_running():
                    runner.stop()
                    print("（已先停止前一個動作）")
                active_id = target_id
                print(f"已切換到 device_id={active_id:#04x}")

            elif cmd_input == "reset":
                if runner.is_running():
                    runner.stop()
                    print("已停止")
                else:
                    print("目前沒有在執行中的動作")

            elif cmd_input == "exit":
                if runner.is_running():
                    runner.stop()
                print("再見")
                break

            elif cmd_input in COMMANDS:
                cmd = COMMANDS[cmd_input]
                active_rtc = devices[active_id]

                if runner.is_running():
                    runner.stop()   # 換指令前先停掉前一個，避免搶同一個 transport

                if cmd.get("mode", "loop") == "once":
                    run_once(cmd, db, active_rtc, reconnect_fn=active_rtc.reconnect)
                else:
                    runner.start(cmd, db, active_rtc, reconnect_fn=active_rtc.reconnect)

            else:
                print(f"未知指令：{cmd_input}，輸入 help 查看可用指令")


if __name__ == "__main__":
    main()