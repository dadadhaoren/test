# -*- coding: utf-8 -*-
"""
乡镇级 POI 面板（宽表）：按《公共产品供给分类标准》将 CATEGORY 与「小类」直接相等匹配，
映射到三个「一级类别」列，经 LON/LAT 与乡镇面空间连接后汇总。

默认处理 2012–2017 年；输出 CSV（utf-8-sig），列：
  年份, code, Name, 基本公共服务, 普惠性非基本公共服务, 生活服务

输出为**平衡面板**：乡镇边界内全部乡镇 × 所处理年份，无匹配 POI 或三列均为 0 的乡镇仍保留，三列记为 0。
Name、code 以乡镇矢量为准（与 POI 汇总按 code 对齐）。

用法：
  python township_poi_panel_wide.py
  python township_poi_panel_wide.py --output "D:\\out\\township_poi_2012_2017.csv"
  python township_poi_panel_wide.py --years 2013,2014 --chunk-size 150000
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

# 一级类别列名（与 CSV 中一致）
COL_BASIC = "基本公共服务"
COL_INCLUSIVE = "普惠性非基本公共服务"
COL_LIFE = "生活服务"
LEVEL_COLS = [COL_BASIC, COL_INCLUSIVE, COL_LIFE]


def find_poi_extracted(explicit: Optional[str]) -> str:
    if explicit:
        p = os.path.abspath(explicit)
        if not os.path.isdir(p):
            raise FileNotFoundError(p)
        return p
    base = r"F:\BaiduNetdiskDownload"
    if not os.path.isdir(base):
        raise FileNotFoundError(f"未找到数据目录: {base}")
    for path in glob.glob(os.path.join(base, "*")):
        if os.path.isdir(path) and "POI" in os.path.basename(path):
            return os.path.join(path, "poi_extracted")
    raise FileNotFoundError("在 BaiduNetdiskDownload 下未找到名称含 POI 的文件夹")


def load_category_map(csv_path: str) -> Tuple[Dict[str, str], Set[str]]:
    """小类 -> 一级类别；以及小类集合（用于过滤）。"""
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    if "一级类别" not in df.columns or "小类" not in df.columns:
        raise ValueError("分类标准 CSV 需包含列：一级类别、小类")
    df = df.dropna(subset=["小类"])
    df["小类"] = df["小类"].astype(str)
    df["一级类别"] = df["一级类别"].astype(str)
    m: Dict[str, str] = {}
    for _, r in df.iterrows():
        k = r["小类"]
        m[k] = r["一级类别"]
    xiaolei: Set[str] = set(m.keys())
    return m, xiaolei


def read_poi_shp_chunked(
    shp_path: str,
    xiaolei: Set[str],
    cat_to_level: Dict[str, str],
    chunk_size: int,
) -> Iterable[gpd.GeoDataFrame]:
    """按行块读取 POI shp，仅保留 CATEGORY 属于小类集合且坐标有效的点。"""
    encodings = ("utf-8", "gb18030")
    gdf0 = None
    enc_used = None
    for enc in encodings:
        try:
            gdf0 = gpd.read_file(shp_path, rows=1, encoding=enc)
            enc_used = enc
            break
        except Exception:
            continue
    if gdf0 is None:
        gdf0 = gpd.read_file(shp_path, rows=1)
        enc_used = None

    need = {"LON", "LAT", "CATEGORY"}
    if not need.issubset(set(gdf0.columns)):
        return

    skip = 0
    while True:
        try:
            if enc_used:
                chunk = gpd.read_file(
                    shp_path,
                    encoding=enc_used,
                    rows=slice(skip, skip + chunk_size),
                )
            else:
                chunk = gpd.read_file(shp_path, rows=slice(skip, skip + chunk_size))
        except Exception:
            try:
                chunk = gpd.read_file(
                    shp_path,
                    encoding="gb18030",
                    rows=slice(skip, skip + chunk_size),
                )
            except Exception:
                break
        if chunk is None or len(chunk) == 0:
            break

        if "CATEGORY" not in chunk.columns:
            break
        chunk = chunk[chunk["CATEGORY"].notna()].copy()
        chunk["CATEGORY"] = chunk["CATEGORY"].astype(str)
        chunk = chunk[chunk["CATEGORY"].isin(xiaolei)]
        if len(chunk) == 0:
            skip += chunk_size
            continue

        chunk["一级类别"] = chunk["CATEGORY"].map(cat_to_level)
        chunk = chunk[chunk["一级类别"].notna()]
        if len(chunk) == 0:
            skip += chunk_size
            continue

        for col in ("LON", "LAT"):
            chunk[col] = pd.to_numeric(chunk[col], errors="coerce")
        chunk = chunk[chunk["LON"].notna() & chunk["LAT"].notna()]
        if len(chunk) == 0:
            skip += chunk_size
            continue

        geom = [Point(xy) for xy in zip(chunk["LON"], chunk["LAT"])]
        out = gpd.GeoDataFrame(
            chunk[["一级类别"]].reset_index(drop=True),
            geometry=geom,
            crs="EPSG:4326",
        )
        yield out
        skip += chunk_size
        if len(chunk) < chunk_size:
            break


def load_townships(shp_path: str) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(shp_path)
    if gdf.crs is None:
        gdf.set_crs("EPSG:4326", inplace=True)
    else:
        gdf = gdf.to_crs("EPSG:4326")
    need = {"code", "Name", "geometry"}
    if not need.issubset(gdf.columns):
        raise ValueError(f"乡镇 shp 需含列 code, Name, geometry；当前为 {list(gdf.columns)}")
    return gdf[list(need)].copy()


def aggregate_year(
    year: int,
    poi_year_root: str,
    townships: gpd.GeoDataFrame,
    xiaolei: Set[str],
    cat_to_level: Dict[str, str],
    chunk_size: int,
    max_shp: Optional[int],
) -> pd.DataFrame:
    pattern = os.path.join(poi_year_root, "*.shp")
    shps = sorted(glob.glob(pattern))
    if max_shp is not None:
        shps = shps[: max_shp]

    parts: List[pd.DataFrame] = []
    for shp in shps:
        for pts in read_poi_shp_chunked(shp, xiaolei, cat_to_level, chunk_size):
            if len(pts) == 0:
                continue
            joined = pts.sjoin(
                townships,
                how="inner",
                predicate="within",
            )
            if len(joined) == 0:
                continue
            joined = joined[~joined.index.duplicated(keep="first")]
            agg = (
                joined.groupby(["code", "一级类别"], as_index=False)
                .size()
                .rename(columns={"size": "n"})
            )
            agg["年份"] = year
            parts.append(agg)

    if not parts:
        return pd.DataFrame(
            columns=["年份", "code", "一级类别", "n"],
        )

    long_df = pd.concat(parts, ignore_index=True)
    long_df = (
        long_df.groupby(["年份", "code", "一级类别"], as_index=False)["n"]
        .sum()
    )
    return long_df


def long_to_wide(long_df: pd.DataFrame) -> pd.DataFrame:
    """长表 -> 宽表（仅 年份+code，不含 Name；Name 由平衡面板骨架提供）。"""
    if long_df.empty:
        return pd.DataFrame(columns=["年份", "code"] + LEVEL_COLS)
    wide = long_df.pivot_table(
        index=["年份", "code"],
        columns="一级类别",
        values="n",
        aggfunc="sum",
        fill_value=0,
    ).reset_index()
    for c in LEVEL_COLS:
        if c not in wide.columns:
            wide[c] = 0
        else:
            wide[c] = wide[c].fillna(0).astype("int64")
    wide = wide[["年份", "code"] + LEVEL_COLS]
    return wide


def township_skeleton(
    townships: gpd.GeoDataFrame,
    years: List[int],
) -> pd.DataFrame:
    """全部乡镇 × 全部年份，列：年份, code, Name。"""
    base = townships[["code", "Name"]].drop_duplicates(subset=["code"], keep="first")
    years_df = pd.DataFrame({"年份": years})
    skel = pd.merge(
        base.assign(_k=1),
        years_df.assign(_k=1),
        on="_k",
    ).drop(columns="_k")
    return skel


def main() -> None:
    test_dir = Path(__file__).resolve().parent.parent.parent
    default_csv = test_dir / "公共产品供给分类标准.csv"
    default_out = test_dir / "township_poi_panel_2012_2017_wide.csv"

    ap = argparse.ArgumentParser(description="乡镇级 POI 宽表（三类一级类别）")
    ap.add_argument(
        "--classify-csv",
        default=str(default_csv),
        help="公共产品供给分类标准.csv 路径",
    )
    ap.add_argument(
        "--township-shp",
        default=r"F:\BaiduNetdiskDownload\四级矢量地图\21.县乡镇四级矢量数据\shp格式\全国乡镇边界（合集）\乡镇级行政区划合集.shp",
        help="乡镇边界 shapefile",
    )
    ap.add_argument(
        "--poi-extracted",
        default=None,
        help="poi_extracted 根目录（默认自动查找）",
    )
    ap.add_argument(
        "--years",
        default="2012,2013,2014,2015,2016,2017",
        help="逗号分隔年份",
    )
    ap.add_argument(
        "--output",
        "-o",
        default=str(default_out),
        help="输出 CSV 路径",
    )
    ap.add_argument(
        "--chunk-size",
        type=int,
        default=200_000,
        help="每个 POI 图层分块行数",
    )
    ap.add_argument(
        "--max-shp",
        type=int,
        default=None,
        help="每年最多处理前 N 个 shp（调试用）",
    )
    args = ap.parse_args()

    cat_to_level, xiaolei = load_category_map(args.classify_csv)
    poi_root = find_poi_extracted(args.poi_extracted)
    years = [int(y.strip()) for y in args.years.split(",") if y.strip()]

    print("加载乡镇边界 …", flush=True)
    townships = load_townships(args.township_shp)
    n_town = len(townships.drop_duplicates(subset=["code"]))
    print(f"  乡镇面要素数: {len(townships)}（唯一 code: {n_town}）", flush=True)

    skeleton = township_skeleton(townships, years)
    print(
        f"平衡面板行数（乡镇×年）: {len(skeleton)} = {n_town} × {len(years)}",
        flush=True,
    )

    all_long: List[pd.DataFrame] = []
    for year in years:
        sub = os.path.join(poi_root, str(year), str(year))
        if not os.path.isdir(sub):
            print(f"警告：{year} POI 目录不存在，该年全部乡镇三列记为 0：{sub}", flush=True)
            continue
        print(f"处理 {year} …", flush=True)
        long_df = aggregate_year(
            year,
            sub,
            townships,
            xiaolei,
            cat_to_level,
            args.chunk_size,
            args.max_shp,
        )
        if not long_df.empty:
            all_long.append(long_df)

    long_all = (
        pd.concat(all_long, ignore_index=True)
        if all_long
        else pd.DataFrame(columns=["年份", "code", "一级类别", "n"])
    )
    wide_counts = long_to_wide(long_all)

    out = skeleton.merge(wide_counts, on=["年份", "code"], how="left")
    out[LEVEL_COLS] = out[LEVEL_COLS].fillna(0).astype("int64")
    out = out[["年份", "code", "Name"] + LEVEL_COLS]
    out = out.sort_values(["年份", "code"]).reset_index(drop=True)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"已写入: {out_path}（共 {len(out)} 行）", flush=True)


if __name__ == "__main__":
    main()
