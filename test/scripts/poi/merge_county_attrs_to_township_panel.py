# -*- coding: utf-8 -*-
"""
将 2023 年初区县矢量（cp936）属性按「乡镇 code 前 6 位 = 区县 code」并入乡镇 POI 面板 CSV。

默认：
  面板：test/township_poi_panel_2012_2021_wide.csv
  区县 shp：…\\2023区县级\\2023年初区县矢量cp936.shp

匹配：str(code) 取前 6 位 → 与 shapefile 的 code（县级）相等。
区县表按 code 去重后左连接；未匹配行区县列为空。

用法：
  python merge_county_attrs_to_township_panel.py
  python merge_county_attrs_to_township_panel.py -o out.csv
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd


# 并入时排除的 shapefile 字段（英文/GADM 层级等，减小面板体积）
COUNTY_DROP_ATTRS = (
    "ENG_NAME",
    "VAR_NAME",
    "NAME_3",
    "VAR_NAME3",
    "GID_3",
    "TYPE_3",
    "NAME_2",
    "VAR_NAME2",
    "GID_2",
    "TYPE_2",
    "NAME_1",
    "VAR_NAME1",
    "GID_1",
    "TYPE_1",
)


def norm_township_code(v: object) -> str:
    s = str(v).strip()
    if re.fullmatch(r"\d+\.0", s):
        s = s[:-2]
    if s.endswith(".0") and s.replace(".0", "").isdigit():
        s = s[:-2]
    return s


def main() -> None:
    test_dir = Path(__file__).resolve().parent.parent.parent
    default_panel = test_dir / "township_poi_panel_2012_2021_wide.csv"
    default_shp = (
        r"F:\BaiduNetdiskDownload\四级矢量地图\21.县乡镇四级矢量数据"
        r"\shp格式\2023区县级\2023年初区县矢量cp936.shp"
    )

    ap = argparse.ArgumentParser(description="乡镇面板并入区县矢量属性（前六位匹配）")
    ap.add_argument("--panel", "-p", default=str(default_panel), help="乡镇面板 CSV")
    ap.add_argument("--county-shp", default=default_shp, help="区县 shapefile")
    ap.add_argument(
        "-o",
        "--output",
        default=None,
        help="输出 CSV（默认覆盖 --panel）",
    )
    args = ap.parse_args()

    panel_path = Path(args.panel)
    out_path = Path(args.output) if args.output else panel_path

    print("读取区县矢量 …", flush=True)
    gdf = gpd.read_file(args.county_shp, encoding="gbk")
    county = gdf.drop(columns=["geometry"], errors="ignore")
    if "code" not in county.columns:
        print("shapefile 无 code 列", file=sys.stderr)
        sys.exit(1)
    county["code"] = pd.to_numeric(county["code"], errors="coerce").astype("Int64")
    county = county.dropna(subset=["code"])
    county["code"] = county["code"].astype(int)
    county = county.drop_duplicates(subset=["code"], keep="first")
    county = county.drop(
        columns=[c for c in COUNTY_DROP_ATTRS if c in county.columns],
        errors="ignore",
    )

    rename = {c: f"区县_{c}" for c in county.columns if c != "code"}
    county_r = county.rename(columns=rename)
    county_r = county_r.rename(columns={"code": "区县code"})

    print(f"  区县面去重后行数: {len(county_r)}", flush=True)

    print("读取乡镇面板 …", flush=True)
    df = pd.read_csv(panel_path, encoding="utf-8-sig", dtype=str, low_memory=False)
    if "code" not in df.columns:
        print("面板无 code 列", file=sys.stderr)
        sys.exit(1)

    df["_前六位"] = df["code"].map(norm_township_code).str[:6]
    df["_区县匹配码"] = pd.to_numeric(df["_前六位"], errors="coerce")
    bad = df["_区县匹配码"].isna().sum()
    if bad:
        print(f"  警告：{bad} 行 code 前六位无法转整数", flush=True)
    df["_区县匹配码"] = df["_区县匹配码"].astype("Int64")

    merged = df.merge(
        county_r,
        left_on="_区县匹配码",
        right_on="区县code",
        how="left",
    )
    merged = merged.drop(columns=["_前六位", "_区县匹配码", "区县code"], errors="ignore")

    ref_col = "区县_地名" if "区县_地名" in merged.columns else (
        [c for c in merged.columns if c.startswith("区县_")][0] if any(c.startswith("区县_") for c in merged.columns) else None
    )
    n_miss = int(merged[ref_col].isna().sum()) if ref_col else 0
    print(f"  未匹配到区县的行数: {n_miss} / {len(merged)}", flush=True)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"已写入: {out_path}", flush=True)


if __name__ == "__main__":
    main()
