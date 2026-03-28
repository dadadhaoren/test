# -*- coding: utf-8 -*-
"""
统计「1223 工商企业信息」分片 CSV（`part_*.csv`）中的**企业注册记录条数**。

约定：每个分片首行为表头，**数据行 = 文件行数 − 1**（与 `scripts/enterprise/06_count_enterprise_registrations_total.py`
对 xlsx 的口径一致）。

**性能**：按二进制块扫描，仅统计换行符数量，不解析 CSV 单元格；适合单文件数 GB、总量约百 GB 的数据。

**注意**：若某字段内含未转义的换行符（多行单元格），行数会高于真实记录数。此类情况可改用 DuckDB
`read_csv` 或 `csv.reader` 抽样核对；本机该批数据通常为单行一条记录。

用法：
  python 01_count_part_csv_records.py
  python 01_count_part_csv_records.py --root "F:\\BaiduNetdiskDownload\\1223工商企业信息（1989-2022）"
  python 01_count_part_csv_records.py --verbose
"""

from __future__ import annotations

import argparse
import glob
import os
import sys


CHUNK = 8 * 1024 * 1024  # 8 MiB


def default_data_root() -> str:
    return r"F:\BaiduNetdiskDownload\1223工商企业信息（1989-2022）"


def resolve_csv_dir(root: str) -> str:
    """若根目录下无 part_*.csv，则使用第一个包含该模式的子目录。"""
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


def count_newlines(path: str) -> int:
    """统计文件中 \\n 出现次数（CRLF 记为 1 行）。"""
    n = 0
    with open(path, "rb") as f:
        while True:
            chunk = f.read(CHUNK)
            if not chunk:
                break
            n += chunk.count(b"\n")
    return n


def main() -> None:
    ap = argparse.ArgumentParser(
        description="分片 CSV（part_*.csv）企业记录条数统计（二进制换行计数，快速）"
    )
    ap.add_argument("--root", default=default_data_root(), help="数据根目录（或已含 part_*.csv 的子目录）")
    ap.add_argument(
        "--pattern",
        default="part_*.csv",
        help="分片文件名 glob，默认 part_*.csv",
    )
    ap.add_argument("-v", "--verbose", action="store_true", help="每个分片打印一行计数")
    args = ap.parse_args()

    csv_dir = resolve_csv_dir(args.root)
    if not os.path.isdir(csv_dir):
        print(f"目录不存在: {csv_dir}", file=sys.stderr)
        sys.exit(1)

    paths = sorted(glob.glob(os.path.join(csv_dir, args.pattern)))
    if not paths:
        print(f"未找到文件: {os.path.join(csv_dir, args.pattern)}", file=sys.stderr)
        sys.exit(1)

    print(f"数据目录: {csv_dir}", flush=True)
    print(f"匹配文件数: {len(paths)}", flush=True)

    grand_lines = 0
    grand_records = 0
    for i, fp in enumerate(paths, start=1):
        lines = count_newlines(fp)
        rec = max(0, lines - 1)  # 表头
        grand_lines += lines
        grand_records += rec
        if args.verbose:
            print(f"[{i}/{len(paths)}] {rec:>12,} 行(数据)  {os.path.basename(fp)}", flush=True)
        elif i % 5 == 0 or i == len(paths):
            print(f"  进度 {i}/{len(paths)}，累计记录 {grand_records:,} …", flush=True)

    print("---", flush=True)
    print(f"分片文件合计数据行（每文件已减 1 行表头）: {grand_records:,}", flush=True)
    print(f"原始换行合计（含表头行）: {grand_lines:,}", flush=True)


if __name__ == "__main__":
    main()
