# -*- coding: utf-8 -*-
"""
乡镇级 POI 面板（宽表）— 2018–2021 年（**分号末段匹配版**）。

对 **大中小类混在同一字段、以 `;` 分隔** 的年份，先取 **最后一个非空片段**（通常为小类），
再与《公共产品供给分类标准》「小类」做 **substring 包含**匹配（旧版「整段包含」脚本已移除，以本脚本为 2018–2021 统一口径）。

- **2018**：列 **`type`**（非 2020 的 `dtype`）：先 `last_semicolon_segment` 再包含匹配；坐标 **`location`**。
- **2019**：无表头 **G 列**（索引 **6**）：先末段再包含匹配；**D/E**=纬/经。路径同原脚本。
- **2020**：不变——仍仅 **`小类`** 与标准表「小类」**完全相等**（该年另有独立 `大类`/`中类`/`小类` 列）。
- **2021**：列 **`类别`**：先末段再包含匹配；坐标 **`经纬度`**。

输出平衡面板（乡镇×年，无匹配则三列 0），默认 CSV utf-8-sig。

用法：
  python township_poi_panel_wide_2018_2021_contains_last_segment.py
  python township_poi_panel_wide_2018_2021_contains_last_segment.py --years 2018,2019 --max-files 3
"""

from __future__ import annotations

import argparse
import csv
import glob
import os
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Set, Tuple

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

COL_BASIC = "基本公共服务"
COL_INCLUSIVE = "普惠性非基本公共服务"
COL_LIFE = "生活服务"
LEVEL_COLS = [COL_BASIC, COL_INCLUSIVE, COL_LIFE]

# 2019 POI 仅位于 zip_extracted 下按省代码分段的子目录（与数据包目录结构一致）
POI_2019_ZIP_SUBDIRS = ("100000", "200000", "300000", "400000", "500000", "600000")

# 2019 无表头 8 列：A=序号…，D=纬度、E=经度，F=大类、G=细类，H=电话（与 Excel 列字母一致）
IDX_2019_LAT = 3
IDX_2019_LON = 4
IDX_2019_COL_G = 6  # 仅该列参与「小类」包含匹配


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


def load_sorted_xiaolei(csv_path: str) -> List[Tuple[str, str]]:
    """返回 [(小类, 一级类别), ...]，按小类长度降序、再按字符串排序（稳定）。"""
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    if "一级类别" not in df.columns or "小类" not in df.columns:
        raise ValueError("分类标准 CSV 需包含列：一级类别、小类")
    df = df.dropna(subset=["小类"])
    pairs: List[Tuple[str, str]] = []
    for _, r in df.iterrows():
        x = str(r["小类"]).strip()
        pairs.append((x, str(r["一级类别"]).strip()))
    pairs.sort(key=lambda t: (-len(t[0]), t[0]))
    return pairs


def match_level_from_text(text: str, sorted_pairs: List[Tuple[str, str]]) -> Optional[str]:
    if not text or not isinstance(text, str):
        return None
    for xiao, yiji in sorted_pairs:
        if xiao in text:
            return yiji
    return None


def last_semicolon_segment(text: object) -> str:
    """按 `;` 分割后取最后一个非空片段（strip），无分号则等价于整段 strip。用于 2018 type / 2019 G / 2021 类别。"""
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return ""
    parts = [p.strip() for p in str(text).split(";")]
    nonempty = [p for p in parts if p]
    return nonempty[-1] if nonempty else ""


def match_level_exact_xiaolei(
    value: object,
    cat_to_level: Dict[str, str],
    xiaolei: Set[str],
) -> Optional[str]:
    """与 2012–2017 一致：`小类` 字段值与标准表「小类」完全相等（strip 后）。"""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    if not s or s not in xiaolei:
        return None
    return cat_to_level.get(s)


def parse_two_floats(s: str) -> Optional[Tuple[float, float]]:
    """从字符串中提取两个浮点数，返回 (lon, lat)（中国大陆范围启发式）。"""
    nums = re.findall(r"-?\d+\.?\d*", str(s))
    if len(nums) < 2:
        return None
    a, b = float(nums[0]), float(nums[1])
    if 70.0 <= a <= 135.0 and 15.0 <= b <= 55.0:
        return a, b
    if 70.0 <= b <= 135.0 and 15.0 <= a <= 55.0:
        return b, a
    return None


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


def long_to_wide(long_df: pd.DataFrame) -> pd.DataFrame:
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
    base = townships[["code", "Name"]].drop_duplicates(subset=["code"], keep="first")
    years_df = pd.DataFrame({"年份": years})
    skel = pd.merge(
        base.assign(_k=1),
        years_df.assign(_k=1),
        on="_k",
    ).drop(columns="_k")
    return skel


def rows_to_points_gdf(
    lon: List[float],
    lat: List[float],
    levels: List[str],
) -> gpd.GeoDataFrame:
    geom = [Point(xy) for xy in zip(lon, lat)]
    gdf = gpd.GeoDataFrame(
        {"一级类别": levels},
        geometry=geom,
        crs="EPSG:4326",
    )
    return gdf


def _iter_chunks_2018(
    poi_root: str,
    sorted_pairs: List[Tuple[str, str]],
    chunk_size: int,
    max_files: Optional[int],
) -> Iterator[Tuple[str, pd.DataFrame]]:
    pattern = os.path.join(poi_root, "2018", "*.csv")
    files = sorted(glob.glob(pattern))
    if max_files is not None:
        files = files[: max_files]
    for fp in files:
        for enc in ("gb18030", "utf-8-sig", "utf-8"):
            try:
                reader = pd.read_csv(
                    fp,
                    encoding=enc,
                    chunksize=chunk_size,
                    dtype=str,
                    on_bad_lines="skip",
                    low_memory=False,
                )
                for chunk in reader:
                    yield fp, chunk
                break
            except Exception:
                continue


def process_chunk_2018(chunk: pd.DataFrame, sorted_pairs: List[Tuple[str, str]]) -> gpd.GeoDataFrame:
    need = {"location", "type"}
    if not need.issubset(chunk.columns):
        return gpd.GeoDataFrame(columns=["一级类别"], geometry=[], crs="EPSG:4326")
    chunk = chunk.copy()
    chunk["type"] = chunk["type"].fillna("").astype(str)
    lon_list: List[float] = []
    lat_list: List[float] = []
    lev_list: List[str] = []
    for _, r in chunk.iterrows():
        pt = parse_two_floats(r["location"])
        if pt is None:
            continue
        lon, lat = pt
        lev = match_level_from_text(last_semicolon_segment(r["type"]), sorted_pairs)
        if lev is None:
            continue
        lon_list.append(lon)
        lat_list.append(lat)
        lev_list.append(lev)
    if not lon_list:
        return gpd.GeoDataFrame(columns=["一级类别"], geometry=[], crs="EPSG:4326")
    return rows_to_points_gdf(lon_list, lat_list, lev_list)


def _glob_2019_d_csv_paths(zip_root: str) -> List[str]:
    """仅扫描 zip_extracted 下 100000–600000 六个子目录内的 d_*.csv。"""
    found: List[str] = []
    for sub in POI_2019_ZIP_SUBDIRS:
        d = os.path.join(zip_root, sub)
        if not os.path.isdir(d):
            continue
        found.extend(
            glob.glob(os.path.join(d, "**", "d_*.csv"), recursive=True)
        )
    return sorted(set(found))


def _iter_chunks_2019_zip(
    zip_root: str,
    sorted_pairs: List[Tuple[str, str]],
    chunk_size: int,
    max_files: Optional[int],
) -> Iterator[Tuple[str, List[List[str]]]]:
    files = _glob_2019_d_csv_paths(zip_root)
    if max_files is not None:
        files = files[: max_files]
    for fp in files:
        batch: List[List[str]] = []
        for enc in ("gb18030", "gbk", "utf-8"):
            try:
                with open(fp, "r", encoding=enc, errors="replace", newline="") as f:
                    reader = csv.reader(f)
                    for row in reader:
                        if len(row) <= IDX_2019_COL_G:
                            continue
                        batch.append(row)
                        if len(batch) >= chunk_size:
                            yield fp, batch
                            batch = []
                    if batch:
                        yield fp, batch
                break
            except Exception:
                batch = []
                continue


def process_batch_2019_zip(
    rows: List[List[str]],
    sorted_pairs: List[Tuple[str, str]],
) -> gpd.GeoDataFrame:
    lon_list: List[float] = []
    lat_list: List[float] = []
    lev_list: List[str] = []
    for row in rows:
        if len(row) <= IDX_2019_COL_G:
            continue
        try:
            lat = float(row[IDX_2019_LAT].strip())
            lon = float(row[IDX_2019_LON].strip())
        except (ValueError, IndexError):
            continue
        if not (15.0 <= lat <= 55.0 and 70.0 <= lon <= 135.0):
            continue
        cat_text = str(row[IDX_2019_COL_G])
        lev = match_level_from_text(last_semicolon_segment(cat_text), sorted_pairs)
        if lev is None:
            continue
        lon_list.append(lon)
        lat_list.append(lat)
        lev_list.append(lev)
    if not lon_list:
        return gpd.GeoDataFrame(columns=["一级类别"], geometry=[], crs="EPSG:4326")
    return rows_to_points_gdf(lon_list, lat_list, lev_list)


def _iter_chunks_2020(
    poi_root: str,
    sorted_pairs: List[Tuple[str, str]],
    chunk_size: int,
    max_files: Optional[int],
) -> Iterator[Tuple[str, pd.DataFrame]]:
    pattern = os.path.join(poi_root, "2020", "*", "*.csv")
    files = sorted(glob.glob(pattern))
    if max_files is not None:
        files = files[: max_files]
    for fp in files:
        for enc in ("utf-8-sig", "utf-8", "gb18030"):
            try:
                reader = pd.read_csv(
                    fp,
                    encoding=enc,
                    chunksize=chunk_size,
                    dtype=str,
                    on_bad_lines="skip",
                    low_memory=False,
                )
                for chunk in reader:
                    yield fp, chunk
                break
            except Exception:
                continue


def process_chunk_2020(
    chunk: pd.DataFrame,
    cat_to_level: Dict[str, str],
    xiaolei: Set[str],
) -> gpd.GeoDataFrame:
    need = {"小类", "wgs84lon", "wgs84lat"}
    if not need.issubset(chunk.columns):
        return gpd.GeoDataFrame(columns=["一级类别"], geometry=[], crs="EPSG:4326")
    chunk = chunk.copy()
    lon_list: List[float] = []
    lat_list: List[float] = []
    lev_list: List[str] = []
    for _, r in chunk.iterrows():
        try:
            lon = float(pd.to_numeric(r["wgs84lon"], errors="coerce"))
            lat = float(pd.to_numeric(r["wgs84lat"], errors="coerce"))
        except (TypeError, ValueError):
            continue
        if pd.isna(lon) or pd.isna(lat):
            continue
        lev = match_level_exact_xiaolei(r["小类"], cat_to_level, xiaolei)
        if lev is None:
            continue
        lon_list.append(lon)
        lat_list.append(lat)
        lev_list.append(lev)
    if not lon_list:
        return gpd.GeoDataFrame(columns=["一级类别"], geometry=[], crs="EPSG:4326")
    return rows_to_points_gdf(lon_list, lat_list, lev_list)


def _iter_chunks_2021(
    poi_root: str,
    sorted_pairs: List[Tuple[str, str]],
    chunk_size: int,
    max_files: Optional[int],
) -> Iterator[Tuple[str, pd.DataFrame]]:
    pattern = os.path.join(poi_root, "2021", "*.csv")
    files = sorted(glob.glob(pattern))
    if max_files is not None:
        files = files[: max_files]
    for fp in files:
        for enc in ("utf-8-sig", "utf-8", "gb18030"):
            try:
                reader = pd.read_csv(
                    fp,
                    encoding=enc,
                    chunksize=chunk_size,
                    dtype=str,
                    on_bad_lines="skip",
                    low_memory=False,
                )
                for chunk in reader:
                    yield fp, chunk
                break
            except Exception:
                continue


def process_chunk_2021(chunk: pd.DataFrame, sorted_pairs: List[Tuple[str, str]]) -> gpd.GeoDataFrame:
    need = {"经纬度", "类别"}
    if not need.issubset(chunk.columns):
        return gpd.GeoDataFrame(columns=["一级类别"], geometry=[], crs="EPSG:4326")
    chunk = chunk.copy()
    chunk["类别"] = chunk["类别"].fillna("").astype(str)
    lon_list: List[float] = []
    lat_list: List[float] = []
    lev_list: List[str] = []
    for _, r in chunk.iterrows():
        pt = parse_two_floats(r["经纬度"])
        if pt is None:
            continue
        lon, lat = pt
        lev = match_level_from_text(last_semicolon_segment(r["类别"]), sorted_pairs)
        if lev is None:
            continue
        lon_list.append(lon)
        lat_list.append(lat)
        lev_list.append(lev)
    if not lon_list:
        return gpd.GeoDataFrame(columns=["一级类别"], geometry=[], crs="EPSG:4326")
    return rows_to_points_gdf(lon_list, lat_list, lev_list)


def aggregate_year(
    year: int,
    poi_root: str,
    townships: gpd.GeoDataFrame,
    sorted_pairs: List[Tuple[str, str]],
    cat_to_level: Dict[str, str],
    xiaolei: Set[str],
    chunk_size: int,
    max_files: Optional[int],
) -> pd.DataFrame:
    parts: List[pd.DataFrame] = []
    if year == 2018:
        for _fp, chunk in _iter_chunks_2018(poi_root, sorted_pairs, chunk_size, max_files):
            pts = process_chunk_2018(chunk, sorted_pairs)
            if len(pts) == 0:
                continue
            joined = pts.sjoin(townships, how="inner", predicate="within")
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
    elif year == 2019:
        zip_root = os.path.join(poi_root, "2019", "2019", "zip_extracted")
        if not os.path.isdir(zip_root):
            print(f"警告：2019 zip_extracted 不存在: {zip_root}", flush=True)
            return pd.DataFrame(columns=["年份", "code", "一级类别", "n"])
        n_csv = len(_glob_2019_d_csv_paths(zip_root))
        if n_csv == 0:
            print(
                f"警告：2019 在 {POI_2019_ZIP_SUBDIRS} 下未找到 d_*.csv：{zip_root}",
                flush=True,
            )
        for _fp, batch in _iter_chunks_2019_zip(zip_root, sorted_pairs, chunk_size, max_files):
            pts = process_batch_2019_zip(batch, sorted_pairs)
            if len(pts) == 0:
                continue
            joined = pts.sjoin(townships, how="inner", predicate="within")
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
    elif year == 2020:
        for _fp, chunk in _iter_chunks_2020(poi_root, sorted_pairs, chunk_size, max_files):
            pts = process_chunk_2020(chunk, cat_to_level, xiaolei)
            if len(pts) == 0:
                continue
            joined = pts.sjoin(townships, how="inner", predicate="within")
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
    elif year == 2021:
        for _fp, chunk in _iter_chunks_2021(poi_root, sorted_pairs, chunk_size, max_files):
            pts = process_chunk_2021(chunk, sorted_pairs)
            if len(pts) == 0:
                continue
            joined = pts.sjoin(townships, how="inner", predicate="within")
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
    else:
        return pd.DataFrame(columns=["年份", "code", "一级类别", "n"])

    if not parts:
        return pd.DataFrame(columns=["年份", "code", "一级类别", "n"])
    long_df = pd.concat(parts, ignore_index=True)
    long_df = (
        long_df.groupby(["年份", "code", "一级类别"], as_index=False)["n"]
        .sum()
    )
    return long_df


def main() -> None:
    test_dir = Path(__file__).resolve().parent.parent.parent
    default_csv = test_dir / "公共产品供给分类标准.csv"
    default_out = test_dir / "township_poi_panel_2018_2021_wide_contains_last_segment.csv"

    ap = argparse.ArgumentParser(
        description="乡镇 POI 宽表 2018–2021（2018/19/21：分号末段后再包含匹配；2020 小类相等）",
    )
    ap.add_argument("--classify-csv", default=str(default_csv))
    ap.add_argument(
        "--township-shp",
        default=r"F:\BaiduNetdiskDownload\四级矢量地图\21.县乡镇四级矢量数据\shp格式\全国乡镇边界（合集）\乡镇级行政区划合集.shp",
    )
    ap.add_argument("--poi-extracted", default=None)
    ap.add_argument("--years", default="2018,2019,2020,2021")
    ap.add_argument("-o", "--output", default=str(default_out))
    ap.add_argument("--chunk-size", type=int, default=100_000)
    ap.add_argument(
        "--max-files",
        type=int,
        default=None,
        help="每年最多处理前 N 个数据文件（调试用；2019 为 d_*.csv 个数）",
    )
    args = ap.parse_args()

    sorted_pairs = load_sorted_xiaolei(args.classify_csv)
    cat_to_level: Dict[str, str] = dict(sorted_pairs)
    xiaolei: Set[str] = set(cat_to_level.keys())
    poi_root = find_poi_extracted(args.poi_extracted)
    years = [int(y.strip()) for y in args.years.split(",") if y.strip()]
    allowed = {2018, 2019, 2020, 2021}
    years = [y for y in years if y in allowed]
    if not years:
        print("年份列表为空或不在 2018–2021 内", file=sys.stderr)
        sys.exit(1)

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
        sub_ok = True
        if year == 2019:
            zr = os.path.join(poi_root, "2019", "2019", "zip_extracted")
            if not os.path.isdir(zr):
                print(f"警告：{year} 目录不存在 {zr}，该年三列记 0", flush=True)
                sub_ok = False
            elif not any(os.path.isdir(os.path.join(zr, s)) for s in POI_2019_ZIP_SUBDIRS):
                print(
                    f"警告：{year} zip_extracted 下无 {POI_2019_ZIP_SUBDIRS} 分段目录，该年三列记 0",
                    flush=True,
                )
                sub_ok = False
        elif year == 2018:
            if not os.path.isdir(os.path.join(poi_root, "2018")):
                print(f"警告：{year} 目录不存在", flush=True)
                sub_ok = False
        elif year == 2020:
            if not glob.glob(os.path.join(poi_root, "2020", "*", "*.csv")):
                print(f"警告：{year} 无 CSV", flush=True)
                sub_ok = False
        elif year == 2021:
            if not glob.glob(os.path.join(poi_root, "2021", "*.csv")):
                print(f"警告：{year} 无 CSV", flush=True)
                sub_ok = False

        if not sub_ok:
            continue

        print(f"处理 {year} …", flush=True)
        long_df = aggregate_year(
            year,
            poi_root,
            townships,
            sorted_pairs,
            cat_to_level,
            xiaolei,
            args.chunk_size,
            args.max_files,
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
