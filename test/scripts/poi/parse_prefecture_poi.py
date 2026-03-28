# -*- coding: utf-8 -*-
"""
从「地级市 POI 兴趣点」目录按年份解析 POI，合并为按年一个 Parquet（或 GeoParquet）。

已自动处理：
- 2020POI：各地级市 zip，内含多个 UTF-8 CSV
- 2013POI：全国 2013.zip，内含按类别 shapefile
- 2023POI：嵌套目录下省级 gd_*_poi.zip，内含 xlsx

需人工解压或安装 7-Zip/UnRAR 后处理的格式（脚本会写入 manifest 提示）：
- 分卷 7z（2015–2017 等）、整包 rar（2012、2014、2018–2022 等）
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

ENCODING_CSV = "utf-8-sig"


def find_poi_root(explicit: Optional[str]) -> str:
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
            return path
    raise FileNotFoundError("在 BaiduNetdiskDownload 下未找到名称含 POI 的文件夹")


def _ensure_out(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)


def parse_2020(
    poi_root: str,
    out_dir: Path,
    max_archives: Optional[int] = None,
) -> Dict[str, Any]:
    year_dir = os.path.join(poi_root, "2020POI")
    zips = sorted(glob.glob(os.path.join(year_dir, "*.zip")))
    if not zips:
        raise FileNotFoundError(f"2020POI 下未找到 zip: {year_dir}")
    if max_archives is not None:
        zips = zips[: max_archives]

    frames: List[pd.DataFrame] = []
    for zp in zips:
        city_archive = os.path.basename(zp)
        with zipfile.ZipFile(zp, "r") as zf:
            for name in zf.namelist():
                if not name.lower().endswith(".csv"):
                    continue
                with zf.open(name) as f:
                    df = pd.read_csv(
                        f,
                        encoding=ENCODING_CSV,
                        dtype=str,
                        low_memory=False,
                    )
                df["__poi_year"] = "2020"
                df["__city_archive"] = city_archive
                df["__inner_csv"] = os.path.basename(name)
                frames.append(df)

    if not frames:
        raise RuntimeError("2020: zip 内未读到任何 CSV")

    merged = pd.concat(frames, ignore_index=True, sort=False)
    out_path = out_dir / "poi_2020.parquet"
    merged.to_parquet(out_path, index=False)
    return {
        "year": 2020,
        "out_file": str(out_path),
        "rows": int(len(merged)),
        "archives_used": len(zips),
    }


def parse_2013(poi_root: str, out_dir: Path) -> Dict[str, Any]:
    import geopandas as gpd

    zp = os.path.join(poi_root, "2013POI", "2013.zip")
    if not os.path.isfile(zp):
        raise FileNotFoundError(zp)

    # GDAL /vsizip/ 在含中文的绝对路径上常失败，解压到临时目录再读 shapefile
    gdfs: List[gpd.GeoDataFrame] = []
    shp_count = 0
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(zp, "r") as zf:
            zf.extractall(tmp)
        for shp_path in glob.glob(os.path.join(tmp, "**", "*.shp"), recursive=True):
            try:
                gdf = gpd.read_file(shp_path, encoding="utf-8")
            except UnicodeDecodeError:
                gdf = gpd.read_file(shp_path, encoding="gb18030")
            gdf = gdf.copy()
            gdf["__poi_year"] = 2013
            gdf["__layer"] = os.path.basename(shp_path)
            gdfs.append(gdf)
            shp_count += 1

    if not gdfs:
        raise RuntimeError("2013.zip 解压后未找到任何 .shp")

    merged = gpd.GeoDataFrame(pd.concat(gdfs, ignore_index=True))
    out_path = out_dir / "poi_2013.parquet"
    merged.to_parquet(out_path, index=False)
    return {
        "year": 2013,
        "out_file": str(out_path),
        "rows": int(len(merged)),
        "layers": shp_count,
    }


def parse_2023(poi_root: str, out_dir: Path) -> Dict[str, Any]:
    year_dir = os.path.join(poi_root, "2023POI")
    zips: List[str] = []
    for root, _, files in os.walk(year_dir):
        for f in files:
            if f.endswith(".zip") and f.startswith("gd_"):
                zips.append(os.path.join(root, f))
    zips = sorted(zips)
    if not zips:
        raise FileNotFoundError(f"2023POI 下未找到 gd_*.zip: {year_dir}")

    frames: List[pd.DataFrame] = []
    for zp in zips:
        prov_archive = os.path.basename(zp)
        with zipfile.ZipFile(zp, "r") as zf:
            for name in zf.namelist():
                if "MACOSX" in name or name.startswith("__"):
                    continue
                if not name.lower().endswith(".xlsx"):
                    continue
                with zf.open(name) as f:
                    df = pd.read_excel(f, engine="openpyxl", dtype=str)
                df["__poi_year"] = "2023"
                df["__province_archive"] = prov_archive
                df["__inner_file"] = os.path.basename(name)
                frames.append(df)

    if not frames:
        raise RuntimeError("2023: zip 内未读到任何 xlsx")

    merged = pd.concat(frames, ignore_index=True, sort=False)
    out_path = out_dir / "poi_2023.parquet"
    merged.to_parquet(out_path, index=False)
    return {
        "year": 2023,
        "out_file": str(out_path),
        "rows": int(len(merged)),
        "archives_used": len(zips),
    }


def scan_unsupported(poi_root: str) -> List[Dict[str, Any]]:
    """列出当前脚本未自动解析、需解压/外部工具的年度目录说明。"""
    notes: List[Dict[str, Any]] = []
    for name in sorted(os.listdir(poi_root)):
        if not name.endswith("POI"):
            continue
        ydir = os.path.join(poi_root, name)
        if not os.path.isdir(ydir):
            continue
        year = name.replace("POI", "")
        if year in ("2013", "2020", "2023"):
            continue
        hint = "需解压 rar/分卷 7z 后，按该年实际格式（csv/shp/xlsx）再跑对应逻辑"
        files: List[str] = []
        for root, _, fs in os.walk(ydir):
            for f in fs:
                if f.endswith((".rar", ".zip", ".7z", ".001")) or ".7z." in f:
                    files.append(os.path.relpath(os.path.join(root, f), ydir))
            if len(files) > 30:
                break
        notes.append({"folder": name, "sample_files": files[:15], "hint": hint})
    return notes


def main() -> int:
    ap = argparse.ArgumentParser(description="解析地级市 POI 按年合并为 Parquet")
    ap.add_argument(
        "--poi-root",
        default=None,
        help=r"POI 根目录，默认在 F:\BaiduNetdiskDownload 下自动查找名称含 POI 的文件夹",
    )
    ap.add_argument(
        "--out",
        default=None,
        help="输出目录，默认为脚本所在 test/output/poi_by_year",
    )
    ap.add_argument(
        "--years",
        default="2020,2013,2023",
        help="逗号分隔年份，仅实现 2013,2020,2023",
    )
    ap.add_argument(
        "--max-archives-2020",
        type=int,
        default=None,
        help="仅处理 2020 的前 N 个地级市 zip，用于试跑",
    )
    args = ap.parse_args()

    test_dir = Path(__file__).resolve().parent.parent.parent
    out_dir = Path(args.out) if args.out else test_dir / "output" / "poi_by_year"
    _ensure_out(out_dir)

    poi_root = find_poi_root(args.poi_root)
    years = [y.strip() for y in args.years.split(",") if y.strip()]

    results: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for y in years:
        try:
            if y == "2020":
                results.append(
                    parse_2020(
                        poi_root,
                        out_dir,
                        max_archives=args.max_archives_2020,
                    )
                )
            elif y == "2013":
                results.append(parse_2013(poi_root, out_dir))
            elif y == "2023":
                results.append(parse_2023(poi_root, out_dir))
            else:
                errors.append({"year": y, "error": "未实现该年自动解析，请解压后扩展脚本"})
        except Exception as e:  # noqa: BLE001
            errors.append({"year": y, "error": str(e)})

    manifest: Dict[str, Any] = {
        "poi_root": poi_root,
        "parsed": results,
        "errors": errors,
        "unsupported_years_hint": scan_unsupported(poi_root),
    }
    manifest_path = out_dir / "parse_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0 if results else 1


if __name__ == "__main__":
    sys.exit(main())
