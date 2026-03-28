# -*- coding: utf-8 -*-
"""
按 **`part_*.csv` 分片**并行调用 `02_extract_enterprises_csv_to_township.py`，
再合并为全国的 **`年份 × 乡镇 code` 计数表**（与 `scripts/enterprise/03_run_extract_enterprises_parallel.py`
对各省 xlsx 的分工一致）。

用法：
  python 03_run_extract_csv_parallel.py --dry-run
  python 03_run_extract_csv_parallel.py --workers 4
  python 03_run_extract_csv_parallel.py --only-parts part_000.csv,part_001.csv
"""

from __future__ import annotations

import argparse
import glob
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
TEST_DIR = SCRIPT_DIR.parent
EXTRACT_SCRIPT = SCRIPT_DIR / "02_extract_enterprises_csv_to_township.py"


def safe_stem(name: str, max_len: int = 100) -> str:
    s = re.sub(r'[<>:"/\\|?*\n\r]', "_", name.strip())
    return s[:max_len] if len(s) > max_len else s


def resolve_csv_dir(root: str) -> str:
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        return root
    if glob.glob(os.path.join(root, "part_*.csv")):
        return root
    subs = [
        os.path.join(root, name)
        for name in sorted(os.listdir(root))
        if os.path.isdir(os.path.join(root, name))
    ]
    for d in subs:
        if glob.glob(os.path.join(d, "part_*.csv")):
            return d
    return root


def default_csv_root() -> str:
    return r"F:\BaiduNetdiskDownload\1223工商企业信息（1989-2022）"


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


def merge_stats_json(paths: List[Path], out: Path, n_parts_ok: int) -> None:
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
    merged["provinces_parallel_ok"] = n_parts_ok
    merged["csv_parts_parallel_ok"] = n_parts_ok
    out.write_text(json.dumps(dict(merged), ensure_ascii=False, indent=2), encoding="utf-8")


def build_cmd(
    csv_path: str,
    out_csv: str,
    stats_json: str,
    division_csv: str,
    industry_exclude_csv: str,
    year_min: Optional[int],
    year_max: Optional[int],
    chunksize: int,
    encoding: str,
    max_rows: Optional[int],
    no_exclude_name_keywords: bool,
    no_exclude_industry: bool,
    extra_exclude_keywords: str,
    date_usa: bool,
) -> List[str]:
    cmd: List[str] = [
        sys.executable,
        str(EXTRACT_SCRIPT),
        "--csv-path",
        csv_path,
        "-o",
        out_csv,
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
    cmd += ["--chunksize", str(chunksize)]
    cmd += ["--encoding", encoding]
    if max_rows is not None:
        cmd += ["--max-rows", str(max_rows)]
    if no_exclude_name_keywords:
        cmd.append("--no-exclude-name-keywords")
    if extra_exclude_keywords:
        cmd += ["--extra-exclude-keywords", extra_exclude_keywords]
    if date_usa:
        cmd.append("--date-usa")
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


def run_one_part(
    entry: Tuple[str, List[str], Path, Path],
    skip_existing: bool,
) -> Tuple[str, int, str]:
    sub, cmd, out_csv, _ = entry
    if skip_existing and out_csv.is_file() and out_csv.stat().st_size > 0:
        return sub, 0, "[skip-existing]"
    code, tail = run_subprocess(cmd)
    return sub, code, tail


def _safe_print_tail(tail: str, n: int = 1500) -> None:
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

    default_division = TEST_DIR / "township_county_division_2023.csv"
    default_industry = TEST_DIR / "exclude_public_service_industry_gb2017.csv"
    default_partial = SCRIPT_DIR / "enterprise_parallel_partial"
    default_merged = SCRIPT_DIR / "township_enterprise_counts_by_year_csv_2000_2022.csv"
    default_merged_stats = SCRIPT_DIR / "township_enterprise_extract_stats_csv_merged.json"

    ap = argparse.ArgumentParser(
        description="按 part 分片并行跑 02_extract_enterprises_csv_to_township 并合并",
    )
    ap.add_argument(
        "--csv-root",
        default=default_csv_root(),
        help="1223 数据根目录（自动解析含 part_*.csv 的子目录）",
    )
    ap.add_argument(
        "--partial-dir",
        default=str(default_partial),
        help="各分片 counts / stats 输出目录",
    )
    ap.add_argument(
        "--merged-output",
        "-o",
        default=str(default_merged),
        help="合并后的全国 CSV",
    )
    ap.add_argument(
        "--merged-stats",
        default=str(default_merged_stats),
        help="合并后的统计 JSON",
    )
    ap.add_argument(
        "--workers",
        type=int,
        default=None,
        help="并行分片任务数（默认 min(4, CPU核数)，避免机械硬盘同时随机读过多文件）",
    )
    ap.add_argument(
        "--only-parts",
        default=None,
        help="只处理这些文件名，逗号分隔，如 part_000.csv,part_001.csv",
    )
    ap.add_argument("--skip-existing", action="store_true", help="若分片 counts 已存在则跳过")
    ap.add_argument("--dry-run", action="store_true", help="只打印命令，不运行")
    ap.add_argument("--division-csv", default=str(default_division))
    ap.add_argument("--industry-exclude-csv", default=str(default_industry))
    ap.add_argument("--year-min", type=int, default=2000)
    ap.add_argument("--year-max", type=int, default=2022)
    ap.add_argument("--chunksize", type=int, default=50_000)
    ap.add_argument("--encoding", default="utf-8-sig")
    ap.add_argument("--max-rows", type=int, default=None, help="每分片最多行数（调试用）")
    ap.add_argument("--no-exclude-name-keywords", action="store_true")
    ap.add_argument("--no-exclude-industry", action="store_true")
    ap.add_argument("--extra-exclude-keywords", default="")
    ap.add_argument(
        "--date-usa",
        action="store_true",
        help="传给 02：按月/日/年解析成立日期",
    )
    args = ap.parse_args()

    if not EXTRACT_SCRIPT.is_file():
        print(f"未找到: {EXTRACT_SCRIPT}", file=sys.stderr)
        sys.exit(1)

    csv_dir = resolve_csv_dir(args.csv_root)
    if not os.path.isdir(csv_dir):
        print(f"目录不存在: {csv_dir}", file=sys.stderr)
        sys.exit(1)

    all_parts = sorted(glob.glob(os.path.join(csv_dir, "part_*.csv")))
    if args.only_parts:
        want = {s.strip() for s in args.only_parts.split(",") if s.strip()}
        all_parts = [p for p in all_parts if os.path.basename(p) in want]
        missing = want - {os.path.basename(p) for p in all_parts}
        if missing:
            print(f"警告：未找到分片: {missing}", flush=True)

    if not all_parts:
        print("没有可处理的 part_*.csv", file=sys.stderr)
        sys.exit(1)

    partial_dir = Path(args.partial_dir)
    partial_dir.mkdir(parents=True, exist_ok=True)

    ncpu = os.cpu_count() or 4
    workers = args.workers if args.workers is not None else min(4, max(1, ncpu))
    workers = min(workers, len(all_parts))

    tasks: List[Tuple[str, List[str], Path, Path]] = []
    for fp in all_parts:
        base = os.path.basename(fp)
        stem = safe_stem(Path(base).stem)
        out_csv = partial_dir / f"{stem}_counts.csv"
        out_stats = partial_dir / f"{stem}_stats.json"
        cmd = build_cmd(
            fp,
            str(out_csv),
            str(out_stats),
            args.division_csv,
            args.industry_exclude_csv,
            args.year_min,
            args.year_max,
            args.chunksize,
            args.encoding,
            args.max_rows,
            args.no_exclude_name_keywords,
            args.no_exclude_industry,
            args.extra_exclude_keywords,
            args.date_usa,
        )
        tasks.append((base, cmd, out_csv, out_stats))

    print(f"CSV 目录: {csv_dir}", flush=True)
    print(f"分片任务数: {len(tasks)}，并行 workers: {workers}", flush=True)
    print(f"分片输出目录: {partial_dir}", flush=True)

    if args.dry_run:
        for sub, cmd, out_csv, _ in tasks:
            print("---", sub, "->", out_csv.name)
            print(" ", " ".join(cmd[:10]), "...")
        sys.exit(0)

    failed: List[str] = []
    ok_csvs: List[Path] = []
    ok_stats: List[Path] = []

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(run_one_part, t, args.skip_existing): t[0] for t in tasks}
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
            stem = safe_stem(Path(name).stem)
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
        print(f"失败 {len(failed)} 个分片: {failed}", flush=True)
        sys.exit(2)


if __name__ == "__main__":
    main()
