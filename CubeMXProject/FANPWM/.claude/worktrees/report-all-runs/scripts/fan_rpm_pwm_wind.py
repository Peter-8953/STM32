# -*- coding: utf-8 -*-
"""
把「MCU CSV（tick,duty,rpm,...）」與「風速計 log（Date/Time/windspeed）」合併，
分析 PWM duty / RPM / 風速三者的對應關係。

使用方式：
1. 套用 duty 階梯（手動 D 指令，或自動 fan_sweep），同時開啟 MCU 的 CSV log（送 "V"）。
2. 風速計記錄同期間的 Date/Time/Value。
3. 設定下面的 MCU_START_TIME：MCU 第一筆 CSV (tick ≈ 0) 對應的風速計/電腦時間。
   不必完全精確，因為本腳本用 nearest-merge，每個風速計資料列會配對最近的 MCU 資料。
4. 執行本腳本，輸出 merged.csv 與 summary.csv。
"""

from pathlib import Path
import os
ROOT = Path(__file__).resolve().parents[1]
import datetime as dt
import pandas as pd

# ============================== 使用者設定 ==============================
MCU_START_TIME = None  # 例："2025-10-30 18:10:00"；None = 用 MCU tick 直接當秒數（僅供除錯）
MCU_FILE = "mcu.csv"     # 由終端機存下 MCU 的 CSV log
WIND_FILE = ROOT / "data" / "real12START_3CM.xls"  # 風速計 log（.xls/.xlsx/.csv/.txt）
OUT_DIR = ROOT / "data" / "output"
# ====================================================================

os.makedirs(OUT_DIR, exist_ok=True)

# ---- 讀 MCU CSV ----
# 可接受：
# 1. capture_mcu_csv.py 產生的檔案：含 pc_time + 10 個 MCU 欄位
# 2. 純 MCU CSV：沒有 header/pc_time，只有 10 個 MCU 欄位
mcu_cols = ["tick", "target_rpm", "rpm", "duty", "ff", "integral",
            "ccr", "per", "rpm_min", "rpm_max"]

try:
    mcu = pd.read_csv(MCU_FILE)
except Exception:
    mcu = None

if mcu is not None and "pc_time" in mcu.columns:
    # 直接用電腦時間對齊風速計 log
    mcu["timestamp"] = pd.to_datetime(mcu["pc_time"], errors="coerce")
    if not all(c in mcu.columns for c in mcu_cols):
        raise SystemExit("MCU CSV 缺少必要欄位，請確認是 capture_mcu_csv.py 的輸出")
else:
    mcu = pd.read_csv(MCU_FILE, header=None, names=mcu_cols, comment="#")
    mcu["tick"] = pd.to_numeric(mcu["tick"], errors="coerce")
    mcu = mcu.dropna(subset=["tick"]).sort_values("tick").reset_index(drop=True)
    if MCU_START_TIME is None:
        mcu["timestamp"] = pd.to_datetime(mcu["tick"], unit="ms")
    else:
        base = pd.to_datetime(MCU_START_TIME)
        mcu["timestamp"] = base + pd.to_timedelta(mcu["tick"], unit="ms")

# ---- 讀風速計 log ----
def _detect_excel_engine(path):
    with open(path, "rb") as f:
        head = f.read(8)
    if head[:4] == b"PK\x03\x04":
        return "openpyxl"
    if head == b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1":
        return "xlrd"
    return None


def read_wind(path):
    engine = _detect_excel_engine(path)
    if engine:
        df = pd.read_excel(path, engine=engine)
    else:
        df = None
        for enc in ("utf-8-sig", "utf-8", "cp950", "cp932", "gb18030"):
            try:
                df = pd.read_csv(path, sep="\t", engine="python", encoding=enc)
                break
            except UnicodeError:
                continue
        if df is None:
            raise SystemExit("無法讀取風速計 log")
    df.columns = [str(c).strip() for c in df.columns]
    if "Function" in df.columns:
        df = df[df["Function"].astype(str).str.strip() == "VEL"].copy()
    df["windspeed"] = pd.to_numeric(
        df["Value"].astype(str).str.strip().str.replace("m/s", "", regex=False),
        errors="coerce")
    df = df.dropna(subset=["windspeed"])

    def _to_td(v):
        if isinstance(v, (dt.datetime, dt.time)):
            t = v.time() if isinstance(v, dt.datetime) else v
            return pd.Timedelta(hours=t.hour, minutes=t.minute,
                                seconds=t.second, microseconds=t.microsecond)
        if isinstance(v, (int, float)) and not pd.isna(v):
            return pd.to_timedelta(float(v), unit="D")
        try:
            return pd.to_timedelta(str(v).strip())
        except Exception:
            return pd.NaT

    date_part = pd.to_datetime(df["Date"], errors="coerce").dt.normalize()
    df["timestamp"] = date_part + df["Time"].map(_to_td)
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return df[["timestamp", "windspeed"]]


wind = read_wind(WIND_FILE)

# ---- nearest-time merge：每個風速計資料列配對最近的 MCU 資料 ----
merged = pd.merge_asof(
    wind.sort_values("timestamp"),
    mcu.sort_values("timestamp"),
    on="timestamp",
    direction="nearest",
    tolerance=pd.Timedelta(seconds=2),
)
merged = merged.dropna(subset=["duty", "rpm"]).reset_index(drop=True)
merged.to_csv(os.path.join(OUT_DIR, "rpm_pwm_wind_merged.csv"), index=False)

# ---- 按 duty 聚合 ----
summary = (
    merged.groupby("duty")
    .agg(
        mean_rpm=("rpm", "mean"),
        std_rpm=("rpm", "std"),
        mean_target_rpm=("target_rpm", "mean"),
        mean_windspeed=("windspeed", "mean"),
        std_windspeed=("windspeed", "std"),
        mean_ccr=("ccr", "mean"),
        mean_per=("per", "mean"),
        n=("rpm", "count"),
    )
    .reset_index()
    .sort_values("duty")
)
summary["pwm_percent"] = summary["mean_ccr"] / summary["mean_per"] * 100.0
summary.to_csv(os.path.join(OUT_DIR, "rpm_pwm_wind_summary.csv"), index=False)

print("===== PWM duty / RPM / 風速 對照表 =====")
print(summary.to_string(index=False, float_format="{:.3f}".format))
print(f"\n輸出：{os.path.abspath(OUT_DIR)}")
print("  rpm_pwm_wind_merged.csv   (逐筆合併資料)")
print("  rpm_pwm_wind_summary.csv (按 duty 聚合)")
