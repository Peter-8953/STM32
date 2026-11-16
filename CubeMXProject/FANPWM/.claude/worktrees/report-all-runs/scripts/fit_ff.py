# -*- coding: utf-8 -*-
from pathlib import Path
import re, numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[1]
from scipy.interpolate import PchipInterpolator

# parse latest calibration points from capture
pts=set()
with open(ROOT / 'logs' / 'COM4_2026_10_31.11.12.32.612.csv',encoding='utf-8',errors='ignore') as f:
    for line in f:
        m=re.search(r'CAL \d+/\d+ duty=([\d.]+)% rpm=([\d.]+)', line)
        if m:
            pts.add((float(m.group(1)),float(m.group(2))))
data=sorted(pts)
duty=np.array([p[0] for p in data])
rpm=np.array([p[1] for p in data])
print('cal points:'); [print(f'  {d:5.1f}% -> {r:7.1f} RPM') for d,r in zip(duty,rpm)]

# enforce monotonic
for i in range(1,len(rpm)):
    if rpm[i]<rpm[i-1]: rpm[i]=rpm[i-1]

# fits
coef2=np.polyfit(duty,rpm,2)
coef3=np.polyfit(duty,rpm,3)
print('\npoly2 coeffs (highest first):', coef2)
print('poly3 coeffs:', coef3)

# dense interpolation
pchip=PchipInterpolator(duty,rpm)  # monotonic cubic
dense_duty=np.arange(0,101,1.0)
dense_rpm=pchip(dense_duty)
dense_rpm=np.clip(dense_rpm,0,None)

# inverse feedforward: target RPM -> duty (monotonic). Use PCHIP rpm->duty
ur, ui = np.unique(rpm, return_index=True)
inv_pchip=PchipInterpolator(rpm[ui], duty[ui])
def ff_duty(r):
    r=np.clip(r,rpm[0],rpm[-1])
    return float(inv_pchip(r))

# write CSVs
import os
OUT = ROOT / 'data' / 'output'
os.makedirs(OUT,exist_ok=True)
pd.DataFrame({'duty_percent':dense_duty,'rpm_fit':dense_rpm}).to_csv(OUT / 'ff_duty_to_rpm_dense.csv',index=False)
# sample target RPMs (full 0..100% in ~417 RPM increments)
full=4167.3
targets=np.linspace(0,full,11)
inv=pd.DataFrame({'target_rpm':targets,'feedforward_duty_pct':[ff_duty(t) for t in targets]})
inv.to_csv(OUT / 'ff_rpm_to_duty.csv',index=False)

print('\nDense interpolation sample (every 10%):')
for i in range(0,101,10):
    print(f'  duty {i:3d}% -> {dense_rpm[i]:7.1f} RPM')
print('\nFeedforward sample (every 10% of max RPM):')
print(inv.to_string(index=False,float_format='{:.2f}'.format))
print('\nSaved fan_output/ff_duty_to_rpm_dense.csv and ff_rpm_to_duty.csv')
