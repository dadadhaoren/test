# -*- coding: utf-8 -*-
"""
将稀疏的「年份×乡镇×n」企业计数表扩展为**平衡面板**（与 POI 脚本中 `township_skeleton` 思路一致）：

- 乡镇全集来自 `township_county_division_2023.csv`（唯一 `code`）；
- 年份区间为 **[year-min, year-max]**（默认 **2012–2021**，与 `township_poi_panel_2012_2021_wide` 对齐）；
- 左连接实际计数，**无记录补 n=0**；
- 区划名随乡镇带出。

默认输入：稀疏长表 `township_enterprise_counts_by_year.csv`（仅需 年份、code、n；也可用带区划版，脚本只取三列）。
默认输出：`test/township_enterprise_panel_balanced_2012_2021.csv`

用法：
  python 05_balance_township_enterprise_panel.py
  python 05_balance_township_enterprise_panel.py --year-min 2000 --year-max 2024 -o out.csv
"""

from __future__ import annotations

import argparse
import re
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
    default_division = test_dir / "township_county_division_2023.csv"
    default_sparse = test_dir / "township_enterprise_counts_by_year.csv"
    default_out = test_dir / "township_enterprise_panel_balanced_2012_2021.csv"

    ap = argparse.ArgumentParser(description="企业乡镇计数 → 平衡面板（年份×乡镇全集，缺补0）")
    ap.add_argument("-i", "--sparse-csv", default=str(default_sparse), help="稀疏长表（含 年份、code、n）")
    ap.add_argument("-d", "--division-csv", default=str(default_division), help="乡镇区划全集")
    ap.add_argument("--year-min", type=int, default=2012)
    ap.add_argument("--year-max", type=int, default=2021)
    ap.add_argument("-o", "--output", default=str(default_out), help="平衡面板输出 CSV")
    args = ap.parse_args()

    if args.year_min > args.year_max:
        raise SystemExit("year-min 不能大于 year-max")

    years = list(range(args.year_min, args.year_max + 1))
    print(f"年份范围: {args.year_min}–{args.year_max}（共 {len(years)} 年）", flush=True)

    print("读取乡镇区划（全集）…", flush=True)
    div = pd.read_csv(args.division_csv, encoding="utf-8-sig", dtype=str, low_memory=False)
    div["code"] = div["code"].map(norm_code)
    div = div.drop_duplicates(subset=["code"], keep="first")
    n_town = len(div)
    print(f"  乡镇数: {n_town}", flush=True)

    years_df = pd.DataFrame({"年份": years})
    div_k = div.assign(_k=1)
    y_k = years_df.assign(_k=1)
    skel = div_k.merge(y_k, on="_k").drop(columns="_k")
    skel["年份"] = skel["年份"].astype(int)
    print(f"  平衡面板行数（骨架）: {len(skel)} = {n_town} × {len(years)}", flush=True)

    print("读取稀疏计数 …", flush=True)
    sparse = pd.read_csv(args.sparse_csv, encoding="utf-8-sig", dtype=str, low_memory=False)
    if "年份" not in sparse.columns or "code" not in sparse.columns or "n" not in sparse.columns:
        raise SystemExit("稀疏表需含列: 年份, code, n")
    sparse = sparse[["年份", "code", "n"]].copy()
    sparse["code"] = sparse["code"].map(norm_code)
    sparse["年份"] = pd.to_numeric(sparse["年份"], errors="coerce").astype("Int64")
    sparse = sparse.dropna(subset=["年份"])
    sparse["年份"] = sparse["年份"].astype(int)
    sparse["n"] = pd.to_numeric(sparse["n"], errors="coerce").fillna(0).astype("int64")
    # 仅保留面板年份内的观测，避免重复键
    sparse = sparse[
        (sparse["年份"] >= args.year_min) & (sparse["年份"] <= args.year_max)
    ]
    # 同年同镇多条则求和（理论上不应有）
    sparse = sparse.groupby(["年份", "code"], as_index=False)["n"].sum()
    print(f"  稀疏观测（面板年内）: {len(sparse)} 行", flush=True)

    out = skel.merge(sparse, on=["年份", "code"], how="left")
    out["n"] = out["n"].fillna(0).astype("int64")

    # 列顺序与 04_merge_division_to_enterprise_counts 一致
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
    xiang = sorted(c for c in out.columns if c.startswith("乡镇_"))
    qu = [c for c in preferred_qu if c in out.columns]
    qu_extra = sorted(c for c in out.columns if c.startswith("区县_") and c not in qu)
    # 与 POI 面板一致：年份、code、Name、n 在前，便于 Excel 查看
    head = ["年份", "code", "Name", "n"] if "Name" in out.columns else ["年份", "code", "n"]
    head = [c for c in head if c in out.columns]
    head += xiang + qu + qu_extra
    tail = [c for c in out.columns if c not in head]
    out = out[head + tail]

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"已写入: {out_path}（{len(out)} 行）", flush=True)


if __name__ == "__main__":
    main()
