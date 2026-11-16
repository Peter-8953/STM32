# -*- coding: utf-8 -*-
"""
用 PC 時間 + MCU CSV 一起記錄。
執行方式：python capture_mcu_csv.py COM4
在另一個終端機/按鈕个月内送 "V" 開啟 CSV 模式。
本腳本會把「-looking like CSV 的行（以數字開頭）」加上 PC 時間戳存成 mcu_capture.csv，
其餘 MCU 文字訊息只印在畫面，不寫入 CSV。
"""

from pathlib import Path
import os
ROOT = Path(__file__).resolve().parents[1]
import re
import sys
import datetime
import serial

PORT = sys.argv[1] if len(sys.argv) > 1 else "COM4"
BAUD = 115200
OUT = str(ROOT / "mcu_capture.csv")

ser = serial.Serial(PORT, BAUD, timeout=1.0)
file_new = not os.path.exists(OUT) or os.path.getsize(OUT) == 0
with open(OUT, "a", encoding="utf-8", newline="") as f:
    if file_new:
        f.write("pc_time,tick,target_rpm,rpm,duty,ff,integral,ccr,per,rpm_min,rpm_max\n")
    print(f"Recording {PORT} -> {OUT}. Press Ctrl+C to stop.")
    try:
        while True:
            raw = ser.readline()
            if not raw:
                continue
            line = raw.decode("utf-8", errors="ignore").strip()
            if not line:
                continue
            if re.match(r"^\d+,", line):
                pc_time = datetime.datetime.now().isoformat()
                f.write(f"{pc_time},{line}\n")
                f.flush()
                print(f"{pc_time}  {line}")
            else:
                print(line)
    except KeyboardInterrupt:
        pass
    finally:
        ser.close()
        print(f"\nSaved: {os.path.abspath(OUT)}")
