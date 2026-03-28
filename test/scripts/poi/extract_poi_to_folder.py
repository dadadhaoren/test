# -*- coding: utf-8 -*-
"""
将「地级市 POI 兴趣点」下各年份压缩包解压到：
  <POI 主目录>\\poi_extracted\\<年份>\\

支持：
- .zip：标准库 zipfile
- 分卷 .7z.001 …：py7zr（需已安装 py7zr）
- .rar / 分卷 .7z：优先 7-Zip（7z.exe）；其次 UnRAR.exe；再次 **WinRAR.exe**（命令行 `x -o+`）
- 可传 `--winrar "C:\\Program Files\\WinRAR\\WinRAR.exe"` 或环境变量 **WINRAR**

用法（在项目 test 目录外也可用绝对路径运行）：
  python extract_poi_to_folder.py
  python extract_poi_to_folder.py --years 2013,2020
  python extract_poi_to_folder.py --seven-zip "C:\\Program Files\\7-Zip\\7z.exe"
  python extract_poi_to_folder.py --winrar "C:\\Program Files\\WinRAR\\WinRAR.exe" --years 2012,2015
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 与 parse_prefecture_poi 一致
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


def default_extract_root(poi_root: str) -> str:
    return os.path.join(poi_root, "poi_extracted")


def discover_seven_zip(user_path: Optional[str]) -> Optional[str]:
    if user_path and os.path.isfile(user_path):
        return user_path
    env = os.environ.get("SEVEN_ZIP", "").strip()
    if env and os.path.isfile(env):
        return env
    candidates = [
        os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "7-Zip", "7z.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"), "7-Zip", "7z.exe"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    w = shutil.which("7z")
    if w:
        return w
    return None


def discover_unrar() -> Optional[str]:
    for c in (
        os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "WinRAR", "UnRAR.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"), "WinRAR", "UnRAR.exe"),
    ):
        if os.path.isfile(c):
            return c
    w = shutil.which("UnRAR") or shutil.which("unrar")
    if w:
        return w
    return None


def discover_winrar(user_path: Optional[str]) -> Optional[str]:
    """WinRAR 图形版主程序，支持命令行解压 RAR/7z 等。"""
    if user_path and os.path.isfile(user_path):
        return user_path
    env = os.environ.get("WINRAR", "").strip()
    if env and os.path.isfile(env):
        return env
    for c in (
        os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), "WinRAR", "WinRAR.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"), "WinRAR", "WinRAR.exe"),
    ):
        if os.path.isfile(c):
            return c
    return None


def run_7z_extract(seven_zip: str, archive: str, dest: str) -> None:
    os.makedirs(dest, exist_ok=True)
    # 7z x archive -o"dest" -y
    # 注意：-o 后路径无空格分隔
    cmd = [seven_zip, "x", archive, f"-o{dest}", "-y"]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(
            f"7z 解压失败 code={r.returncode}\narchive={archive}\nstdout={r.stdout}\nstderr={r.stderr}"
        )


def run_unrar_extract(unrar: str, archive: str, dest: str) -> None:
    os.makedirs(dest, exist_ok=True)
    cmd = [unrar, "x", "-o+", archive, dest + "\\"]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(
            f"UnRAR 解压失败 code={r.returncode}\narchive={archive}\nstdout={r.stdout}\nstderr={r.stderr}"
        )


def run_winrar_extract(winrar: str, archive: str, dest: str) -> None:
    """使用 WinRAR.exe 命令行：x 解压并保持路径；-o+ 覆盖；-ibck 后台；-y 全部确认。"""
    os.makedirs(dest, exist_ok=True)
    cmd = [winrar, "x", "-o+", "-ibck", "-y", archive, dest + "\\"]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(
            f"WinRAR 解压失败 code={r.returncode}\narchive={archive}\nstdout={r.stdout}\nstderr={r.stderr}"
        )


def extract_zip(archive: str, dest: str) -> None:
    os.makedirs(dest, exist_ok=True)
    with zipfile.ZipFile(archive, "r") as zf:
        zf.extractall(dest)


def extract_7z_multivolume(
    first_volume: str,
    dest: str,
    seven_zip: Optional[str],
    winrar: Optional[str],
) -> None:
    """分卷 7z：优先 7-Zip；其次 WinRAR（可解 7z）；再尝试 py7zr。"""
    os.makedirs(dest, exist_ok=True)
    if seven_zip:
        run_7z_extract(seven_zip, first_volume, dest)
        return
    if winrar:
        run_winrar_extract(winrar, first_volume, dest)
        return
    import py7zr
    from py7zr.exceptions import Bad7zFile

    try:
        with py7zr.SevenZipFile(first_volume, mode="r") as z:
            z.extractall(path=dest)
    except Bad7zFile as e:
        raise RuntimeError(
            "py7zr 无法读取该 7z（常见原因：格式/固实压缩等）。"
            "请安装 7-Zip 并设置 SEVEN_ZIP，或安装 WinRAR 并传入 --winrar。"
        ) from e


def year_from_folder(folder_name: str) -> Optional[str]:
    m = re.match(r"^(\d{4})POI$", folder_name)
    return m.group(1) if m else None


def find_7z_first_volume(year_dir: str) -> Optional[str]:
    """在年份目录下查找分卷 7z 的第一卷（*.7z.001 或 *.7z.1）。"""
    candidates: List[str] = []
    for root, _, files in os.walk(year_dir):
        for f in files:
            if re.search(r"\.7z\.0*1$", f, re.I) and "(" not in f:
                candidates.append(os.path.join(root, f))
            elif f.endswith(".7z") and not re.search(r"\.7z\.\d+", f):
                # 单文件 .7z
                candidates.append(os.path.join(root, f))
    if not candidates:
        return None
    # 优先 *.7z.001
    for c in sorted(candidates):
        if ".7z.001" in c.replace("\\", "/") or c.endswith(".7z.001"):
            return c
    return sorted(candidates)[0]


def extract_year(
    poi_root: str,
    extract_root: str,
    year_key: str,
    seven_zip: Optional[str],
    unrar: Optional[str],
    winrar: Optional[str],
) -> Dict[str, Any]:
    """year_key 如 '2013'，对应文件夹 2013POI。"""
    folder = f"{year_key}POI"
    year_dir = os.path.join(poi_root, folder)
    out = os.path.join(extract_root, year_key)
    os.makedirs(out, exist_ok=True)

    result: Dict[str, Any] = {"year": year_key, "dest": out, "status": "ok", "detail": None}

    if not os.path.isdir(year_dir):
        result["status"] = "skip"
        result["detail"] = "年份目录不存在"
        return result

    # 2023：嵌套子目录中的 gd_*.zip
    if year_key == "2023":
        zips: List[str] = []
        for root, _, files in os.walk(year_dir):
            for f in files:
                if f.startswith("gd_") and f.endswith(".zip"):
                    zips.append(os.path.join(root, f))
        zips = sorted(zips)
        if not zips:
            result["status"] = "skip"
            result["detail"] = "未找到 gd_*.zip"
            return result
        for i, zp in enumerate(zips):
            stem = Path(zp).stem
            sub = os.path.join(out, stem)
            extract_zip(zp, sub)
        result["detail"] = f"已解压 {len(zips)} 个省级 zip 到子目录"
        return result

    # 2020：大量地级市 zip
    if year_key == "2020":
        zips = sorted(glob.glob(os.path.join(year_dir, "*.zip")))
        if not zips:
            result["status"] = "skip"
            result["detail"] = "未找到地级市 zip"
            return result
        for zp in zips:
            stem = Path(zp).stem
            sub = os.path.join(out, stem)
            extract_zip(zp, sub)
        result["detail"] = f"已解压 {len(zips)} 个地级市 zip"
        return result

    # 单 zip（2013）
    zips = [f for f in glob.glob(os.path.join(year_dir, "*.zip")) if "(" not in os.path.basename(f)]
    if len(zips) == 1:
        extract_zip(zips[0], out)
        result["detail"] = os.path.basename(zips[0])
        return result

    # 分卷 7z（2015–2017 等）
    vol = find_7z_first_volume(year_dir)
    if vol:
        try:
            extract_7z_multivolume(vol, out, seven_zip, winrar)
            detail_tool = "7z"
            if not seven_zip and winrar:
                detail_tool = "WinRAR"
            elif not seven_zip and not winrar:
                detail_tool = "py7zr"
            result["detail"] = f"7z({detail_tool}): {os.path.basename(vol)}"
        except Exception as ex:  # noqa: BLE001
            result["status"] = "error"
            result["detail"] = str(ex)
        return result

    # 单 rar
    rars = [f for f in glob.glob(os.path.join(year_dir, "*.rar")) if "(" not in os.path.basename(f)]
    if len(rars) >= 1:
        rar_path = rars[0]
        if seven_zip:
            run_7z_extract(seven_zip, rar_path, out)
            result["detail"] = f"rar(7z): {os.path.basename(rar_path)}"
            return result
        if unrar:
            run_unrar_extract(unrar, rar_path, out)
            result["detail"] = f"rar(UnRAR): {os.path.basename(rar_path)}"
            return result
        if winrar:
            run_winrar_extract(winrar, rar_path, out)
            result["detail"] = f"rar(WinRAR): {os.path.basename(rar_path)}"
            return result
        result["status"] = "error"
        result["detail"] = (
            "发现 .rar 但未找到 7-Zip(7z.exe)、UnRAR.exe 或 WinRAR.exe。"
            "请使用 --seven-zip、安装 UnRAR，或传入 --winrar 指向 WinRAR.exe。"
        )
        return result

    result["status"] = "skip"
    result["detail"] = "未识别到 zip/7z/rar 主压缩包"
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="按年份解压 POI 压缩包到 poi_extracted")
    ap.add_argument("--poi-root", default=None, help="POI 主目录，默认自动查找")
    ap.add_argument(
        "--extract-root",
        default=None,
        help="解压目标根目录，默认 <POI 主目录>\\\\poi_extracted",
    )
    ap.add_argument(
        "--years",
        default=None,
        help="逗号分隔年份，如 2013,2020；默认全部 2012–2023",
    )
    ap.add_argument("--seven-zip", default=None, help="7z.exe 完整路径（可选）")
    ap.add_argument(
        "--winrar",
        default=None,
        help='WinRAR.exe 完整路径，如 "C:\\\\Program Files\\\\WinRAR\\\\WinRAR.exe"',
    )
    args = ap.parse_args()

    poi_root = find_poi_root(args.poi_root)
    extract_root = args.extract_root or default_extract_root(poi_root)
    os.makedirs(extract_root, exist_ok=True)

    seven_zip = discover_seven_zip(args.seven_zip)
    unrar = discover_unrar()
    winrar = discover_winrar(args.winrar)

    if args.years:
        years = [y.strip() for y in args.years.split(",") if y.strip()]
    else:
        years = [str(y) for y in range(2012, 2024)]

    report: List[Dict[str, Any]] = []
    for y in years:
        report.append(extract_year(poi_root, extract_root, y, seven_zip, unrar, winrar))

    manifest_path = os.path.join(extract_root, "extract_manifest.json")
    merged: Dict[str, Any] = {
        "poi_root": poi_root,
        "extract_root": extract_root,
        "seven_zip_used": seven_zip,
        "unrar_found": unrar,
        "winrar_used": winrar,
        "results": [],
    }
    if os.path.isfile(manifest_path):
        try:
            old = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
            by_year = {r["year"]: r for r in old.get("results", []) if isinstance(r, dict) and "year" in r}
        except (json.JSONDecodeError, OSError, TypeError, KeyError):
            by_year = {}
    else:
        by_year = {}
    for r in report:
        by_year[r["year"]] = r
    merged["results"] = [by_year[k] for k in sorted(by_year.keys())]

    Path(manifest_path).write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(merged, ensure_ascii=False, indent=2))
    if any(r.get("status") == "error" for r in merged["results"]):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
