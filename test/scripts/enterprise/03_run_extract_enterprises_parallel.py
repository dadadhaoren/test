# -*- coding: utf-8 -*-
"""
按**省文件夹**并行调用 `02_extract_enterprises_to_township.py`（每省独立子进程），
最后合并为**全国** `年份×乡镇 code` 计数表与汇总统计 JSON。

前提：`02_extract_enterprises_to_township.py` 已支持 `--enterprise-root` 指向**单省目录**
（其下直接为 `*.xlsx`）。

默认：`--workers` = min(10, CPU 逻辑核数)（高并发；仍受磁盘与内存约束，可再调大）。

用法：
  python 03_run_extract_enterprises_parallel.py --dry-run
  python 03_run_extract_enterprises_parallel.py --workers 12
  python 03_run_extract_enterprises_parallel.py --only-subdirs 上海所有企业-新版,宁夏所有企业
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
EXTRACT_SCRIPT = SCRIPT_DIR / "02_extract_enterprises_to_township.py"


def safe_stem(name: str, max_len: int = 100) -> str:
    s = re.sub(r'[<>:"/\\|?*\n\r]', "_", name.strip())
    return s[:max_len] if len(s) > max_len else s


def list_province_subdirs(national_root: str) -> List[str]:
    root = os.path.abspath(national_root)
    out: List[str] = []
    for sub in sorted(os.listdir(root)):
        d = os.path.join(root, sub)
        if os.path.isdir(d):
            out.append(sub)
    return out


def merge_count_csvs(paths: List[Path], out: Path) -> int:
    dfs = []
    for p in paths:
        if not p.is_file() or p.stat().st_size == 0:
            continue
        dfs.append(pd.read_csv(p, encoding="utf-8-sig"))
    if not dfs:
        pd.DataFrame(columns=["年份", "code", "n"]).to_csv(out, index=False, encoding="utf-8-sig")
        return 0
    all_df = pd.concat(dfs, ignore_index=True)
    merged = all_df.groupby(["年份", "code"], as_index=False)["n"].sum()
    merged = merged.sort_values(["年份", "code"]).reset_index(drop=True)
    merged.to_csv(out, index=False, encoding="utf-8-sig")
    return len(merged)


def merge_stats_json(paths: List[Path], out: Path, n_provinces_ok: int) -> None:
    merged: Dict[str, Any] = defaultdict(int)
    county_keys: Optional[int] = None
    for p in paths:
        if not p.is_file():
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        for k, v in d.items():
            if k == "county_keys_in_map" and isinstance(v, int):
                county_keys = v if county_keys is None else county_keys
            elif isinstance(v, int):
                merged[k] += v
    merged["county_keys_in_map"] = county_keys
    merged["provinces_parallel_ok"] = n_provinces_ok
    out.write_text(json.dumps(dict(merged), ensure_ascii=False, indent=2), encoding="utf-8")


def build_extract_command(
    extract_script: Path,
    enterprise_root_one_province: str,
    output_csv: str,
    stats_json: str,
    division_csv: str,
    industry_exclude_csv: str,
    year_min: Optional[int],
    year_max: Optional[int],
    max_files: Optional[int],
    no_exclude_name_keywords: bool,
    no_exclude_industry: bool,
    extra_exclude_keywords: str,
) -> List[str]:
    cmd: List[str] = [
        sys.executable,
        str(extract_script),
        "--enterprise-root",
        enterprise_root_one_province,
        "-o",
        output_csv,
        "--stats-json",
        stats_json,
        "--division-csv",
        division_csv,
    ]
    if industry_exclude_csv:
        cmd += ["--industry-exclude-csv", industry_exclude_csv]
    if no_exclude_industry:
        cmd.append("--no-exclude-industry")
    if year_min is not None:
        cmd += ["--year-min", str(year_min)]
    if year_max is not None:
        cmd += ["--year-max", str(year_max)]
    if max_files is not None:
        cmd += ["--max-files", str(max_files)]
    if no_exclude_name_keywords:
        cmd.append("--no-exclude-name-keywords")
    if extra_exclude_keywords:
        cmd += ["--extra-exclude-keywords", extra_exclude_keywords]
    return cmd


def run_subprocess(cmd: List[str]) -> Tuple[int, str]:
    r = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    tail = (r.stdout or "")[-4000:]
    return r.returncode, tail


def run_one_province(
    entry: Tuple[str, List[str], Path, Path],
    skip_existing: bool,
) -> Tuple[str, int, str]:
    sub, cmd, out_csv, _ = entry
    if skip_existing and out_csv.is_file() and out_csv.stat().st_size > 0:
        return sub, 0, "[skip-existing]"
    code, tail = run_subprocess(cmd)
    return sub, code, tail


def _safe_print_tail(tail: str, n: int = 1500) -> None:
    """Windows 下重定向到文件时 stdout 可能为 GBK，避免打印子进程 UTF-8 日志时崩溃。"""
    chunk = tail[-n:] if tail else ""
    try:
        print(chunk, flush=True)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "utf-8"
        print(chunk.encode(enc, errors="replace").decode(enc, errors="replace"), flush=True)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    test_dir = SCRIPT_DIR.parent.parent
    default_national = r"F:\BaiduNetdiskDownload\全国所有企业工商信息"
    default_division = test_dir / "township_county_division_2023.csv"
    default_industry = test_dir / "exclude_public_service_industry_gb2017.csv"
    default_partial = test_dir / "enterprise_parallel_partial"
    default_merged = test_dir / "township_enterprise_counts_by_year.csv"
    default_merged_stats = test_dir / "township_enterprise_extract_stats.json"

    ap = argparse.ArgumentParser(
        description="按省并行跑 02_extract_enterprises_to_township 并合并全国计数",
    )
    ap.add_argument("--national-root", default=default_national, help="全国企业工商根目录（含各省子文件夹）")
    ap.add_argument(
        "--partial-dir",
        default=str(default_partial),
        help="各省分片输出目录（counts + stats）",
    )
    ap.add_argument("--merged-output", "-o", default=str(default_merged), help="合并后的全国 CSV")
    ap.add_argument(
        "--merged-stats",
        default=str(default_merged_stats),
        help="合并后的统计 JSON（会覆盖单省跑时的同名文件，注意备份）",
    )
    ap.add_argument(
        "--workers",
        type=int,
        default=None,
        help="并行省任务数（默认 min(10, CPU逻辑核数)，高并发）",
    )
    ap.add_argument(
        "--only-subdirs",
        default=None,
        help="只处理这些子文件夹名，逗号分隔；默认处理根下全部省文件夹",
    )
    ap.add_argument("--skip-existing", action="store_true", help="若分省 counts 已存在则跳过该省")
    ap.add_argument("--dry-run", action="store_true", help="只打印将执行的省与命令，不运行")
    ap.add_argument("--division-csv", default=str(default_division))
    ap.add_argument("--industry-exclude-csv", default=str(default_industry))
    ap.add_argument("--year-min", type=int, default=None)
    ap.add_argument("--year-max", type=int, default=None)
    ap.add_argument("--max-files", type=int, default=None, help="每省最多处理 xlsx 数（调试用）")
    ap.add_argument("--no-exclude-name-keywords", action="store_true")
    ap.add_argument("--no-exclude-industry", action="store_true")
    ap.add_argument("--extra-exclude-keywords", default="")
    args = ap.parse_args()

    if not EXTRACT_SCRIPT.is_file():
        print(f"未找到: {EXTRACT_SCRIPT}", file=sys.stderr)
        sys.exit(1)

    national = os.path.abspath(args.national_root)
    partial_dir = Path(args.partial_dir)
    partial_dir.mkdir(parents=True, exist_ok=True)

    subdirs = list_province_subdirs(national)
    if args.only_subdirs:
        want = {s.strip() for s in args.only_subdirs.split(",") if s.strip()}
        subdirs = [s for s in subdirs if s in want]
        missing = want - set(subdirs)
        if missing:
            print(f"警告：未找到的子文件夹: {missing}", flush=True)

    if not subdirs:
        print("没有可处理的省子文件夹", file=sys.stderr)
        sys.exit(1)

    ncpu = os.cpu_count() or 4
    workers = args.workers if args.workers is not None else min(10, max(1, ncpu))
    workers = min(workers, len(subdirs))

    tasks: List[Tuple[str, List[str], Path, Path]] = []
    for sub in subdirs:
        stem = safe_stem(sub)
        out_csv = partial_dir / f"{stem}_counts.csv"
        out_stats = partial_dir / f"{stem}_stats.json"
        prov_root = os.path.join(national, sub)
        cmd = build_extract_command(
            EXTRACT_SCRIPT,
            prov_root,
            str(out_csv),
            str(out_stats),
            args.division_csv,
            args.industry_exclude_csv,
            args.year_min,
            args.year_max,
            args.max_files,
            args.no_exclude_name_keywords,
            args.no_exclude_industry,
            args.extra_exclude_keywords,
        )
        tasks.append((sub, cmd, out_csv, out_stats))

    print(f"全国根目录: {national}", flush=True)
    print(f"省任务数: {len(tasks)}，并行 workers: {workers}", flush=True)
    print(f"分片目录: {partial_dir}", flush=True)

    if args.dry_run:
        for sub, cmd, out_csv, _ in tasks:
            print("---", sub, "->", out_csv.name)
            print(" ", " ".join(cmd[:8]), "...")
        sys.exit(0)

    failed: List[str] = []
    ok_csvs: List[Path] = []
    ok_stats: List[Path] = []

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {
            ex.submit(run_one_province, t, args.skip_existing): t[0] for t in tasks
        }
        for fut in as_completed(futs):
            sub_hint = futs[fut]
            try:
                name, code, tail = fut.result()
            except Exception as e:
                print(f"[异常] {sub_hint}: {e}", flush=True)
                failed.append(sub_hint)
                continue
            if code != 0:
                print(f"[失败] {name} exit={code}", flush=True)
                _safe_print_tail(tail)
                failed.append(name)
                continue
            if tail == "[skip-existing]":
                print(f"[跳过] {name}", flush=True)
            else:
                print(f"[完成] {name}", flush=True)
            stem = safe_stem(name)
            oc = partial_dir / f"{stem}_counts.csv"
            os_ = partial_dir / f"{stem}_stats.json"
            if oc.is_file():
                ok_csvs.append(oc)
            if os_.is_file():
                ok_stats.append(os_)

    n_ok = len(tasks) - len(failed)
    ok_csvs = list(dict.fromkeys(ok_csvs))
    ok_stats = list(dict.fromkeys(ok_stats))
    merged_n = merge_count_csvs(ok_csvs, Path(args.merged_output))
    merge_stats_json(ok_stats, Path(args.merged_stats), n_ok)

    print(f"合并写入: {args.merged_output}（{merged_n} 行）", flush=True)
    print(f"统计写入: {args.merged_stats}", flush=True)
    if failed:
        print(f"失败 {len(failed)} 个省: {failed}", flush=True)
        sys.exit(2)


if __name__ == "__main__":
    main()
