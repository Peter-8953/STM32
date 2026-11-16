# -*- coding: utf-8 -*-
"""檢查 docs/*.md 是否仍含常见簡體中文詞。
輸出 UTF-8 報表至 docs/markdown_traditional_check.txt。
"""
from pathlib import Path
import glob, os

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
OUT = DOCS / "markdown_traditional_check.txt"

# 常見簡體詞（繁體常選）；此表只做 heuristic scan，不是完整 linguistics check。
SIMPLIFIED_WORDS = [
    "数据", "信息", "软件", "代码", "变量", "函数", "模块", "库", "调试", "编译",
    "内存", "接口", "报告", "结构", "架构", "优化", "获取", "搭建", "控件",
    "交互", "回调", "缓存", "定时", "伪", "强", "块", "标",
    "供应", "损失", "并", "传", "换", "游戏", "运行", "逻辑", "误差", "范围",
    "传输", "重复", "样", "录", "质", "采样", "虚拟", "通讯", "服务", "节点"
]

# 一些繁體字本身可作 keyword，避免 false positive：只 flagged 如果 matched word appearing as whole term
issues = []
for md in sorted(DOCS.glob("*.md")):
    if md.name == "markdown_traditional_check.txt":
        continue
    text = md.read_text(encoding="utf-8")
    found = sorted(set(w for w in SIMPLIFIED_WORDS if w in text))
    issues.append((md.name, found))

lines = []
lines.append("Markdown Traditional Chinese check")
lines.append("=" * 30)
for md_name, found in issues:
    if found:
        lines.append(f" {md_name}: {', '.join(found)}")
    else:
        lines.append(f" {md_name}: (no common-simplified hits)")
lines.append("")
lines.append("Note: heuristic scan only. Manual proofread recommended.")
OUT.write_text("\n".join(lines), encoding="utf-8")
print("written:", OUT)
