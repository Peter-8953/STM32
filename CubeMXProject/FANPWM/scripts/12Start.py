# -*- coding: utf-8 -*-
"""
風扇 PWM Duty vs 風速 -- 上升/下降趨勢、遲滯、線性度分析

量測協定: 依 UP_SEQ 的順序,每 STEP_SEC 秒換一階往上(預設 0、12、20、30、...、100),到 100% 後停兩階
          (第一階算上升、第二階算下降),再依 DOWN_SEQ 往下(100、90、...、20、12、0),回到 0%(0% 只停一階)後重複下一輪。
          階梯不必等距(例如 0% 之後先走 12%,再走 20%、30%...):照實際順序填進 UP_SEQ / DOWN_SEQ 即可。
          (若 100% 只停一階,把下面的 DOWN_SEQ 改成從 90 開始:下降的 100% 會借用上升的 100%。)

風速計的紀錄裡沒有 PWM 欄位,「這筆資料是幾 %」是推出來的,有兩種推法:
  detect : 從風速本身找「台階跳變」的位置當邊界,再用已知協定(UP_SEQ / DOWN_SEQ 的 duty 順序)
           比對各階平均風速的高低,決定每階對應幾 %。不依賴 START_TIME,也不怕時鐘漂移。
  time   : 從 START_TIME 起每 STEP_SEC 秒一格(固定格子)。
兩種方法一律都會跑,SEGMENT_MODE 決定採用哪一個,兩者不一致時會印出警告。

有「死區」的風扇(例如要到 12% 或 20% 才起轉):低於起轉 duty 的台階風速 ~ 0,
階與階之間沒有風速跳變可偵測。把 FAN_START_DUTY 設成風扇開始轉的 PWM 即可:程式會從第一個「起轉」的跳變往前、
從「停轉」的跳變往後,依 STEP_SEC 補出沒風的台階,duty 標籤才不會錯位。
風扇 0% 就在轉(舊風扇)時設成 0。
  - 階梯 0、12、20、30、...、100,12% 起轉   -> FAN_START_DUTY = 12(只有 0% 沒風)
  - 階梯每 10% 一階,20% 起轉(JIESAMMY)     -> FAN_START_DUTY = 20(0%、10% 沒風)
  - 階梯每 10% 一階,但風扇 12% 起轉          -> 填 12 或 20 結果相同(10% 那階還沒風、20% 才有風)
量測只在你設定的階梯上取樣,看不出兩階之間確切是哪一點起轉。

需要:pip install pandas numpy matplotlib openpyxl xlrd
      (.xls 舊格式要 xlrd;.xlsx 要 openpyxl)
"""

import os
import sys
import subprocess
import datetime as dt
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# ============================== 使用者設定 ==============================
DATA_FILE  = "good.xls"                    # .xls / .xlsx / .csv / .txt 皆可;檔名打錯、找不到(或設成 None)時會跳出視窗讓你選檔
SEP        = "\t"                         # 只有文字檔才用到;逗號分隔請改 ","
START_TIME = None                         # duty 第一次設成 0% 的時刻;None = 用 log 第一筆的時間(換檔案時最不容易過期)。detect 模式只拿它和偵測結果比對
STEP_SEC   = 60                           # 每個 duty 停留秒數
SETTLE_SEC = 20                           # 每階前面幾秒不算(風扇變速緩衝)
SEGMENT_MODE = "detect"                   # "detect" = 由資料偵測台階邊界(推薦);"time" = 固定時間格子
DETECT_WIN_SEC = 6                        # 偵測邊界時,跳變點前後各取幾秒比較風速
AUTO_ALIGN = True                         # 自動搜尋最佳 START_TIME(PWM 開始時間常比 log 開頭早或晚)
ALIGN_RANGE_SEC = (-120, 360)             # 搜尋範圍(秒);正值 = PWM 比 START_TIME 更早開始
TAIL_GUARD_SEC = 3                        # 每階結尾前幾秒不算(偵測到的邊界約有 ±2 秒誤差,避免混進下一階的變速期)
MIN_LAST_STEP_SEC = 15                    # 最後一階「穩定後」至少要有幾秒資料才保留(沒錄滿 60 秒也能用)
FAN_START_DUTY = 12                       # 風扇開始轉的 PWM(%,上升時)。階梯 0、12、20、... 而風扇 12% 起轉 -> 12(只有 0% 沒風);JIESAMMY(每 10% 一階、20% 起轉)-> 20;0% 就在轉的舊風扇 -> 0
SPIN_THRESHOLD_MS = 0.3                   # 平均風速低於這個值(m/s)就視為「沒在轉」;風速計在靜止空氣中的雜訊要明顯小於它
OUTLET_DIAMETER_MM = 115.0                 # 風扇出風口直徑 (mm);風量 = 風速 x 出風口面積
FIG_VELOCITY_UNITS = ("m/s", "km/h")      # 風速圖的 (左軸, 右軸) 單位;右軸填 None 就不畫;可選 m/s, km/h, mph, ft/min, ft/s, knots
FIG_FLOW_UNITS = ("CMS", None)            # 風量圖的 (左軸, 右軸) 單位;右軸填 None 就不畫;可選 CMM, CFM, CMS
OUT_DIR    = "fan_output"                 # 圖與 CSV 輸出資料夾(相對路徑 = 放在「這支程式所在的資料夾」底下,不受執行時的工作資料夾影響)
OPEN_OUT_DIR = True                       # 跑完自動打開輸出資料夾
SHOW_PLOTS = True                         # 只跑批次不想彈視窗就改 False

# 線性度要分析的 duty 範圍(風扇常有低 duty 死區、高 duty 飽和,看「中段」是否線性很有用)
# None = 自動:0~100%,再加上「風扇起轉後第一個有風的階」以上的範圍,以及再去掉起轉那一階與最高一階的「中段」
#   (階梯 0、12、20、...、FAN_START_DUTY = 12:0~100%、12~100%、20~90%;每 10% 一階、20% 起轉:0~100%、20~100%、30~90%;FAN_START_DUTY = 0:0~100%、第二階~90%)
# 也可以手動指定,例如 [(0, 100), (20, 100), (30, 90)]
LIN_RANGES = None

# 每一階的 PWM(%),照實際順序填,階梯不必等距:先上升 UP_SEQ,到 100% 後停兩階,再下降 DOWN_SEQ
UP_SEQ    = [0, 12] + list(range(20, 101, 10))     # 0,12,20,30,...,100   (11 階,上升)
DOWN_SEQ  = list(range(100, 19, -10)) + [12, 0]    # 100,90,...,20,12,0   (11 階,下降;100% 停兩階 = 上升一階 + 下降一階)
#           每 10% 一階的協定(例如 JIESAMMY):UP_SEQ = list(range(0, 101, 10));DOWN_SEQ = list(range(100, -1, -10))
#           若 100% 只停一階,DOWN_SEQ 改成從 90 開始(此時下降的 100% 借用上升的 100%),例如 list(range(90, 19, -10)) + [12, 0]
ONE_CYCLE = UP_SEQ + DOWN_SEQ[:-1]        # 21 階 = 21 分鐘一輪(0% 在轉折處只停一階)
# =========================================================================

# ---- 由上面的設定推出來的值(一般不用改)----
STEP_W = int(np.median(np.diff(UP_SEQ)))  # 相鄰兩階 duty 間隔的典型值(階梯不等距時取中位數,例如 0、12、20、30... -> 10);只用來決定長條圖的寬度與「每一階變化量」的換算基準
if FAN_START_DUTY is None:                # 沒填就當 0%(0% 就在轉)
    FAN_START_DUTY = 0
# 風扇「第一個有風的階」:量測只在 UP_SEQ 的階梯上取樣,所以看得到有風的第一階是「>= FAN_START_DUTY 的最小階」
# (階梯 0、12、20、...、12% 起轉 -> 12%;階梯每 10% 一階、12% 起轉 -> 20% 這一階才有風)。線性度的預設範圍、起轉點的檢查都用這一階。
START_STEP = min([d for d in UP_SEQ if d >= FAN_START_DUTY] or [UP_SEQ[-1]])
if LIN_RANGES is None:
    _i0 = UP_SEQ.index(START_STEP)
    LIN_RANGES = ([(UP_SEQ[0], UP_SEQ[-1])]
                  + ([(START_STEP, UP_SEQ[-1])] if START_STEP > UP_SEQ[0] else [])
                  + [(UP_SEQ[min(_i0 + 1, len(UP_SEQ) - 1)], UP_SEQ[-2])])       # 中段:去掉「起轉那一階」與最高的一階

# 相對路徑一律接在程式所在資料夾後面。若改用「目前工作資料夾」,從 VS Code 等工具執行時,
# 工作資料夾常常不是程式所在的位置,輸出就會跑到別處,看起來像是沒有輸出。
_HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
if not os.path.isabs(OUT_DIR):
    OUT_DIR = os.path.join(_HERE, OUT_DIR)
os.makedirs(OUT_DIR, exist_ok=True)

# 中文字型(否則軸標籤會變方框)
plt.rcParams["font.sans-serif"] = [
    "Microsoft JhengHei", "Microsoft YaHei", "PingFang TC", "Noto Sans CJK TC",
    "SimHei", "Arial Unicode MS", "DejaVu Sans",
]
plt.rcParams["axes.unicode_minus"] = False


def eff_duty(d):
    """排定的 duty -> 拿來和風速比對的「有效 duty」:低於起轉 duty 的風扇沒在轉,一律當 0。
    這樣死區的台階(例如 0%、10%)在比對時彼此等價,不會因為「它們排定的 duty 不一樣」去干擾對應;
    FAN_START_DUTY = 0 時原樣不變。"""
    d = np.asarray(d, float)
    return np.where(d >= FAN_START_DUTY, d, 0.0)


def out(name):
    """輸出路徑;若檔案正被別的程式(多半是 Excel)開著,改存成帶時間的新檔名。"""
    path = os.path.join(OUT_DIR, name)
    try:
        with open(path, "ab"):
            pass
    except PermissionError:
        base, ext = os.path.splitext(name)
        path = os.path.join(OUT_DIR, f"{base}_{dt.datetime.now():%H%M%S}{ext}")
        print(f"[warn] {name} 被其他程式開著(多半是 Excel),改存成 {os.path.basename(path)}")
    return path


# ============================ 讀檔 ============================
_ENCODINGS = ("utf-8-sig", "utf-8", "cp950", "cp932", "gb18030", "utf-16", "cp1252")


def _detect_excel_engine(path):
    """看檔頭 magic number,不信副檔名。xlsx=ZIP(PK),xls=OLE2。"""
    with open(path, "rb") as f:
        head = f.read(8)
    if head[:4] == b"PK\x03\x04":
        return "openpyxl"
    if head == b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1":
        return "xlrd"
    return None


def resolve_data_file(path):
    """DATA_FILE 找得到就直接用;沒設定、檔名打錯或找不到時,跳出「選擇檔案」視窗讓你選。
    相對路徑會先找目前工作資料夾,再找這支程式所在的資料夾。"""
    if path:
        here = os.path.dirname(os.path.abspath(globals().get("__file__", "."))) if "__file__" in globals() else os.getcwd()
        for cand in (path, os.path.join(here, path)):
            if os.path.isfile(cand):
                if cand != path:
                    print(f"[info] 在程式所在資料夾找到 {path}")
                return cand
        print(f"[warn] 找不到資料檔:{path}(目前工作資料夾:{os.getcwd()}),請在視窗中選擇檔案")
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()                      # 隱藏 tkinter 預設的空白主視窗
        root.attributes("-topmost", True)    # 讓選檔視窗浮在最上層,不要躲在編輯器後面
        chosen = filedialog.askopenfilename(
            parent=root, title="選擇風速計資料檔",
            filetypes=[("Excel / 文字", "*.xls *.xlsx *.txt *.csv"), ("All", "*.*")])
        root.destroy()
    except Exception as e:                   # 沒有圖形介面(例如遠端、無顯示器的環境)
        raise SystemExit(f"無法開啟選檔視窗({e})。請把 DATA_FILE 改成正確的檔案路徑。")
    if not chosen:                           # 按了「取消」
        raise SystemExit("沒有選擇檔案")
    print(f"[info] 使用選擇的檔案:{chosen}")
    return chosen


def read_log(path, sep):
    engine = _detect_excel_engine(path)
    if engine:
        try:
            df = pd.read_excel(path, engine=engine)
        except ImportError as e:
            raise SystemExit(f"缺少讀 Excel 的套件:pip install {engine}\n({e})")
        print(f"[info] Excel 格式,engine={engine}")
        return df
    for enc in _ENCODINGS:
        try:
            df = pd.read_csv(path, sep=sep, engine="python", encoding=enc)
            print(f"[info] 文字檔,編碼 {enc}")
            return df
        except UnicodeError:
            continue
    raise SystemExit(f"無法判斷 {path} 的編碼")


def _to_timedelta(v):
    """Excel 的時間欄可能是 time / datetime / 一天的小數 / 字串,統一轉成 Timedelta。"""
    if isinstance(v, (dt.datetime, dt.time)):
        t = v.time() if isinstance(v, dt.datetime) else v
        return pd.Timedelta(hours=t.hour, minutes=t.minute,
                            seconds=t.second, microseconds=t.microsecond)
    if isinstance(v, (int, float, np.floating)) and not pd.isna(v):
        return pd.to_timedelta(float(v), unit="D")
    try:
        return pd.to_timedelta(str(v).strip())
    except Exception:
        return pd.NaT


DATA_FILE = resolve_data_file(DATA_FILE)
raw = read_log(DATA_FILE, SEP)
raw.columns = [str(c).strip() for c in raw.columns]

if "Function" in raw.columns:
    raw = raw[raw["Function"].astype(str).str.strip() == "VEL"].copy()

raw["windspeed"] = pd.to_numeric(
    raw["Value"].astype(str).str.strip().str.replace("m/s", "", regex=False),
    errors="coerce",
)
raw = raw.dropna(subset=["windspeed"])
# 溫度、濕度(例如 "24.6°C"、"61.3%RH"):只取數字,不依賴單位符號的編碼;沒有這兩欄就當成缺值
for _col, _name in (("Temperature", "temp_c"), ("Humidity", "rh_pct")):
    raw[_name] = (pd.to_numeric(raw[_col].astype(str).str.extract(r"(-?\d+(?:\.\d+)?)")[0], errors="coerce")
                  if _col in raw.columns else np.nan)

date_part = pd.to_datetime(raw["Date"], errors="coerce").dt.normalize()
raw["timestamp"] = date_part + raw["Time"].map(_to_timedelta)

if raw["timestamp"].isna().all():
    raise SystemExit("Date/Time 全部解析失敗,請檢查欄位內容:\n" + raw.head().to_string())
n_bad = raw["timestamp"].isna().sum()
if n_bad:
    print(f"[warn] {n_bad} 筆 Date/Time 解析失敗,已略過")
raw = raw.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

# ============================ 切段:決定每筆資料屬於哪一階 ============================
cycle_len = len(ONE_CYCLE)
MIN_USABLE_SEC = SETTLE_SEC + MIN_LAST_STEP_SEC     # 一階至少要有這麼長才有可用資料
raw["t_log"] = (raw["timestamp"] - raw["timestamp"].iloc[0]).dt.total_seconds()
LABEL_COLS = ["step_idx", "cycle", "duty", "direction", "sec_in_step", "sec_to_end", "complete"]


def _labels_from_steps(index, step_idx, sec_in_step, complete, sec_to_end=None):
    """第 step_idx 階 -> duty / 方向 / 輪次。
    0% 只停一階:它同時是上一輪下降的終點與這一輪上升的起點,
    第 2 輪以後的這一階歸為「上一輪的 down 0%」(它是從高轉速降下來的,不是從靜止起動)。"""
    step_idx = np.asarray(step_idx, dtype=int)
    pos = step_idx % cycle_len
    cyc = step_idx // cycle_len
    direction = np.where(pos < len(UP_SEQ), "up", "down")
    wrap0 = (pos == 0) & (cyc > 0)
    direction = np.where(wrap0, "down", direction)
    cyc = np.where(wrap0, cyc - 1, cyc)
    return pd.DataFrame({
        "step_idx": step_idx, "cycle": cyc, "duty": np.array(ONE_CYCLE)[pos],
        "direction": direction, "sec_in_step": np.asarray(sec_in_step, float),
        "sec_to_end": (np.full(len(step_idx), np.inf) if sec_to_end is None
                       else np.asarray(sec_to_end, float)),
        "complete": np.asarray(complete, bool),
    }, index=index)


# ---------- 方法 A:固定時間格子 ----------
t0 = pd.to_datetime(START_TIME) if START_TIME else raw["timestamp"].iloc[0]


def auto_align(df, t0):
    """搜尋 START_TIME 偏移:正確對齊時,「排定的 duty」和「實測風速」的相關性最高。
    這同時能解決「差幾秒」和「差整數階(例如 PWM 比 log 早開始 2 分鐘)」兩種錯位。
    (用帶正負號的相關係數:反相的對齊不會被誤認成好對齊)"""
    e_all = (df["timestamp"] - t0).dt.total_seconds().to_numpy()
    ws = df["windspeed"].to_numpy()
    sched = eff_duty(ONE_CYCLE)                           # 死區的台階當 0:不會因為「排定的 duty 比 0% 大」而影響對齊

    def score_at(o):
        e = e_all + o
        m = e >= 0
        if m.sum() < 100:
            return -1.0
        e, w = e[m], ws[m]
        si = (e // STEP_SEC).astype(int)
        keep = (e - si * STEP_SEC) >= SETTLE_SEC
        d, w = sched[si[keep] % len(sched)], w[keep]
        if len(d) < 100 or d.std() == 0 or w.std() == 0:
            return -1.0
        r = np.corrcoef(d, w)[0, 1]
        return r * abs(r)

    offs = np.arange(ALIGN_RANGE_SEC[0], ALIGN_RANGE_SEC[1] + 1, 1.0)
    sc = np.array([score_at(o) for o in offs])
    best = float(np.median(offs[sc >= sc.max() - 5e-4]))
    sc0 = score_at(0.0)
    print(f"[align] 目前 START_TIME 的 R2={sc0:.4f};最佳偏移 {best:+.0f} 秒,R2={sc.max():.4f}")
    if min(abs(best - ALIGN_RANGE_SEC[0]), abs(best - ALIGN_RANGE_SEC[1])) <= 2:
        print("[warn] 最佳偏移碰到搜尋範圍 ALIGN_RANGE_SEC 的邊界,真正的最佳值可能在範圍之外:"
              "START_TIME 可能和這份 log 差很多,建議改成 None(用 log 第一筆時間)或擴大 ALIGN_RANGE_SEC")
    if sc.max() - sc0 > 0.005 and abs(best) >= 1:
        new_t0 = t0 - pd.Timedelta(seconds=best)
        print(f"[align] 採用校正:START_TIME 由 {t0} 改為 {new_t0}"
              f"({'PWM 比 log 更早開始' if best > 0 else 'PWM 比 log 更晚開始'} {abs(best):.0f} 秒)")
        return new_t0
    print("[align] 現有 START_TIME 已足夠好,不調整。")
    return t0


if AUTO_ALIGN:
    t0 = auto_align(raw, t0)


def label_by_time(df, t0):
    e = (df["timestamp"] - t0).dt.total_seconds().to_numpy()
    valid = e >= 0
    step = np.floor(e / STEP_SEC).astype(int)
    sec = e - step * STEP_SEC
    if not valid.any():
        return _labels_from_steps(df.index, np.zeros(len(df), int), sec, valid, STEP_SEC - sec), {}
    last_step = step[valid].max()
    last_cover = e[valid].max() - last_step * STEP_SEC
    keep_last = last_cover >= MIN_USABLE_SEC
    complete = valid & ((step < last_step) | keep_last)
    return (_labels_from_steps(df.index, step, sec, complete, STEP_SEC - sec),
            dict(last_cover=last_cover, keep_last=keep_last))


# ---------- 方法 B:從資料本身偵測台階邊界 ----------
def detect_boundaries(t, x):
    """找風速「跳變」的位置。回傳 (邊界時間[秒,自 log 第一筆起], 是否為補點, 失敗原因)。
    作法:每秒取中位數 -> 比較每一秒前後各 DETECT_WIN_SEC 秒的中位數差 -> 取明顯的局部峰值。
    門檻依資料自己的跳變大小與雜訊決定;若兩個邊界剛好風速相同(漏掉一個),
    且間隔約為 STEP_SEC 的整數倍,就在中間補點。"""
    K = DETECT_WIN_SEC
    n = int(np.ceil(t[-1])) + 1
    if n < 4 * K:
        return None, None, "資料太短"
    sec = np.floor(t).astype(int)
    sr = (pd.Series(x).groupby(sec).median().reindex(range(n))
          .interpolate(limit_direction="both").to_numpy())
    d = np.zeros(n)
    for i in range(3, n - 2):
        ke = min(K, i, n - i)
        d[i] = np.median(sr[i:i + ke]) - np.median(sr[i - ke:i])
    a = np.abs(d)

    sigma = 1.4826 * np.median(np.abs(d - np.median(d)))
    thr0 = max(5 * sigma, 1e-6)
    min_dist = int(STEP_SEC * 0.5)
    taken = np.zeros(n, bool)
    cand = []
    for i in np.argsort(-a):
        if a[i] < thr0:
            break
        if taken[max(0, i - min_dist): i + min_dist + 1].any():
            continue
        taken[i] = True
        cand.append(int(i))
    if len(cand) < 3:
        return None, None, f"只找到 {len(cand)} 個明顯的跳變"
    n_exp = max(1, int(round((t[-1] - t[0]) / STEP_SEC)))
    J = np.median(np.sort(a[cand])[::-1][:n_exp])        # 典型跳變大小
    thr = max(thr0, 0.4 * J)
    cand = sorted(i for i in cand if a[i] >= thr)
    if len(cand) < 3:
        return None, None, f"只找到 {len(cand)} 個明顯的跳變"

    edges = []
    for i in cand:                                       # 取高原中心當邊界時刻
        lo, hi = max(0, i - K), min(n, i + K + 1)
        idx = np.where(a[lo:hi] >= 0.9 * a[i])[0] + lo
        edges.append(float(np.mean(idx)))

    B, filled = [edges[0]], [False]
    for j in range(1, len(edges)):
        g = edges[j] - edges[j - 1]
        m = int(round(g / STEP_SEC))
        if m >= 2 and abs(g - m * STEP_SEC) <= 0.1 * STEP_SEC * m:
            for q in range(1, m):
                B.append(edges[j - 1] + g * q / m)
                filled.append(True)
        B.append(edges[j])
        filled.append(False)
    B, filled = np.array(B), np.array(filled)
    # log 開頭/結尾常有「開機、關機」造成的多餘跳變:它與鄰近邊界的間隔遠小於一階,且落在 log 最前/最後一階內
    while len(B) > 3 and B[1] - B[0] < 0.85 * STEP_SEC and (B[0] - t[0]) < STEP_SEC:
        B, filled = B[1:], filled[1:]
    while len(B) > 3 and B[-1] - B[-2] < 0.85 * STEP_SEC and (t[-1] - B[-1]) < STEP_SEC:
        B, filled = B[:-1], filled[:-1]
    sp = np.diff(B)
    if sp.min() < 0.85 * STEP_SEC or sp.max() > 1.15 * STEP_SEC:
        return None, None, (f"邊界間隔不像 ~{STEP_SEC} 秒一階"
                            f"(最短 {sp.min():.0f}、最長 {sp.max():.0f} 秒)")
    return B, filled, None


def label_by_detection(df):
    t = df["t_log"].to_numpy()
    x = df["windspeed"].to_numpy()
    B, filled, why = detect_boundaries(t, x)
    if B is None:
        return None, why
    t_end = t[-1]

    def level(a, b):                                     # [a, b) 內的中位風速;樣本太少回傳 nan
        m = (t >= a) & (t < b)
        return float(np.median(x[m])) if m.sum() >= 8 else np.nan

    # 風扇有死區(例如 20% 才起轉:0%、10% 沒風;12% 起轉、階梯 0、12、20...:只有 0% 沒風)時,沒風的階與階之間沒有跳變可偵測,所以:
    #   開頭 -- 第一個邊界是「起轉」(之前沒風、之後有風)時,往前依 STEP_SEC 補出沒風的台階;
    #   結尾 -- 最後一個邊界是「停轉」(之前有風、之後沒風)時,往後依 STEP_SEC 補出沒風的台階。
    # 補出來的台階等「duty 對應」決定後才確定留不留(見下方),因為 log 開頭、結尾也可能只是
    # PWM 開始前/結束後的空檔(同樣沒風),那不屬於任何一階。
    n_dead_up = sum(d < FAN_START_DUTY for d in UP_SEQ)    # 上升時還沒起轉的階數(JIESAMMY:0%、10% = 2)
    n_dead_dn = sum(d < FAN_START_DUTY for d in DOWN_SEQ)  # 下降時低於起轉 duty 的階數(10%、0% = 2)
    # 「之前(之後)幾乎沒風」= 低於 SPIN_THRESHOLD_MS,或不到另一側風速的 3 成:風扇剛起轉的那一階風速可能很低(例如 12% 只有 0.35 m/s),
    # 它與 0% 之間的跳變小於「典型跳變 x 0.4」而偵測不到,真正偵測到的第一個(最後一個)邊界是它與下一階(上一階)之間的跳變
    lb0 = level(B[0] - 20, B[0] - 3)
    la0 = level(B[0] + SETTLE_SEC, B[0] + STEP_SEC - TAIL_GUARD_SEC)
    startup = bool(la0 >= SPIN_THRESHOLD_MS and lb0 < max(SPIN_THRESHOLD_MS, 0.3 * la0))
    lbe = level(B[-1] - 20, B[-1] - 3)
    lae = level(B[-1] + SETTLE_SEC, min(B[-1] + STEP_SEC - TAIL_GUARD_SEC, t_end + 1.0))
    stopping = bool(lbe >= SPIN_THRESHOLD_MS and lae < max(SPIN_THRESHOLD_MS, 0.3 * lbe))

    lead = []                                            # 開頭補出來的階 (start, end),由近到遠找,多給 1 階餘裕
    for q in range(1, ((n_dead_up + 1) if startup else 1) + 1):
        s_, e_ = B[0] - q * STEP_SEC, B[0] - (q - 1) * STEP_SEC
        if e_ - max(s_, t[0]) < MIN_USABLE_SEC:          # log 沒涵蓋到、或涵蓋太短,更遠的也不會有
            break
        lead.append((s_, e_))
    lead.reverse()
    trail = []                                           # 結尾的階
    if stopping:
        for k in range(n_dead_dn + 1):
            s_, e_ = B[-1] + k * STEP_SEC, B[-1] + (k + 1) * STEP_SEC
            if min(e_, t_end) - s_ < MIN_USABLE_SEC:
                break
            trail.append((s_, e_ if e_ <= t_end else t_end + 1e-6))
    elif t_end - B[-1] >= MIN_USABLE_SEC:                # 結尾殘段太短就丟掉
        trail.append((B[-1], t_end + 1e-6))
    starts = np.array([s_ for s_, _ in lead] + list(B[:-1]) + [s_ for s_, _ in trail])
    ends = np.array([e_ for _, e_ in lead] + list(B[1:]) + [e_ for _, e_ in trail])
    M = len(starts)
    if M < 6:
        return None, f"可用的台階只有 {M} 階,不足以判斷對應的 duty"
    n_in = len(B) - 1                                    # 夾在兩個邊界之間的階數
    opt_lead = np.zeros(M, bool)                         # 「補出來、可能要剔除」的死區台階
    opt_trail = np.zeros(M, bool)
    if startup:
        opt_lead[:len(lead)] = True
    if stopping:
        opt_trail[len(lead) + n_in:] = True

    lv = np.full(M, np.nan)                              # 每階穩定期的平均風速
    for j in range(M):
        m = (t >= starts[j] + SETTLE_SEC) & (t < ends[j] - (TAIL_GUARD_SEC if ends[j] <= t_end else 0))
        if m.sum() >= 10:
            lv[j] = x[m].mean()
    ok = ~np.isnan(lv)

    # 決定第一階對應協定的第幾階:試所有起點相位,取「協定 duty 與各階風速」相關最高者
    # (協定 duty 用 eff_duty:死區的台階都當 0,彼此不分高下,對應主要靠有風的階與最高點決定)
    def phase_scores(T):
        L = len(T)
        out_ = np.full(L, -1.0)
        for ph_ in range(L):
            dd = T[(np.arange(M) + ph_) % L][ok]
            if dd.std() > 0 and lv[ok].std() > 0:
                r_ = np.corrcoef(dd, lv[ok])[0, 1]
                out_[ph_] = r_ * abs(r_)
        return out_

    sc = phase_scores(eff_duty(ONE_CYCLE))
    phase = int(np.argmax(sc))
    srt = np.sort(sc)[::-1]
    # 另一種常見協定(100% 只停一階 <-> 停兩階)擬合得比目前設定更好嗎?若是,多半是 DOWN_SEQ 設錯
    peak = UP_SEQ[-1]
    down_once = [d for d in DOWN_SEQ if d != peak]
    alt_down = down_once if peak in DOWN_SEQ else [peak] + down_once
    alt = dict(name="100% 只停一階" if peak in DOWN_SEQ else "100% 停兩階",
               r2=float(phase_scores(eff_duty(UP_SEQ + alt_down[:-1])).max()))
    if srt[0] < 0.7:
        hint = (f";資料比較像「{alt['name']}」的協定(R2={alt['r2']:.2f}),請檢查 DOWN_SEQ"
                if alt["r2"] - srt[0] > 0.01 else "")
        return None, f"各階風速與協定的 duty 序列對不上(最佳 R2 只有 {srt[0]:.2f}){hint}"

    # 剔除「補出來、卻不屬於這一輪」的死區台階:
    #   開頭 -- 不可跑到第一個有風的階所在那一輪的起點(0%)之前(多半是 PWM 開始前的空檔);
    #   結尾 -- 不可超過那一輪結束的 0%(再往後是下一輪的 10%,但那一輪根本沒開始)。
    step_no = np.arange(M) + phase
    keep = np.ones(M, bool)
    if opt_lead.any():
        j1 = int(np.argmax(~opt_lead))                   # 第一個夾在兩個邊界之間的階(起轉後第一個有風的階)
        keep &= ~(opt_lead & (step_no < step_no[j1] // cycle_len * cycle_len))
    if opt_trail.any():
        j2 = M - 1 - int(np.argmax(~opt_trail[::-1]))    # 最後一個夾在兩個邊界之間的階(停轉前最後一個有風的階)
        keep &= ~(opt_trail & (step_no > step_no[j2] // cycle_len * cycle_len + cycle_len))
    n_drop_seg = int((~keep).sum())
    if n_drop_seg:
        phase = (phase + int(np.argmax(keep))) % cycle_len   # 前面被剔掉幾階,第一階就往後挪幾階(整輪對齊時 = 0)
        starts, ends, lv, opt_lead, opt_trail = (a[keep] for a in (starts, ends, lv, opt_lead, opt_trail))
        M = len(starts)
    n_lead_added, n_trail_added = int(opt_lead.sum()), int(opt_trail.sum())

    idx = np.searchsorted(starts, t, side="right") - 1
    valid = (idx >= 0) & (t < ends[-1])
    idc = np.clip(idx, 0, M - 1)
    to_end = ends[idc] - t
    to_end[ends[idc] > t_end] = np.inf                  # 只有「結尾在 log 末端」的殘段才沒有下一個邊界;結尾是真實邊界的階仍要套用結尾保護
    lab = _labels_from_steps(df.index, idc + phase, t - starts[idc], valid, to_end)

    tab = _labels_from_steps(np.arange(M), np.arange(M) + phase, np.zeros(M), np.ones(M, bool))
    tab.insert(0, "seg", np.arange(M))
    tab["start_sec"] = starts
    tab["end_sec"] = np.minimum(ends, t_end)
    tab["start_time"] = df["timestamp"].iloc[0] + pd.to_timedelta(starts, unit="s")
    tab["mean_windspeed_settled"] = lv
    tab = tab.drop(columns=["step_idx", "sec_in_step", "complete"])
    return lab, dict(B=B, filled=filled, phase=phase, r2=srt[0], r2_second=srt[1], table=tab, alt=alt,
                     startup=startup, stopping=stopping, n_lead=n_lead_added, n_trail=n_trail_added,
                     n_dropped=n_drop_seg, lead_gap=float(B[0] - t[0]), n_dead_up=n_dead_up)


def compare_modes(df, lt, ld, info, t0):
    """把「資料偵測的邊界」和「固定時間格子」比對,不一致時警告。"""
    B, filled = info["B"], info["filled"]
    Bt = B[~filled]
    sp = np.diff(B)
    print(f"[detect] 偵測到 {len(Bt)} 個台階邊界"
          + (f"(另補 {filled.sum()} 個)" if filled.any() else "")
          + f",階長平均 {sp.mean():.1f} s(範圍 {sp.min():.1f}-{sp.max():.1f} s)")
    ph = info["phase"]
    print(f"[detect] 第一個納入的台階 = 協定第 {ph} 階({ONE_CYCLE[ph]}%);"
          f"duty 序列與風速 R2={info['r2']:.4f}(次佳 {info['r2_second']:.4f})")
    if info["r2"] - info["r2_second"] < 0.02:
        print("[warn] 最佳與次佳的對應差很小,duty 對應可能不唯一(記錄太短或缺少最高/最低階)")
    if info["n_lead"] or info["n_trail"]:
        print(f"[detect] 風扇有死區(FAN_START_DUTY={FAN_START_DUTY}%,沒風的台階之間沒有跳變):"
              f"開頭補 {info['n_lead']} 階、結尾補 {info['n_trail']} 階"
              + (f"(另剔除 {info['n_dropped']} 階 PWM 開始前/結束後的空檔)" if info["n_dropped"] else ""))
    k_imp = int((info["lead_gap"] + 5) // STEP_SEC)      # 第一個跳變之前,約有幾階沒風(假設 log 在 PWM 開始前不久才開始錄)
    if info["startup"] and k_imp > info["n_dead_up"] + 1:
        _imp = UP_SEQ[min(k_imp, len(UP_SEQ) - 1)]       # 前面 k_imp 階都沒風 -> 風扇是從 UP_SEQ 的第 k_imp 階(從 0 算起)才起轉
        print(f"[warn] 第一個風速跳變前,log 開頭有約 {info['lead_gap']:.0f} 秒沒風(約 {k_imp} 階),"
              f"比 FAN_START_DUTY={FAN_START_DUTY}% 預期的 {info['n_dead_up']} 階多。"
              f"若風扇其實要到 {_imp}% 才起轉,請把 FAN_START_DUTY 改成 {_imp};"
              "若只是 PWM 開始前 log 先錄了一段空檔,可以忽略。")
    alt = info.get("alt")
    if alt and alt["r2"] - info["r2"] > 0.01:
        print(f"[warn] 資料比較像「{alt['name']}」的協定(R2={alt['r2']:.4f}),目前設定的 R2 只有 {info['r2']:.4f}:"
              "請檢查 DOWN_SEQ / ONE_CYCLE 是否和實際量測一致,否則下降端的 duty 標籤會整排錯位")

    g0 = (t0 - df["timestamp"].iloc[0]).total_seconds()  # 時間格子起點(自 log 第一筆起算)
    k = np.round((Bt - Bt[0]) / STEP_SEC)
    rel = Bt - (Bt[0] + k * STEP_SEC)                    # 相對第一個邊界的累積偏離
    drift = np.polyfit(k, rel, 1)[0] if len(Bt) >= 4 else 0.0
    const = ((Bt[0] - g0 + STEP_SEC / 2) % STEP_SEC) - STEP_SEC / 2
    off = const + rel                                    # 各邊界:實際 - 格子
    print(f"[compare] 實際切換時刻比時間格子{'晚' if const >= 0 else '早'} {abs(const):.1f} s;"
          f"時鐘漂移 {drift:+.3f} s/階(整段共 {drift * (k[-1] - k[0]):+.1f} s)")
    if off.min() < -2.0 or off.max() > SETTLE_SEC - 3:
        print(f"[warn] 時間格子與實際切換的差距範圍 {off.min():+.1f} ~ {off.max():+.1f} s,"
              f"超出 SETTLE_SEC={SETTLE_SEC} 能涵蓋的範圍:時間格子會把相鄰階的資料混進來,"
              "建議使用 SEGMENT_MODE='detect'")

    m = (lt["complete"] & ld["complete"]
         & (lt["sec_in_step"] >= SETTLE_SEC) & (ld["sec_in_step"] >= SETTLE_SEC)
         & (lt["sec_to_end"] >= TAIL_GUARD_SEC) & (ld["sec_to_end"] >= TAIL_GUARD_SEC)).to_numpy()
    if m.sum():
        same = ((lt["duty"] == ld["duty"]) & (lt["direction"] == ld["direction"])).to_numpy()[m]
        ag = same.mean() * 100
        print(f"[compare] 兩種切法都認定為穩定期的 {m.sum()} 筆中,duty/方向標籤一致率 {ag:.1f}%")
        if ag < 99:
            rows = np.flatnonzero(m)[~same]
            lab_of = lambda L_: (L_["direction"].to_numpy()[rows] + " "
                                 + L_["duty"].to_numpy()[rows].astype(int).astype(str) + "%")
            where = (pd.DataFrame({"偵測標籤": lab_of(ld), "格子標籤": lab_of(lt), "t": df["t_log"].to_numpy()[rows]})
                     .groupby(["偵測標籤", "格子標籤"]).agg(筆數=("t", "size"), 起始秒=("t", "min"), 結束秒=("t", "max"))
                     .sort_values("筆數", ascending=False).head(4))
            print("[compare] 不一致的樣本集中在(時間為自 log 第一筆起算的秒數):")
            print(where.to_string(float_format="{:.0f}".format))
            print("[warn] 兩種切法的標籤不一致:時間格子可能漂移、START_TIME 差整數階,"
                  f"或實際協定不是 {cycle_len} 階一輪。請對照 fig0 的紅色(偵測)與灰色(格子)刻度。")


lab_t, info_t = label_by_time(raw, t0)
lab_d, info_d = label_by_detection(raw)
mode_used, det_B = "time", None
if lab_d is None:
    print(f"[detect] 資料偵測切段失敗:{info_d}")
    if SEGMENT_MODE == "detect":
        print("[warn] 退回「固定時間格子」切段")
else:
    det_B = info_d["B"]
    compare_modes(raw, lab_t, lab_d, info_d, t0)
    if SEGMENT_MODE == "detect":
        mode_used = "detect"

lab = lab_d if mode_used == "detect" else lab_t
for c in LABEL_COLS:
    raw[c] = lab[c].to_numpy()
print(f"[mode] 採用「{'資料偵測' if mode_used == 'detect' else '固定時間格子'}」切段")
if mode_used == "time" and info_t and info_t["keep_last"] and info_t["last_cover"] < STEP_SEC - 1:
    print(f"[info] 最後一階只錄了 {info_t['last_cover']:.0f}/{STEP_SEC} 秒,仍保留(穩定後資料較少)")
if info_d and isinstance(info_d, dict):
    info_d["table"].to_csv(out("step_table.csv"), index=False)

n_steps_used = raw.loc[raw["complete"], "step_idx"].nunique()
print(f"資料共 {len(raw)} 筆,涵蓋 {raw['t_log'].max()/60:.1f} 分鐘;"
      f"納入統計的台階 {n_steps_used} 階(約 {n_steps_used / cycle_len:.2f} 輪)")
n_drop = int((~raw["complete"]).sum())
if n_drop:
    print(f"[info] {n_drop} 筆屬於開頭/結尾不完整的階,未納入統計")

settled = raw[(raw["sec_in_step"] >= SETTLE_SEC) & (raw["sec_to_end"] >= TAIL_GUARD_SEC) & raw["complete"]]

summary = (
    settled.groupby(["cycle", "direction", "duty"])["windspeed"]
    .agg(mean_windspeed="mean", std_windspeed="std", n="count")
    .reset_index()
    .sort_values(["cycle", "direction", "duty"])
)
# 峰值(100%)停幾階,由 UP_SEQ / DOWN_SEQ 決定:
#  - DOWN_SEQ 含 100%(停兩階):下降的 100% 是獨立量測,直接使用。
#  - DOWN_SEQ 不含 100%(只停一階):下降曲線沒有獨立量測的 100%,借用同一輪上升的 100%
#    (同一個物理狀態),並標記 borrowed=True,方便在需要「真正獨立量測」的統計
#    (噪訊排行、跨輪一致性)中排除,避免同一筆資料算兩次。
PEAK_DUTY = UP_SEQ[-1]
PEAK_SHARED = PEAK_DUTY not in DOWN_SEQ
summary["borrowed"] = False
if PEAK_SHARED:
    peak = summary[(summary["direction"] == "up") & (summary["duty"] == PEAK_DUTY)].copy()
    if len(peak):
        peak["direction"] = "down"
        peak["borrowed"] = True
        summary = (pd.concat([summary, peak], ignore_index=True)
                   .sort_values(["cycle", "direction", "duty"]).reset_index(drop=True))
print("\n===== 每階平均風速 =====")
print(summary.to_string(index=False, float_format="{:.3f}".format))
if PEAK_SHARED:
    print(f"(borrowed=True 的列:{PEAK_DUTY}% 只停一階,下降曲線直接採用同一輪上升的 {PEAK_DUTY}%)")
summary.to_csv(out("summary_per_step.csv"), index=False)

# ============================ 上升/下降曲線與遲滯 ============================
def curve(direction):
    g = summary[summary["direction"] == direction].groupby("duty")
    return g["mean_windspeed"].mean(), g["std_windspeed"].mean()


up_mean, up_std = curve("up")
down_mean, down_std = curve("down")

hyst = pd.DataFrame({"duty": sorted(set(up_mean.index) | set(down_mean.index))})
hyst["windspeed_up"] = hyst["duty"].map(up_mean)
hyst["windspeed_down"] = hyst["duty"].map(down_mean)
hyst["std_up"] = hyst["duty"].map(up_std)
hyst["std_down"] = hyst["duty"].map(down_std)
hyst["hysteresis"] = hyst["windspeed_up"] - hyst["windspeed_down"]
# 以滿幅(上升曲線最大 - 最小)為分母;不用「該點平均風速」,否則低風速處(例如 0%)會被放大成假的大遲滯
fs_range = hyst["windspeed_up"].max() - hyst["windspeed_up"].min()
hyst["hyst_pct"] = hyst["hysteresis"] / fs_range * 100
if PEAK_SHARED:
    # 峰值階是上升/下降共用的同一個量測,「上升 - 下降」必為 0,沒有遲滯資訊,不列入
    hyst.loc[hyst["duty"] == PEAK_DUTY, ["hysteresis", "hyst_pct"]] = np.nan

print("\n===== Hysteresis(上升 - 下降) =====")
print(hyst.drop(columns=["std_up", "std_down"]).to_string(index=False, float_format="{:.3f}".format))
if not PEAK_SHARED:
    print(f"(注意:{PEAK_DUTY}% 的「上升 - 下降」是同一個 duty 的第一分鐘與第二分鐘之差,"
          "反映的是時間穩定度(升溫、風扇尚在穩定),不是一般意義的遲滯。)")
hyst.to_csv(out("hysteresis.csv"), index=False)

duty_arr = hyst["duty"].to_numpy(float)
up_arr = hyst["windspeed_up"].to_numpy(float)
down_arr = hyst["windspeed_down"].to_numpy(float)       # 100% 只停一階時,下降的 100% 已在 summary 中取自上升
down_std_arr = hyst["std_down"].to_numpy(float)

# 檢查哪些階沒有資料(例如記錄提早結束)
have = set(zip(summary["direction"], summary["duty"]))
missing = [(d, k) for d, seq in (("up", UP_SEQ), ("down", DOWN_SEQ)) for k in seq if (d, k) not in have]
if missing:
    print("[warn] 這些階沒有資料(記錄提早結束或 START_TIME 不對?):",
          ", ".join(f"{d}@{k}%" for d, k in missing))
    print(f"       若缺的是最後一階:該階在記錄結束前必須錄到至少 {MIN_USABLE_SEC} 秒"
          f"(SETTLE_SEC {SETTLE_SEC} + MIN_LAST_STEP_SEC {MIN_LAST_STEP_SEC})才會被採用;"
          "可延長記錄時間,或調小 MIN_LAST_STEP_SEC。")


# ============================ 起轉 / 停轉(風扇有死區時看這裡)============================
# 由量到的風速判斷:上升時從哪個 duty 開始有風、下降時最低到哪個 duty 還有風。
# 風扇常有「起轉」與「停轉」的 duty 不同(遲滯):例如上升要 20% 才轉,下降到 10% 還在轉。
def _spin_split(w):
    good = ~np.isnan(w)
    on = good & (np.where(good, w, 0.0) >= SPIN_THRESHOLD_MS)
    return duty_arr[on], duty_arr[good & ~on]


spin_up, dead_up = _spin_split(up_arr)
spin_dn, dead_dn = _spin_split(down_arr)
start_duty = float(spin_up.min()) if len(spin_up) else None       # 上升時,第一個有風的 duty
stop_duty = float(spin_dn.min()) if len(spin_dn) else None        # 下降時,最後一個還有風的 duty
_low = lambda w: float(duty_arr[~np.isnan(w)].min()) if (~np.isnan(w)).any() else None   # 有量到風速的最低 duty
low_up, low_dn = _low(up_arr), _low(down_arr)
# 起轉/停轉點「確定」的條件:比它低的 duty 有量到、而且沒在轉;或最低的那階(0%)就已經在轉。
# (記錄從中途開始/提早結束,最低的那幾階沒量到時,只能說「最低量到的 duty 已經在轉」,不能說它就是起轉點。)
sure_up = start_duty is not None and (start_duty > low_up or low_up <= UP_SEQ[0])
sure_dn = stop_duty is not None and (stop_duty > low_dn or low_dn <= DOWN_SEQ[-1])
if len(dead_up) or len(dead_dn) or FAN_START_DUTY > 0:
    _fd = lambda a: "、".join(f"{d:.0f}%" for d in a) if len(a) else "無"
    _wv = lambda arr, d: float(arr[duty_arr == d][0])
    print(f"\n===== 起轉 / 停轉(平均風速 >= {SPIN_THRESHOLD_MS:g} m/s 才算在轉)=====")
    if start_duty is None:
        up_txt = "全部都沒在轉"
    elif sure_up:
        up_txt = f"從 {start_duty:.0f}% 起轉({_wv(up_arr, start_duty):.2f} m/s)"
    else:
        up_txt = f"最低只量到 {start_duty:.0f}%({_wv(up_arr, start_duty):.2f} m/s)且已在轉,更低的 duty 沒有資料,看不出起轉點"
    if stop_duty is None:
        dn_txt = "全部都沒在轉"
    elif sure_dn:
        dn_txt = f"仍在轉的最低 duty = {stop_duty:.0f}%({_wv(down_arr, stop_duty):.2f} m/s)"
    else:
        dn_txt = f"最低只量到 {stop_duty:.0f}%({_wv(down_arr, stop_duty):.2f} m/s)且仍在轉,更低的 duty 沒有資料,看不出停轉點"
    print(f"上升:沒在轉 = {_fd(dead_up)};{up_txt}")
    print(f"下降:沒在轉 = {_fd(dead_dn)};{dn_txt}")
    if sure_up and sure_dn and stop_duty < start_duty:
        print(f"  -> 起轉/停轉有遲滯:上升要到 {start_duty:.0f}% 才轉,下降時 {stop_duty:.0f}% 仍在轉")
    if sure_up and start_duty != START_STEP:                 # 比的是「第一個有風的階」:12% 起轉、每 10% 一階 -> 20%,不算不一致
        _lower = max([d for d in UP_SEQ if d < start_duty], default=None)
        _want = (f"大於 {_lower}% 且不超過 {start_duty:.0f}% 的值(例如 {start_duty:.0f})" if _lower is not None
                 else f"{start_duty:.0f}")
        print(f"[warn] 資料顯示上升時從 {start_duty:.0f}% 這一階才有風,但 FAN_START_DUTY = {FAN_START_DUTY} 對應的第一個有風的階是 {START_STEP}%:"
              f"請把 FAN_START_DUTY 改成{_want}。"
              "(它決定開頭/結尾要補幾階沒風的台階、以及線性度的預設範圍。)")
        if start_duty > START_STEP and (duty_arr == START_STEP).any() and not np.isnan(_wv(up_arr, START_STEP)):
            print(f"       若 {START_STEP}% 其實有在轉、只是風速很低(這一階量到 {_wv(up_arr, START_STEP):.2f} m/s,低於 SPIN_THRESHOLD_MS = {SPIN_THRESHOLD_MS:g}),"
                  "不用改 FAN_START_DUTY,把 SPIN_THRESHOLD_MS 調小即可(風速計在靜止空氣中的讀值要明顯小於它)。")


# ============================ 環境:溫度、濕度隨 duty(檢查「上升/下降的差」是不是升溫、環境漂移造成的)============================
# 溫度是風速計量到的空氣溫度(解析度約 0.1 °C)。同一個 duty,若下降階段的溫度比上升階段高,
# 風速差就可能含有熱效應,不能全算成遲滯。
have_env = bool(raw["temp_c"].notna().any())
if have_env:
    env = (settled.groupby(["cycle", "direction", "duty"])[["temp_c", "rh_pct"]].mean().reset_index())
    if PEAK_SHARED:                                      # 100% 只停一階時,下降端借用上升端(同 summary 的做法)
        _pk = env[(env["direction"] == "up") & (env["duty"] == PEAK_DUTY)].copy()
        _pk["direction"] = "down"
        env = pd.concat([env, _pk], ignore_index=True)
    env_up = env[env["direction"] == "up"].groupby("duty")[["temp_c", "rh_pct"]].mean()
    env_dn = env[env["direction"] == "down"].groupby("duty")[["temp_c", "rh_pct"]].mean()
    env_tab = pd.DataFrame({"duty": hyst["duty"].to_numpy()})
    env_tab["temp_up"] = env_tab["duty"].map(env_up["temp_c"])
    env_tab["temp_down"] = env_tab["duty"].map(env_dn["temp_c"])
    env_tab["temp_up_minus_down"] = env_tab["temp_up"] - env_tab["temp_down"]
    env_tab["rh_up"] = env_tab["duty"].map(env_up["rh_pct"])
    env_tab["rh_down"] = env_tab["duty"].map(env_dn["rh_pct"])
    env_tab["rh_up_minus_down"] = env_tab["rh_up"] - env_tab["rh_down"]
    env_tab["wind_up_minus_down"] = hyst["hysteresis"].to_numpy()
    print("\n===== 環境:溫度/濕度隨 duty(上升 vs 下降)=====")
    print(env_tab.to_string(index=False, float_format="{:.3f}".format))
    env_tab.to_csv(out("environment_by_duty.csv"), index=False)
    _t_first = raw.loc[raw["t_log"] < 60, "temp_c"].median()
    _t_last = raw.loc[raw["t_log"] > raw["t_log"].max() - 60, "temp_c"].median()
    print(f"[env] 溫度:log 開頭約 {_t_first:.1f} °C -> 結尾約 {_t_last:.1f} °C"
          f"(整段 {raw['temp_c'].min():.1f} ~ {raw['temp_c'].max():.1f} °C);"
          f"濕度 {raw['rh_pct'].min():.1f} ~ {raw['rh_pct'].max():.1f} %RH")
else:
    print("\n[info] 紀錄中沒有可用的溫度/濕度欄位,略過環境分析(fig7)")

# ============================ PWM 對照表:風速(多種單位)與風量 ============================
# 風量 = 風速 x 出風口面積。這裡假設量到的風速 = 出風口截面的平均風速;
# 實際會受風速計擺放位置、出風口風速分布影響,風量只能當估算值。
FT, MILE, NMI = 0.3048, 1609.344, 1852.0               # 1 ft、1 mile、1 海浬 = 幾 m(定義值)
OUTLET_AREA_M2 = np.pi * (OUTLET_DIAMETER_MM / 2) ** 2 * 1e-6
VEL_COLS = [                                            # (欄名, 1 m/s 等於幾單位, Excel 數字格式)
    ("Air Velocity (m/s)", 1.0, "0.000"),
    ("Air Velocity (km/h)", 3.6, "0.00"),
    ("Air Velocity (mph)", 3600 / MILE, "0.00"),
    ("Air Velocity (ft/min)", 60 / FT, "0.0"),
    ("Air Velocity (ft/s)", 1 / FT, "0.00"),
    ("Air Velocity (knots)", 3600 / NMI, "0.00"),
]
FLOW_COLS = [                                           # (欄名, 1 m³/s 等於幾單位, Excel 數字格式)
    ("Air Flow (CMM, m³/min)", 60.0, "0.0000"),
    ("Air Flow (CFM, ft³/min)", 60 / FT ** 3, "0.000"),
    ("Air Flow (CMS, m³/s)", 1.0, "0.000000"),
]


VEL_FACTOR = {"m/s": 1.0, "km/h": 3.6, "mph": 3600 / MILE, "ft/min": 60 / FT, "ft/s": 1 / FT, "knots": 3600 / NMI}
FLOW_FACTOR = {"CMS": 1.0, "CMM": 60.0, "CFM": 60 / FT ** 3}                     # 1 m³/s 等於幾單位
for _units, _tab in ((FIG_VELOCITY_UNITS, VEL_FACTOR), (FIG_FLOW_UNITS, FLOW_FACTOR)):
    if _units[0] is None:
        raise SystemExit("圖的左軸單位不能是 None")
    for _u in _units:
        if _u is not None and _u not in _tab:
            raise SystemExit(f"圖的單位 {_u!r} 不存在,可選:{', '.join(_tab)}")


def make_airflow_table(duty, v_ms):
    v = np.asarray(v_ms, float)
    t = pd.DataFrame({"PWM (%)": np.asarray(duty).astype(int)})
    for name, f, _ in VEL_COLS:
        t[name] = v * f
    cms = v * OUTLET_AREA_M2
    for name, f, _ in FLOW_COLS:
        t[name] = cms * f
    return t


v_avg = hyst[["windspeed_up", "windspeed_down"]].mean(axis=1).to_numpy()     # 上升與下降的平均
airflow_tables = {
    "Average (Up+Down)": make_airflow_table(duty_arr, v_avg),
    "Ramp Up": make_airflow_table(duty_arr, up_arr),
    "Ramp Down": make_airflow_table(duty_arr, down_arr),
}
_short = {"Air Velocity (m/s)": "m/s", "Air Velocity (km/h)": "km/h", "Air Velocity (mph)": "mph",
          "Air Velocity (ft/min)": "ft/min", "Air Velocity (ft/s)": "ft/s", "Air Velocity (knots)": "knots",
          "Air Flow (CMM, m³/min)": "CMM", "Air Flow (CFM, ft³/min)": "CFM", "Air Flow (CMS, m³/s)": "CMS"}
print(f"\n===== PWM 對照表(上升與下降平均;出風口直徑 {OUTLET_DIAMETER_MM:g} mm,"
      f"面積 {OUTLET_AREA_M2 * 1e6:.2f} mm² = {OUTLET_AREA_M2 * 1e4:.4f} cm²)=====")
_fmt_console = {"m/s": "{:.3f}", "km/h": "{:.2f}", "mph": "{:.2f}", "ft/min": "{:.1f}", "ft/s": "{:.2f}",
                "knots": "{:.2f}", "CMM": "{:.4f}", "CFM": "{:.3f}", "CMS": "{:.6f}"}      # CMS 數值很小,要多印幾位
print(airflow_tables["Average (Up+Down)"].rename(columns=_short)
      .to_string(index=False, formatters={k: v.format for k, v in _fmt_console.items()}))
print("(風量 = 風速 x 出風口面積,假設風速 = 出風口截面平均風速,僅供估算;上升/下降各自的表在 Excel 的其他工作表)")

airflow_tables["Average (Up+Down)"].to_csv(out("pwm_airflow_table.csv"), index=False, encoding="utf-8-sig")
print(f"\n===== PWM 對照表:上升 Ramp Up(Air Velocity / Air Flow)=====")
print(airflow_tables["Ramp Up"].rename(columns=_short)
      .to_string(index=False, formatters={k: v.format for k, v in _fmt_console.items()}))
airflow_tables["Ramp Up"].to_csv(out("pwm_airflow_table_up.csv"), index=False, encoding="utf-8-sig")
airflow_tables["Ramp Down"].to_csv(out("pwm_airflow_table_down.csv"), index=False, encoding="utf-8-sig")
info_rows = [
    ("出風口直徑 (mm)", f"{OUTLET_DIAMETER_MM:g}"),
    ("出風口面積 (mm²)", f"{OUTLET_AREA_M2 * 1e6:.3f}"),
    ("出風口面積 (cm²)", f"{OUTLET_AREA_M2 * 1e4:.4f}"),
    ("出風口面積 (m²)", f"{OUTLET_AREA_M2:.6e}"),
    ("風量公式", "Air Flow (m³/s) = Air Velocity (m/s) x 面積 (m²)"),
    ("風速換算 (1 m/s =)", f"3.6 km/h = {3600 / MILE:.5f} mph = {60 / FT:.3f} ft/min = {1 / FT:.5f} ft/s = {3600 / NMI:.5f} knots"),
    ("風量換算 (1 m³/s =)", f"60 CMM = {60 / FT ** 3:.3f} CFM"),
    ("單位說明", "mph = miles/hour;ft/min = FPM;CMM = m³/min;CFM = ft³/min;CMS = m³/s"),
    ("Average 工作表", "(上升 + 下降) / 2;各輪已先平均"),
    ("Ramp Up / Ramp Down", "各自方向的平均;" + ("下降的 100% 取自上升的 100%(100% 只停一階)" if PEAK_SHARED
                                                  else "100% 停兩階:第一階屬於上升、第二階屬於下降")),
    ("注意", "風量為估算值:假設風速計量到的風速 = 出風口截面平均風速;實際受擺放位置與風速分布影響"),
    ("資料檔", str(DATA_FILE)),
]
info_df = pd.DataFrame(info_rows, columns=["Item", "Value"])
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter
_fmt = {name: nf for name, _, nf in VEL_COLS + FLOW_COLS}
with pd.ExcelWriter(out("pwm_airflow_table.xlsx"), engine="openpyxl") as xw:
    for sheet, tdf in airflow_tables.items():
        tdf.to_excel(xw, sheet_name=sheet, index=False)
    info_df.to_excel(xw, sheet_name="Info", index=False)
    for sheet, tdf in airflow_tables.items():
        ws = xw.sheets[sheet]
        ws.freeze_panes = "B2"
        ws.row_dimensions[1].height = 34
        for j, col in enumerate(tdf.columns, start=1):
            c = ws.cell(row=1, column=j)
            c.font = Font(bold=True)
            c.alignment = Alignment(wrap_text=True, horizontal="center", vertical="center")
            ws.column_dimensions[get_column_letter(j)].width = 11 if j == 1 else 17
            if col in _fmt:
                for r in range(2, len(tdf) + 2):
                    ws.cell(row=r, column=j).number_format = _fmt[col]
    wi = xw.sheets["Info"]
    wi.column_dimensions["A"].width = 26
    wi.column_dimensions["B"].width = 100
    for c in wi[1]:
        c.font = Font(bold=True)

# ============================ 線性度 ============================
def _t95(dof):
    """雙尾 95% 的 t 值(小樣本查表,免裝 scipy)。"""
    tab = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228}
    return tab.get(dof, 2.16 if dof <= 15 else 2.05 if dof <= 30 else 1.98)


def linfit(x, y):
    m = ~np.isnan(y)
    x, y = x[m], y[m]
    if len(x) < 3:
        return None
    s, i = np.polyfit(x, y, 1)
    pred = s * x + i
    res = y - pred
    n = len(x)
    ss_tot = np.sum((y - y.mean()) ** 2)
    fs = y.max() - y.min()
    se = np.sqrt(np.sum(res ** 2) / (n - 2) / np.sum((x - x.mean()) ** 2))     # 斜率標準誤
    rmse = np.sqrt(np.mean(res ** 2))
    return dict(
        n=n, slope=s, intercept=i, x=x, y=y, pred=pred, res=res, fs=fs,
        r2=1 - np.sum(res ** 2) / ss_tot if ss_tot > 0 else np.nan,
        max_res=np.max(np.abs(res)),
        nl_pct=np.max(np.abs(res)) / fs * 100 if fs > 0 else np.nan,   # 最大偏離 / 滿幅
        rmse=rmse, rmse_pct=rmse / fs * 100 if fs > 0 else np.nan,     # 殘差均方根 / 滿幅
        se_slope=se, ci_slope=_t95(n - 2) * se,
    )


print("\n===== 線性度:windspeed = slope x duty + intercept =====")
print("max|res| = 離直線最遠的點;NL% = max|res| 佔該曲線風速範圍(滿幅)的百分比")
fits = {}
for lo, hi in LIN_RANGES:
    m = (duty_arr >= lo) & (duty_arr <= hi)
    for name, arr in (("Up", up_arr), ("Down", down_arr)):
        f = linfit(duty_arr[m], arr[m])
        fits[(name, lo, hi)] = f
        if f:
            print(f"{name:4s} duty {lo:3d}-{hi:3d}%: slope={f['slope']:.4f} m/s/%  "
                  f"intercept={f['intercept']:.3f}  R2={f['r2']:.4f}  "
                  f"max|res|={f['max_res']:.3f} m/s  NL={f['nl_pct']:.1f}%FS")
print("(R2 > 0.98 且 NL < 約 5%FS 通常可視為相當線性)")
if START_STEP > UP_SEQ[0]:
    _prev = max(d for d in UP_SEQ if d < START_STEP)         # 起轉前最後一個沒風的階
    _dz = f"{UP_SEQ[0]}%" if _prev == UP_SEQ[0] else f"{UP_SEQ[0]}~{_prev}%"
    print(f"(風扇要到 {START_STEP}% 這一階才有風" + (f"(FAN_START_DUTY = {FAN_START_DUTY})" if FAN_START_DUTY != START_STEP else "")
          + f":範圍包含 {_dz} 的死區時,死區也被算進直線,線性度會變差;"
          f"要說明「起轉之後」是否線性,請看 {START_STEP}% 以上的範圍。)")

# 報告用彙整表:一次列出所有範圍/方向的線性度指標,另存 CSV
print("\n===== 線性度彙整(報告用)=====")
rows = [dict(direction=nm, duty_range=f"{lo}-{hi}%", n_points=f["n"], slope=f["slope"],
             slope_ci95=f["ci_slope"], intercept=f["intercept"], R2=f["r2"],
             RMSE_mps=f["rmse"], RMSE_pctFS=f["rmse_pct"], max_dev_mps=f["max_res"], NL_pctFS=f["nl_pct"])
        for (nm, lo, hi), f in fits.items() if f]
lin_df = pd.DataFrame(rows)
print(lin_df.to_string(index=False, float_format="{:.5f}".format))
lin_df.to_csv(out("linearity_summary.csv"), index=False)
for lo, hi in LIN_RANGES:
    fu_, fd_ = fits.get(("Up", lo, hi)), fits.get(("Down", lo, hi))
    if fu_ and fd_:
        dsl = fd_["slope"] - fu_["slope"]
        z = dsl / np.hypot(fu_["se_slope"], fd_["se_slope"])
        print(f"duty {lo}-{hi}%: 下降斜率 - 上升斜率 = {dsl:+.4f} m/s/%({dsl / fu_['slope'] * 100:+.1f}%),差 / 標準誤 = {z:.1f}")
print("註:斜率 CI 與標準誤假設殘差是隨機的;實際殘差有系統性彎曲(見 fig2 殘差圖),")
print("    所以 CI 只代表「一條直線描述這幾個階平均值有多緊密」,不是嚴格的統計推論。")

# ============================ 平滑度 ============================
def step_deltas(d, w):
    """相鄰兩階 -> (區間中點, 風速變化, 這一階的起點 duty, 終點 duty)。"""
    m = ~np.isnan(w)
    d, w = d[m], w[m]
    return (d[:-1] + d[1:]) / 2, np.diff(w), d[:-1], d[1:]


mid_up, d_up, a_up, b_up = step_deltas(duty_arr, up_arr)                       # 0 -> 100
mid_dn, d_dn, a_dn, b_dn = step_deltas(duty_arr[::-1], down_arr[::-1])         # 100 -> 0
# 區間中點 -> (下界, 上界)。階梯不等距(例如 0、12、20、30...)時,區間要用實際的兩端,不能用「中點 ± 半階」去推
_span = {}
for _m, _a, _b in zip(np.r_[mid_up, mid_dn], np.r_[a_up, a_dn], np.r_[b_up, b_dn]):
    _span.setdefault(round(float(_m), 6), (min(_a, _b), max(_a, _b)))


def step_kinds(w):
    """相鄰兩階的風速變化屬於哪一類:'dead' = 兩階都沒在轉;'edge' = 一階沒轉、一階在轉(起轉/停轉);'run' = 兩階都在轉。
    起轉(從靜止跳到有風)的變化量天生就和其他階不同,不能拿來當「不平滑」。"""
    w = w[~np.isnan(w)]
    off = w < SPIN_THRESHOLD_MS
    return np.where(off[:-1] & off[1:], "dead", np.where(off[:-1] | off[1:], "edge", "run"))


kind_up = step_kinds(up_arr)
kind_dn = step_kinds(down_arr[::-1])


def interval_label(mid):
    """相鄰兩階的中點 -> duty 區間文字,例如 5 -> '0~10%'(階梯 0、12、20 時,6 -> '0~12%'、16 -> '12~20%')。"""
    lo, hi = _span.get(round(float(mid), 6), (mid - STEP_W / 2, mid + STEP_W / 2))
    return f"{lo:.0f}~{hi:.0f}%"


print("\n===== 平滑度:逐階變化量 =====")
for label, mid, delta, kind, bad, edge_note, wid in (
        ("Up(每升一階,風速變化)", mid_up, d_up, kind_up, lambda v: v < 0, "起轉:風扇從靜止到轉動", np.abs(b_up - a_up)),
        ("Down(每降一階,風速變化)", mid_dn, d_dn, kind_dn, lambda v: v > 0, "停轉:風扇從轉動到靜止", np.abs(b_dn - a_dn))):
    run = kind == "run"
    unit = wid / STEP_W                                              # 這一階的 duty 差是典型階寬的幾倍(等距階梯 = 1;階梯 0、12、20 的 12~20% 是 0.8)
    med = np.median(np.abs(delta[run]) / unit[run]) if run.any() else 0     # 典型變化量(換算成每個典型階寬)只用「兩階都在轉」的區間算
    print(f"{label}:")
    for d, v, k, u, wd in zip(mid, delta, kind, unit, wid):
        note = ""
        if k == "dead":
            note = "  (風扇沒在轉)"
        elif k == "edge":
            note = f"  ({edge_note},不算不平滑)"
        else:
            if bad(v):
                note += "  <-- 反向!"
            if med > 0 and abs(abs(v) / u - med) > 0.5 * med:
                note += "  <-- 跟其他階差很多"
            if u != 1:
                note += f"  (這一階 duty 只差 {wd:.0f}%,判斷是否「差很多」時已換算成每 {STEP_W}%)"
        print(f"  duty {interval_label(d):>8s}: {v:+.3f} m/s{note}")

# 上升與下降的變化量放在同一個區間、同一側(都取正值)比較
cmp_df = pd.DataFrame({"mid": sorted(set(np.round(mid_up, 6)) | set(np.round(mid_dn, 6)))})
cmp_df["duty_interval"] = cmp_df["mid"].map(interval_label)
cmp_df["up_rise"] = cmp_df["mid"].map(dict(zip(np.round(mid_up, 6), d_up)))
cmp_df["down_drop"] = cmp_df["mid"].map(dict(zip(np.round(mid_dn, 6), -d_dn)))
cmp_df["up_minus_down"] = cmp_df["up_rise"] - cmp_df["down_drop"]
cmp_df = cmp_df.drop(columns="mid")
print("\n上升與下降的變化量對照(都取正值,m/s):")
print(cmp_df.to_string(index=False, float_format="{:.3f}".format))
if PEAK_SHARED:
    _pk_prev = max([d for d in UP_SEQ if d < PEAK_DUTY], default=PEAK_DUTY - STEP_W)
    print(f"({_pk_prev}~{PEAK_DUTY}% 區間的下降端用的是借用的上升 {PEAK_DUTY}%)")
cmp_df.to_csv(out("step_change_comparison.csv"), index=False)

# ============================ 跨輪一致性 / 視窗內噪訊 ============================
real = summary[~summary["borrowed"]]                  # 只用獨立量測的階(排除借用的 down@100)
n_cycles = real["cycle"].nunique()
print(f"\n===== 一致性:跨輪比較({n_cycles} 輪)=====")
if n_cycles < 2:
    print("只有 1 輪,無法比較輪與輪之間 -- 多跑幾輪才看得出重複性。")
else:
    cons = (real.groupby(["direction", "duty"])["mean_windspeed"]
            .agg(mean_across="mean", std_across="std", n_cycles="count").reset_index())
    print(cons.to_string(index=False, float_format="{:.3f}".format))
    cons.to_csv(out("cross_cycle_consistency.csv"), index=False)
    w = cons.loc[cons["std_across"].idxmax()]
    print(f"跨輪差異最大:{w['direction']} duty={w['duty']:.0f}%, std={w['std_across']:.3f} m/s")

print("\n===== 單階視窗內噪訊最大的前 3 筆 =====")
print(real.sort_values("std_windspeed", ascending=False).head(3)
      [["cycle", "direction", "duty", "mean_windspeed", "std_windspeed", "n"]]
      .to_string(index=False, float_format="{:.3f}".format))

# ============================ 繪圖 ============================
# Fig 0: 原始風速 + 判定的 duty 階梯 + 台階邊界 -- 先看這張確認切段正確!
# 紅色短線 = 由資料偵測到的台階邊界;灰色短線 = 固定時間格子(START_TIME + n x STEP_SEC)
fig, ax = plt.subplots(figsize=(12, 4.8))
xm = raw["t_log"] / 60
ax.plot(xm, raw["windspeed"], lw=0.6, label="Wind speed")
ax.set_xlabel("Time since first log sample (min)")
ax.set_ylabel("Wind speed (m/s)")
ax2 = ax.twinx()
ax2.plot(xm, raw["duty"].where(raw["complete"]), color="gray", alpha=0.6, drawstyle="steps-post")
ax2.set_ylabel("PWM duty (%)  (gray = labels used)")
tr = ax.get_xaxis_transform()
g0 = (t0 - raw["timestamp"].iloc[0]).total_seconds()
tmax = raw["t_log"].max()
grid_pts = g0 + STEP_SEC * np.arange(np.ceil(-g0 / STEP_SEC), np.floor((tmax - g0) / STEP_SEC) + 1)
ax.vlines(grid_pts / 60, 0.93, 0.965, transform=tr, color="gray", lw=1.2, label="Time-grid edge")
if det_B is not None:
    ax.vlines(det_B / 60, 0.965, 1.0, transform=tr, color="red", lw=1.5, label="Step edge detected from data")
# 每個台階標上判定的 duty(貼在圖的底部),方便一眼核對標籤
for _k, _g in raw[raw["complete"]].groupby("step_idx"):
    ax.text(_g["t_log"].mean() / 60, 0.02, f"{int(_g['duty'].iloc[0])}%", transform=tr,
            ha="center", va="bottom", fontsize=7, color="dimgray")
ax.set_title(f"Raw log, step edges and duty labels (mode: {mode_used})")
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=3, fontsize=8, frameon=False)   # 放在圖外,不擋資料與刻度
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(out("fig0_timeseries_check.png"), dpi=150, bbox_inches="tight")

# Fig 1: 上升/下降曲線 (誤差線 = 視窗內 1σ)
fig, ax = plt.subplots(figsize=(7, 5))
ax.errorbar(hyst["duty"], hyst["windspeed_up"], yerr=hyst["std_up"], fmt="o-", capsize=3, label="Ramp Up")
ax.errorbar(duty_arr, down_arr, yerr=down_std_arr, fmt="x--", capsize=3,
            label="Ramp Down (100% = shared peak step)" if PEAK_SHARED else "Ramp Down")
ax.set_xlabel("PWM Duty (%)")
ax.set_ylabel("Wind Speed (m/s)")
ax.set_title("Duty vs Wind Speed (error bar = within-window 1σ)")
ax.legend()
ax.grid()
fig.savefig(out("fig1_duty_vs_windspeed.png"), dpi=150)

# Fig 2: 線性度 -- LIN_RANGES 的每個範圍各一張(資料 + 擬合線與方程式 + 殘差)
for ri, (lo, hi) in enumerate(LIN_RANGES):
    fu, fd = fits.get(("Up", lo, hi)), fits.get(("Down", lo, hi))
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(7, 8), sharex=True, gridspec_kw={"height_ratios": [3, 2]})
    for f, lab, mk, ls in ((fu, "Up", "o", "-"), (fd, "Down", "x", "--")):
        if f:
            a1.plot(f["x"], f["y"], mk, label=f"{lab} data")
            a1.plot(f["x"], f["pred"], ls,
                    label=f"{lab} fit: y={f['slope']:.4f}x{f['intercept']:+.3f}\n    R²={f['r2']:.4f}, NL={f['nl_pct']:.2f}%FS")
            a2.plot(f["x"], f["res"], mk + ls, label=f"{lab} residual")
    a1.set_ylabel("Wind Speed (m/s)")
    a1.set_title(f"Linearity Check (duty {lo}-{hi}%)")
    a1.legend(fontsize=8)
    a1.grid()
    a2.axhline(0, color="gray", ls="--")
    a2.set_xlabel("PWM Duty (%)")
    a2.set_ylabel("Residual (m/s)")
    a2.legend(fontsize=8)
    a2.grid()
    fig.tight_layout()
    fig.savefig(out("fig2_linearity.png" if ri == 0 else f"fig2_linearity_{lo}_{hi}.png"), dpi=150)

# Fig 3: 遲滯 %
fig, ax = plt.subplots(figsize=(7, 4))
ax.plot(hyst["duty"], hyst["hyst_pct"], "o-")
ax.axhline(0, ls="--", color="gray")
ax.set_xlabel("PWM Duty (%)")
ax.set_ylabel("Hysteresis (% of full scale)")
ax.set_title("Hysteresis = (Up - Down) / full-scale range")
_sec = ax.secondary_yaxis("right", functions=(lambda pct: pct * fs_range / 100, lambda v: v * 100 / fs_range))
_sec.set_ylabel("Up - Down (m/s)")
ax.grid()
fig.tight_layout()
fig.savefig(out("fig3_hysteresis.png"), dpi=150)

# Fig 4: 逐階變化量(平滑度)-- 橫軸是 duty 區間;上升的增加量與下降的減少量「都取正值」並排,方便直接比較
fig, ax = plt.subplots(figsize=(9, 4.2))
w = 0.3 * STEP_W
b1 = ax.bar(mid_up - w / 2, d_up, width=w, label="Up: rise (lower -> upper duty)")
b2 = ax.bar(mid_dn + w / 2, -d_dn, width=w, label="Down: drop (upper -> lower duty)")
for bars in (b1, b2):
    ax.bar_label(bars, fmt="%.2f", fontsize=7, padding=2)
ticks = np.array(sorted(set(np.round(mid_up, 6)) | set(np.round(mid_dn, 6))))
ax.set_xticks(ticks)
ax.set_xticklabels([interval_label(t) for t in ticks], fontsize=9)
ax.axhline(0, ls="--", color="gray")
ax.set_xlabel("PWM duty interval")
ax.set_ylabel("Wind speed change per step, magnitude (m/s)")
ax.set_title("Step-to-Step Change (up vs down, same side)")
top = max(np.max(d_up), np.max(-d_dn))
bot = min(0.0, np.min(d_up), np.min(-d_dn))
ax.set_ylim(bot * 1.3, top * 1.35)
ax.legend(loc="upper right", ncol=2, fontsize=8)
ax.grid(axis="y")
fig.tight_layout()
fig.savefig(out("fig4_smoothness.png"), dpi=150)

# Fig 5: 各輪重複性
fig, ax = plt.subplots(figsize=(7, 5))
for (cyc, dr), g in summary.groupby(["cycle", "direction"]):
    ax.plot(g["duty"], g["mean_windspeed"], "o-" if dr == "up" else "x--",
            alpha=0.7, label=f"Cycle {cyc} {dr}")
ax.set_xlabel("PWM Duty (%)")
ax.set_ylabel("Wind Speed (m/s)")
ax.set_title("Repeatability Across Cycles")
ax.legend(fontsize=8)
ax.grid()
fig.savefig(out("fig5_repeatability.png"), dpi=150)

# Fig 6: PWM 對照圖 -- 左軸風速 (m/s)、右軸風量(單位 = FIG_FLOW_UNITS 的第一個);線 = 上升與下降的平均,色帶 = 上升與下降之間的範圍
FLOW_UNIT = FIG_FLOW_UNITS[0]
FLOW_PER_MS = OUTLET_AREA_M2 * FLOW_FACTOR[FLOW_UNIT]      # 1 m/s 的風速 = 幾個風量單位
_stack = np.vstack([up_arr, down_arr])
fig, ax = plt.subplots(figsize=(8, 5))
ax.fill_between(duty_arr, np.nanmin(_stack, axis=0), np.nanmax(_stack, axis=0),
                color="C0", alpha=0.25, label="Up/Down range")
ax.plot(duty_arr, v_avg, "o-", color="C0", label="Average (Up+Down)")
for _x, _y in zip(duty_arr, v_avg):
    ax.annotate(f"{_y:.2f}", (_x, _y), textcoords="offset points", xytext=(0, 8), ha="center", fontsize=8)
ax.set_xlabel("PWM Duty (%)")
ax.set_ylabel("Air Velocity (m/s)")
_sec = ax.secondary_yaxis("right", functions=(lambda v: v * FLOW_PER_MS, lambda q: q / FLOW_PER_MS))
_sec.set_ylabel(f"Air Flow ({FLOW_UNIT})")
ax.set_ylim(top=np.nanmax(_stack) * 1.1)                  # 留空間給最高點的數字標籤
ax.set_title(f"PWM vs Air Velocity / Air Flow (outlet diameter {OUTLET_DIAMETER_MM:g} mm)")
ax.legend(loc="upper left", fontsize=8)
ax.grid()
fig.tight_layout()
fig.savefig(out("fig6_pwm_velocity_flow.png"), dpi=150)

# Fig 8 / Fig 9: 上升(Ramp Up)與下降(Ramp Down)各一張 -- 左圖 Air Velocity、右圖 Air Flow
# 軸的單位由 FIG_VELOCITY_UNITS / FIG_FLOW_UNITS 決定;其他單位請看 pwm_airflow_table_*.csv 或 Excel
_ANNOT = {"m/s": ".2f", "km/h": ".1f", "mph": ".1f", "ft/min": ".0f", "ft/s": ".1f", "knots": ".1f",
          "CMM": ".3f", "CFM": ".2f", "CMS": ".5f"}


def plot_velocity_flow(label, v_ms, fname):
    v_ms = np.asarray(v_ms, float)
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    specs = (("Air Velocity", FIG_VELOCITY_UNITS, VEL_FACTOR, v_ms, "C0"),
             ("Air Flow", FIG_FLOW_UNITS, FLOW_FACTOR, v_ms * OUTLET_AREA_M2, "C2"))
    for ax_, (name, (u_left, u_right), fac, base, color) in zip(axes, specs):
        y = base * fac[u_left]
        ax_.plot(duty_arr, y, "o-", color=color)
        for x_, y_ in zip(duty_arr, y):
            if not np.isnan(y_):
                ax_.annotate(format(y_, _ANNOT[u_left]), (x_, y_), textcoords="offset points",
                             xytext=(0, 8), ha="center", fontsize=8)
        if u_right is not None:
            k = fac[u_right] / fac[u_left]
            sec = ax_.secondary_yaxis("right", functions=(lambda a, k=k: a * k, lambda b, k=k: b / k))
            sec.set_ylabel(f"{name} ({u_right})")
        ax_.set_ylabel(f"{name} ({u_left})")
        ax_.set_xlabel("PWM Duty (%)")
        ax_.set_ylim(top=np.nanmax(y) * 1.12)               # 留空間給最高點的數字標籤
        ax_.set_title(f"{label}: {name}")
        ax_.grid()
    fig.suptitle(f"{label} - PWM vs Air Velocity / Air Flow (outlet diameter {OUTLET_DIAMETER_MM:g} mm)")
    fig.tight_layout()
    fig.savefig(out(fname), dpi=150)


plot_velocity_flow("Ramp Up", up_arr, "fig8_ramp_up_velocity_flow.png")
plot_velocity_flow("Ramp Down", down_arr, "fig9_ramp_down_velocity_flow.png")

# Fig 7: 溫度/濕度 -- 上圖:整段時間的變化(底色 = 上升/下降階段);下圖:同一個 duty 上升 vs 下降的平均溫度
if have_env:
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(11, 7), gridspec_kw={"height_ratios": [3, 2]})
    _steps = raw[raw["complete"]].groupby("step_idx").agg(t0=("t_log", "min"), t1=("t_log", "max"),
                                                          direction=("direction", "first"))
    _spans = []
    for _r in _steps.itertuples():
        if _spans and _spans[-1][2] == _r.direction:
            _spans[-1][1] = _r.t1
        else:
            _spans.append([_r.t0, _r.t1, _r.direction])
    for _a, _b, _dr in _spans:
        a1.axvspan(_a / 60, _b / 60, color="C0" if _dr == "up" else "C1", alpha=0.08)
        a1.text((_a + _b) / 120, 0.97, "Up phase" if _dr == "up" else "Down phase",
                transform=a1.get_xaxis_transform(), ha="center", va="top", fontsize=8, color="dimgray")
    # 儀器解析度只有 0.1,原始值會在相鄰兩個值之間來回跳;畫 30 秒中位數,趨勢才看得出來
    _sm = raw.set_index("timestamp")[["temp_c", "rh_pct"]].rolling("30s", center=True, min_periods=1).median()
    a1.plot(raw["t_log"] / 60, _sm["temp_c"].to_numpy(), color="C3", lw=1.5)
    a1.set_ylabel("Temperature (°C)", color="C3")
    a1.set_xlabel("Time since first log sample (min)")
    a1.set_title("Air temperature / humidity during the run (30 s median; shaded: up / down phase)")
    a1b = a1.twinx()
    a1b.plot(raw["t_log"] / 60, _sm["rh_pct"].to_numpy(), color="C2", lw=1.5, alpha=0.9)
    a1b.set_ylabel("Humidity (%RH)", color="C2")
    a1.grid(alpha=0.3)
    a2.plot(env_tab["duty"], env_tab["temp_up"], "o-", label="Ramp Up")
    a2.plot(env_tab["duty"], env_tab["temp_down"], "x--", label="Ramp Down")
    a2.set_xlabel("PWM Duty (%)")
    a2.set_ylabel("Temperature (°C)")
    a2.set_title("Mean temperature at each duty (same duty, up vs down)")
    a2.legend(fontsize=8)
    a2.grid()
    fig.tight_layout()
    fig.savefig(out("fig7_environment.png"), dpi=150)

_files = os.listdir(OUT_DIR)
print(f"\n輸出資料夾:{os.path.abspath(OUT_DIR)}")
print(f"  圖 {sum(f.endswith('.png') for f in _files)} 張,資料表 {sum(f.endswith(('.csv', '.xlsx')) for f in _files)} 個")
if OPEN_OUT_DIR:
    try:
        if sys.platform.startswith("win"):
            os.startfile(os.path.abspath(OUT_DIR))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", OUT_DIR])
        else:
            subprocess.Popen(["xdg-open", OUT_DIR])
    except Exception:
        pass                                 # 打不開資料夾不影響結果
if SHOW_PLOTS:
    plt.show()
else:
    plt.close("all")