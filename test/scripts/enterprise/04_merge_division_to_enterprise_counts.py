# -*- coding: utf-8 -*-
"""
将 `township_enterprise_counts_by_year.csv`（年份×乡镇 code×n）并入
`township_county_division_2023.csv` 中的乡镇名与省/市/县各级区划字段（与 POI 面板并入区县属性口径一致）。

匹配：**乡镇 code** 与区划表 **code** 相等（字符串规范化后）。

默认输出：`test/township_enterprise_counts_by_year_with_division.csv`

用法：
  python 04_merge_division_to_enterprise_counts.py
  python 04_merge_division_to_enterprise_counts.py -i counts.csv -d division.csv -o out.csv
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd


def norm_code(v: object) -> str:
    s = str(v).strip()
    if re.fullmatch(r"\d+\.0", s):
        s = s[:-2]
    if s.endswith(".0") and s.replace(".0", "").isdigit():
        s = s[:-2]
    return s


def main() -> None:
    test_dir = Path(__file__).resolve().parent.parent.parent
    default_counts = test_dir / "township_enterprise_counts_by_year.csv"
    default_division = test_dir / "township_county_division_2023.csv"
    default_out = test_dir / "township_enterprise_counts_by_year_with_division.csv"

    ap = argparse.ArgumentParser(description="企业乡镇计数表并入区划名（乡镇+区县各级）")
    ap.add_argument("-i", "--counts", default=str(default_counts), help="年份×code×n CSV")
    ap.add_argument(
        "-d",
        "--division-csv",
        default=str(default_division),
        help="乡镇区划表（含 Name、区县_*）",
    )
    ap.add_argument("-o", "--output", default=str(default_out), help="输出 CSV")
    args = ap.parse_args()

    print("读取企业计数 …", flush=True)
    cnt = pd.read_csv(args.counts, encoding="utf-8-sig", dtype=str, low_memory=False)
    cnt["code"] = cnt["code"].map(norm_code)
    if "n" in cnt.columns:
        cnt["n"] = pd.to_numeric(cnt["n"], errors="coerce").fillna(0).astype("int64")
    if "年份" in cnt.columns:
        cnt["年份"] = pd.to_numeric(cnt["年份"], errors="coerce").astype("Int64")

    print("读取乡镇区划表 …", flush=True)
    div = pd.read_csv(args.division_csv, encoding="utf-8-sig", dtype=str, low_memory=False)
    div["code"] = div["code"].map(norm_code)
    div = div.drop_duplicates(subset=["code"], keep="first")

    # 区划侧除 code 外的列
    div_cols = [c for c in div.columns if c != "code"]

    merged = cnt.merge(div, on="code", how="left")

    # 列顺序：年份、code、n、Name、乡镇_*、区县_*（与 township_county_division_2023 / POI 并入习惯一致）
    preferred_qu = [
        "区县_地名",
        "区县_区划码",
        "区县_县级",
        "区县_县级码",
        "区县_县级类",
        "区县_地级",
        "区县_地级码",
        "区县_地级类",
        "区县_省级",
        "区县_省级码",
        "区县_省级类",
        "区县_曾用名",
        "区县_备注",
        "区县_year",
    ]
    xiang = sorted(c for c in merged.columns if c.startswith("乡镇_"))
    qu = [c for c in preferred_qu if c in merged.columns]
    qu_extra = sorted(
        c for c in merged.columns if c.startswith("区县_") and c not in qu
    )
    head = ["年份", "code", "n"]
    if "Name" in merged.columns:
        head.append("Name")
    head += xiang + qu + qu_extra
    tail = [c for c in merged.columns if c not in head]
    merged = merged[head + tail]

    ref = "区县_地名" if "区县_地名" in merged.columns else None
    n_miss = int(merged[ref].isna().sum()) if ref else 0
    print(f"  行数: {len(merged)}，未匹配到区划的乡镇行: {n_miss}", flush=True)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"已写入: {out_path}", flush=True)


if __name__ == "__main__":
    main()
