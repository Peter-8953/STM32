# -*- coding: utf-8 -*-
"""
從風速計 log（real12START_3CM.xls）配合 sweep_table 的 60 秒/步，
分段計算每一個 PWM duty 對應的穩定段風速（取每步最後 30 秒），
輸出 CSV：PWM duty / RPM / 風速 (up & down)。
"""
from pathlib import Path
import os
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data' / 'output'
import pandas as pd, datetime as dt

# sweep table (must match Core/Src/fan_sweep.c)
sweep = [
  (0,60),(12,60),(20,60),(30,60),(40,60),(50,60),(60,60),(70,60),(80,60),(90,60),
  (100,120),(90,60),(80,60),(70,60),(60,60),(50,60),(40,60),(30,60),(20,60),(12,60),
]

# RPM mapping from CAL measurement (source: Core test log / existing fan_output/rpm_pwm_wind.csv)
rpm_map = {0:0,12:509,20:1042,30:1795,40:2221,50:2629,60:3007,
           70:3378,80:3763,90:4038,100:4309}

# read wind
xl = pd.ExcelFile(ROOT / 'data' / 'real12START_3CM.xls')
df = xl.parse('Report')
df.columns = [str(c).strip() for c in df.columns]
df = df[df['Function'].astype(str).str.strip()=='VEL'].copy()
df['windspeed'] = pd.to_numeric(df['Value'].astype(str).str.strip().str.replace('m/s','',regex=False), errors='coerce')
df = df.dropna(subset=['windspeed'])

def _td(v):
    if isinstance(v,(dt.datetime,dt.time)):
        t = v.time() if isinstance(v,dt.datetime) else v
        return pd.Timedelta(hours=t.hour,minutes=t.minute,seconds=t.second,microseconds=t.microsecond)
    if isinstance(v,(int,float)) and not pd.isna(v):
        return pd.to_timedelta(float(v),unit='D')
    try: return pd.to_timedelta(str(v).strip())
    except Exception: return pd.NaT

df['timestamp'] = pd.to_datetime(df['Date'],errors='coerce').dt.normalize() + df['Time'].map(_td)
df = df.dropna(subset=['timestamp']).sort_values('timestamp').reset_index(drop=True)

# align start to first zero plateau start
t0 = pd.Timestamp('2026-10-11 18:07:00')

rows = []
cursor = t0
occurrence = {}  # duty -> count
for duty, dwell in sweep:
    seg = df[(df['timestamp']>=cursor) & (df['timestamp']<cursor+pd.Timedelta(seconds=dwell))]
    stable = seg[seg['timestamp'] >= cursor+pd.Timedelta(seconds=dwell-30)]
    if len(stable)==0:
        stable = seg
    occ = occurrence.get(duty,0)+1
    occurrence[duty]=occ
    direction = 'up' if occ==1 else 'down'
    rows.append({
        'step': len(rows)+1,
        'direction': direction,
        'duty_pct': float(duty),
        'rpm': rpm_map.get(duty, None),
        'wind_mps_mean': stable['windspeed'].mean(),
        'wind_mps_std': stable['windspeed'].std(),
        'n_samples': len(stable),
        'window_start': cursor.strftime('%Y-%m-%d %H:%M:%S'),
        'window_end': (cursor+pd.Timedelta(seconds=dwell)).strftime('%Y-%m-%d %H:%M:%S'),
    })
    cursor = cursor + pd.Timedelta(seconds=dwell)

out = pd.DataFrame(rows)
# build compact up/down relation per duty
rel = []
for duty in sorted(set(d for d,_ in sweep)):
    ups = out[(out.duty_pct==duty)&(out.direction=='up')]
    downs = out[(out.duty_pct==duty)&(out.direction=='down')]
    w_up = ups.wind_mps_mean.iloc[0] if len(ups) else None
    w_down = downs.wind_mps_mean.iloc[0] if len(downs) else None
    hyst = (w_up-w_down) if (w_up is not None and w_down is not None) else None
    rel.append({
        'duty_pct': duty,
        'rpm': rpm_map.get(duty,None),
        'wind_up_mps': w_up,
        'wind_down_mps': w_down,
        'hysteresis_mps': hyst,
    })
rel_df = pd.DataFrame(rel).sort_values('duty_pct')

os.makedirs(OUT, exist_ok=True)
out.to_csv(OUT / 'fan_test_steps.csv', index=False)
rel_df.to_csv(OUT / 'pwm_rpm_wind_relation.csv', index=False)

print('===== 逐步風速 (每步穩定段) =====')
print(out[['step','direction','duty_pct','rpm','wind_mps_mean','n_samples']].to_string(index=False,float_format='{:.3f}'.format))
print('\n===== PWM / RPM / 風速 對照表 =====')
print(rel_df.to_string(index=False,float_format='{:.4f}'.format))
print('\n輸出：')
print('  fan_output/fan_test_steps.csv')
print('  fan_output/pwm_rpm_wind_relation.csv')
