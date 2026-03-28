# -*- coding: utf-8 -*-
"""
由「乡镇边界」+「2023 年初区县矢量」整合为**仅区划属性**的乡镇级表（无 POI），
区县字段命名与 `merge_county_attrs_to_township_panel.py` / `township_poi_panel_*_wide.csv` 一致（`区县_*`）。

匹配规则：乡镇 `code` 字符串取前 6 位 → 与区县 shapefile 的县级 `code` 相等；区县按 `code` 去重。

默认路径：
  区县：…\\2023区县级\\2023年初区县矢量cp936.shp（gbk）
  乡镇：…\\全国乡镇边界（合集）\\乡镇级行政区划合集.shp

输出默认：test/township_county_division_2023.csv（utf-8-sig，不含 geometry）

用法：
  python build_township_county_division_table.py
  python build_township_county_division_table.py -o out.csv
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

# 与 merge_county_attrs_to_township_panel.py 一致
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


def read_county_attrs(county_shp: str, encoding: str) -> pd.DataFrame:
    gdf = gpd.read_file(county_shp, encoding=encoding)
    county = gdf.drop(columns=["geometry"], errors="ignore")
    if "code" not in county.columns:
        raise ValueError("区县 shapefile 需包含列 code")
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
    return county_r


def read_township_attrs(township_shp: str) -> pd.DataFrame:
    last_err: Exception | None = None
    gdf = None
    for enc in ("utf-8", "gb18030", "gbk", None):
        try:
            gdf = gpd.read_file(township_shp, encoding=enc)
            break
        except Exception as e:
            last_err = e
    if gdf is None:
        raise last_err  # type: ignore[misc]
    tw = gdf.drop(columns=["geometry"], errors="ignore")
    if "code" not in tw.columns or "Name" not in tw.columns:
        raise ValueError("乡镇 shapefile 需包含列 code、Name")
    # 与 POI 脚本一致：主键列名 code、Name；其余加 乡镇_ 前缀以免与区县列混淆
    extra = [c for c in tw.columns if c not in ("code", "Name")]
    ren = {c: f"乡镇_{c}" for c in extra}
    tw = tw.rename(columns=ren)
    tw = tw.drop_duplicates(subset=["code"], keep="first")
    return tw


def main() -> None:
    test_dir = Path(__file__).resolve().parent.parent.parent
    default_county = (
        r"F:\BaiduNetdiskDownload\四级矢量地图\21.县乡镇四级矢量数据"
        r"\shp格式\2023区县级\2023年初区县矢量cp936.shp"
    )
    default_township = (
        r"F:\BaiduNetdiskDownload\四级矢量地图\21.县乡镇四级矢量数据"
        r"\shp格式\全国乡镇边界（合集）\乡镇级行政区划合集.shp"
    )
    default_out = test_dir / "township_county_division_2023.csv"

    ap = argparse.ArgumentParser(description="乡镇+区县矢量整合为区划属性表（前六位匹配）")
    ap.add_argument("--county-shp", default=default_county, help="区县 shapefile（默认 cp936/gbk）")
    ap.add_argument("--county-encoding", default="gbk", help="区县矢量编码")
    ap.add_argument("--township-shp", default=default_township, help="乡镇 shapefile")
    ap.add_argument("-o", "--output", default=str(default_out), help="输出 CSV")
    args = ap.parse_args()

    print("读取区县矢量 …", flush=True)
    county_r = read_county_attrs(args.county_shp, args.county_encoding)
    print(f"  区县去重后: {len(county_r)} 行", flush=True)

    print("读取乡镇矢量 …", flush=True)
    tw = read_township_attrs(args.township_shp)
    print(f"  乡镇去重后: {len(tw)} 行", flush=True)

    tw = tw.copy()
    tw["_前六位"] = tw["code"].map(norm_township_code).str[:6]
    tw["_区县匹配码"] = pd.to_numeric(tw["_前六位"], errors="coerce")
    bad = tw["_区县匹配码"].isna().sum()
    if bad:
        print(f"  警告：{bad} 行乡镇 code 前六位无法转整数", flush=True)
    tw["_区县匹配码"] = tw["_区县匹配码"].astype("Int64")

    merged = tw.merge(
        county_r,
        left_on="_区县匹配码",
        right_on="区县code",
        how="left",
    )
    merged = merged.drop(columns=["_前六位", "_区县匹配码", "区县code"], errors="ignore")

    ref_col = "区县_地名" if "区县_地名" in merged.columns else (
        [c for c in merged.columns if c.startswith("区县_")][0]
        if any(c.startswith("区县_") for c in merged.columns)
        else None
    )
    n_miss = int(merged[ref_col].isna().sum()) if ref_col else 0
    print(f"  未匹配到区县的乡镇行: {n_miss} / {len(merged)}", flush=True)

    # 列顺序：code、Name → 乡镇_*（字母序）→ 区县_*（与 township_poi_panel_*_wide 中区县字段顺序一致，其余列殿后）
    xiang = sorted(c for c in merged.columns if c.startswith("乡镇_"))
    qu_all = [c for c in merged.columns if c.startswith("区县_")]
    preferred = [
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
    qu = [c for c in preferred if c in qu_all] + sorted(
        c for c in qu_all if c not in preferred
    )
    rest = [c for c in merged.columns if c not in ("code", "Name") and c not in xiang and c not in qu_all]
    merged = merged[["code", "Name"] + xiang + qu + rest]

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"已写入: {out_path}（{len(merged)} 行）", flush=True)


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
