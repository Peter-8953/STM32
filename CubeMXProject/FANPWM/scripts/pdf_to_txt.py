# -*- coding: utf-8 -*-
"""
純 Python PDF → TXT，不需 Poppler。
使用方式：pip install pypdf
           python pdf_to_txt.py
它會把 essay/*.pdf 全部輸出到 essay/txt/*.txt。
"""

import os
import glob
from pypdf import PdfReader

BASE = os.path.join(os.path.dirname(__file__), "essay")
TXT_DIR = os.path.join(BASE, "txt")
os.makedirs(TXT_DIR, exist_ok=True)

files = glob.glob(os.path.join(BASE, "*.pdf"))
if not files:
    print("essay 資料夾中找不到 PDF")
    raise SystemExit(1)

for path in sorted(files):
    try:
        reader = PdfReader(path)
        out_txt = os.path.join(TXT_DIR, os.path.basename(path) + ".txt")
        with open(out_txt, "w", encoding="utf-8") as fh:
            for i, page in enumerate(reader.pages, start=1):
                text = page.extract_text() or ""
                fh.write(f"\n===== PAGE {i} =====\n")
                fh.write(text + "\n")
        print(f"OK: {os.path.basename(path)} -> {out_txt}")
    except Exception as e:
        print(f"FAIL: {path} ({e})")

print("done")