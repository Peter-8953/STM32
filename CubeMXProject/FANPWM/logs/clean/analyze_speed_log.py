#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""速度閉迴路 log 分析：步階響應指標 + duty 拆解 + 一致性檢查

用法
    python analyze_speed_log.py log.csv
    python analyze_speed_log.py log.csv --tick-ms 1 --tail-s 3 --png out.png

log 以 CSV (逗號分隔) 為主，也接受 Tab / 空白 / 分號分隔；會自動略過標題列之前的雜訊行、
中途重複印出的標題與其他非數字行。至少要有欄位：
    tick, target_rpm, actual_rpm, duty, ff, integral   (有 ccr、per 時會多做一項檢查)
假設控制器為  duty = ff + Kp*(sp - actual) + integral ,  ccr = duty/100*per
只分析 log 裡第一個 target 變動 (步階)。
"""
import argparse
import sys

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

try:  # 避免 Windows 主控台中文亂碼
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def cross(t, y, level):
    """y 第一次由下往上穿越 level 的時間 (線性內插)；沒有則回傳 None"""
    for i in range(1, len(y)):
        if y[i - 1] < level <= y[i]:
            return t[i - 1] + (level - y[i - 1]) / (y[i] - y[i - 1]) * (t[i] - t[i - 1])
    return None


def settle(t, y, target, pct):
    """最後一次離開 ±pct% 帶之後，第一個回到帶內的時間；結尾仍在帶外則回傳 None"""
    out = np.abs(y - target) > abs(target) * pct / 100
    if not out.any():
        return t[0]
    last = np.where(out)[0][-1]
    return None if last == len(y) - 1 else t[last + 1]


def f(v, unit="s", nd=2):
    return "N/A" if v is None else f"{v:.{nd}f} {unit}"


NEED = ["tick", "target_rpm", "actual_rpm", "duty", "ff", "integral"]


def load_log(path):
    """讀 CSV / TSV / 空白分隔的 log。自動判斷分隔符號，容忍 BOM、CRLF、欄名空白、
    標題列之前的雜訊行，以及中途夾雜的非數字行 (例如重複印出的標題)。"""
    with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
        lines = fh.read().split("\n")
    hdr = next((i for i, ln in enumerate(lines) if "tick" in ln and "actual_rpm" in ln), 0)
    head = lines[hdr]
    sep = "," if "," in head else ";" if ";" in head else r"\s+"
    df = pd.read_csv(path, sep=sep, skiprows=hdr, encoding="utf-8-sig",
                     skipinitialspace=True, on_bad_lines="skip")
    df.columns = [str(c).strip() for c in df.columns]
    miss = [c for c in NEED if c not in df.columns]
    if miss:
        sys.exit(f"找不到欄位 {miss}；檔案裡的欄位是 {list(df.columns)}")
    df = df.apply(pd.to_numeric, errors="coerce").dropna(subset=NEED).reset_index(drop=True)
    if len(df) < 10:
        sys.exit("有效資料列太少 (< 10)，請確認檔案格式")
    return df


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path")
    ap.add_argument("--tick-ms", type=float, default=1.0, help="tick 每 1 單位幾 ms (預設 1)")
    ap.add_argument("--tail-s", type=float, default=3.0, help="取最後幾秒當穩態區間 (預設 3)")
    ap.add_argument("--jump-thr", type=float, default=0.1,
                    help="積分項單拍變化與 Ki*err 差超過多少 %% 就列為異常 (預設 0.1)")
    ap.add_argument("--png", default="speed_log_analysis.png")
    a = ap.parse_args()

    df = load_log(a.path)
    df["t"] = (df["tick"] - df["tick"].iloc[0]) * a.tick_ms / 1000.0
    Ts = float(df["t"].diff().median())

    # ── 0. 找步階、切出分析區間 ───────────────────────────────
    chg = np.where(df["target_rpm"].diff().abs() > 0)[0]
    if len(chg) == 0:
        sys.exit("target_rpm 從頭到尾都沒變，找不到步階")
    i0 = int(chg[0])
    nxt = int(chg[1]) if len(chg) > 1 else len(df)
    tgt = float(df["target_rpm"].iloc[i0])
    y0 = float(df["actual_rpm"].iloc[max(i0 - 1, 0)])
    step = tgt - y0
    s = 1 if step > 0 else -1
    seg = df.iloc[i0:nxt].reset_index(drop=True)
    tt = seg["t"].to_numpy() - seg["t"].iloc[0]
    y = seg["actual_rpm"].to_numpy()
    duty = seg["duty"].to_numpy()

    # ── 1. 步階響應指標 ──────────────────────────────────────
    t_first = next((tt[k] for k in range(len(y)) if abs(y[k] - y0) > 0.01 * abs(step)), None)
    t10 = cross(tt, s * y, s * (y0 + 0.1 * step))
    t90 = cross(tt, s * y, s * (y0 + 0.9 * step))
    t_hit = cross(tt, s * y, s * tgt)
    ipk = int(np.argmax(s * y))
    peak, t_pk = float(y[ipk]), float(tt[ipk])
    os_pct = max(0.0, s * (peak - tgt) / abs(step) * 100)
    tail = seg[seg["t"] >= seg["t"].iloc[-1] - a.tail_s]
    e_tail = tgt - tail["actual_rpm"]

    # ── 2. 一致性檢查、反推 PI 參數 ───────────────────────────
    has_ccr = {"ccr", "per"} <= set(df.columns)
    ccr_err = float((df["ccr"] - df["duty"] / 100 * df["per"]).abs().max()) if has_ccr else None
    P = duty - seg["ff"].to_numpy() - seg["integral"].to_numpy()   # P 項 (log 沒有直接記)
    err = tgt - y
    dI = seg["integral"].diff().to_numpy()
    ff_end = seg["ff"].iloc[-1]
    # ff 斜坡已結束、速度讀值有效 (PI 有作用) 的列，才拿來估參數
    ok = (np.abs(seg["ff"].to_numpy() - ff_end) < 0.006) & (y > 0) & ~np.isnan(dI)
    Kp = (P[ok] * err[ok]).sum() / (err[ok] ** 2).sum()
    ki_tick = (dI[ok] * err[ok]).sum() / (err[ok] ** 2).sum()
    for _ in range(2):  # 剔除離群點後再估一次
        good = ok & (np.abs(dI - ki_tick * err) < a.jump_thr)
        ki_tick = (dI[good] * err[good]).sum() / (err[good] ** 2).sum()
    Ki = ki_tick / Ts
    jumps = np.where(ok & (np.abs(dI - ki_tick * err) >= a.jump_thr))[0]
    recon = seg["ff"].to_numpy() + Kp * err + seg["integral"].to_numpy()
    duty_res = float(np.abs(duty - recon)[ok].max())

    # 由 P 項反推控制器「實際使用的 setpoint」(若 ≠ target，代表有斜坡/濾波)
    live = y > 0
    sp_impl = np.where(live, y + P / Kp, np.nan)
    r = live & (sp_impl > 0.05 * tgt) & (sp_impl < 0.95 * tgt)
    ramp = np.polyfit(tt[r], sp_impl[r], 1)[0] if r.sum() >= 3 else None

    # ── 3. 起轉與積分飽和 ────────────────────────────────────
    k10 = next((k for k in range(len(y)) if s * y[k] >= s * (y0 + 0.1 * step)), None)
    odd = []
    if k10:
        odd = [k for k in range(1, k10)
               if y[k] > 0 and y[k - 1] > 0 and y[k] < y[k - 1] and duty[k] > duty[k - 1]]

    # ── 報告 ─────────────────────────────────────────────────
    line = "=" * 64
    print(line)
    print(f"樣本 {len(df)} 筆，取樣週期 {Ts * 1000:.0f} ms；"
          f"步階在 tick {int(seg['tick'][0])}：{y0:g} → {tgt:g} rpm")
    print(line)
    print("【1. 步階響應】(時間從步階那一拍起算)")
    print(f"  第一次讀到速度    : {f(t_first)}")
    rise = t90 - t10 if (t10 is not None and t90 is not None) else None
    print(f"  10% / 90% 穿越    : {f(t10)} / {f(t90)}   上升時間 {f(rise)}")
    print(f"  第一次到達目標    : {f(t_hit)}")
    print(f"  峰值 / 過衝       : {peak:.1f} rpm @ {t_pk:.2f} s / {os_pct:.1f}%")
    for p in (5, 2, 1):
        print(f"  安定時間 ±{p}%     : {f(settle(tt, y, tgt, p))}")
    print(f"  最後 {a.tail_s:g} s        : 平均誤差 {e_tail.mean():+.1f} rpm "
          f"({e_tail.mean() / tgt * 100:+.2f}%)，"
          f"範圍 {tail['actual_rpm'].min():.1f} ~ {tail['actual_rpm'].max():.1f} rpm")

    print("\n【2. 一致性檢查 / 反推 PI】")
    print("  ccr 與 duty*per/100 最大差 : "
          + (f"{ccr_err:.2f} count" if ccr_err is not None else "N/A (沒有 ccr/per 欄)"))
    print(f"  Kp ≈ {Kp:.5f} %/rpm    Ki ≈ {Ki:.5f} %/(rpm·s)    Ti = Kp/Ki ≈ {Kp / Ki:.2f} s")
    print(f"  duty ≈ ff + Kp*err + I 的最大殘差 : {duty_res:.3f} %")
    if ramp:
        print(f"  由 P 項反推的 setpoint 斜率 ≈ {ramp:.0f} rpm/s "
              f"(控制器用的不是 target 階躍，是斜坡化後的 setpoint)")
    if len(jumps):
        print("  積分項出現 Ki*err 解釋不了的跳變：")
        for j in jumps:
            prev = seg["integral"][j - 1]
            ratio = f"{seg['integral'][j] / prev:.2f}" if prev else "n/a"
            print(f"    tick {int(seg['tick'][j])}: ΔI = {dI[j]:+.2f}，Ki*err 只預期 {ki_tick * err[j]:+.3f}，"
                  f"前後比 {ratio}")

    print("\n【3. 起轉 / 積分飽和】")
    if k10:
        I_before = float(seg["integral"].iloc[k10 - 1])
        I_peak = float(seg["integral"].max())
        print(f"  速度過 10% 那拍的 duty = {duty[k10]:.2f}%；"
              f"末段穩態 duty ≈ {tail['duty'].mean():.2f}% (ff 末值 {ff_end:.2f}%)")
        print(f"  起轉前積分項已累積 {I_before:.2f}% / 峰值 {I_peak:.2f}% "
              f"({I_before / I_peak * 100:.0f}%)")
    if odd:
        ticks = ", ".join(str(int(seg['tick'][k])) for k in odd)
        print(f"  速度讀值下降但 duty 在上升 (疑似低速量測假象) 的 tick: {ticks}")

    # ── 圖 ───────────────────────────────────────────────────
    T = (df["t"] - df["t"].iloc[i0]).to_numpy()
    Tg = T[i0:nxt]
    fig, ax = plt.subplots(3, 1, figsize=(10, 9), sharex=True)

    ax[0].plot(T, df["target_rpm"], "k--", lw=1, label="target")
    ax[0].plot(Tg, sp_impl, ":", color="tab:green", lw=2.2, label="implied setpoint (actual + P/Kp)")
    ax[0].plot(T, df["actual_rpm"], color="tab:blue", lw=1.8, label="actual")
    ax[0].axhspan(tgt * 0.98, tgt * 1.02, color="gray", alpha=0.15, label="±2% band")
    ax[0].annotate(f"peak {peak:.0f} rpm (+{os_pct:.1f}%)", (t_pk, peak), xytext=(12, 6),
                   textcoords="offset points", arrowprops=dict(arrowstyle="->"))
    ax[0].set_ylabel("speed [rpm]")
    ax[0].set_ylim(top=max(peak, tgt) * 1.15)   # 留空間給峰值標註

    ax[1].plot(T, df["duty"], "k", lw=1.8, label="duty")
    ax[1].plot(T, df["ff"], label="ff")
    ax[1].plot(Tg, P, label="P = duty - ff - I")
    ax[1].plot(T, df["integral"], label="integral")
    ax[1].set_ylabel("duty [%]")

    ax[2].fill_between(Tg, 0, err, color="tab:orange", alpha=0.3, label="error = target - actual")
    ax[2].set_ylabel("error [rpm]")
    ax2 = ax[2].twinx()
    ax2.plot(T, df["integral"], color="tab:red", lw=1.8, label="integral (right axis)")
    ax2.set_ylabel("integral [%]")
    h1, l1 = ax[2].get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax[2].legend(h1 + h2, l1 + l2, loc="upper right", fontsize=8)
    ax[2].set_xlabel("time since step [s]")

    for k, axis in enumerate(ax):
        axis.grid(alpha=0.3)
        if t10 is not None:
            axis.axvline(t10, color="tab:red", ls=":", lw=1,
                         label="speed passes 10%" if k == 0 else None)
        for j in jumps:
            axis.axvline(Tg[j], color="m", ls="--", lw=1,
                         label="integral jump" if (k == 0 and j == jumps[0]) else None)
        if k < 2:
            axis.legend(loc="lower right" if k == 0 else "upper right", fontsize=8)
    fig.tight_layout()
    fig.savefig(a.png, dpi=130)
    print(f"\n圖已存到 {a.png}")


if __name__ == "__main__":
    main()
