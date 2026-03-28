# -*- coding: utf-8 -*-
"""
统计全国企业工商 xlsx 中「成立日期」解析出的年份范围（最早 / 最晚），
与 `extract_enterprises_to_township.py` 口径一致：

- **首张工作表**
- 日期列优先 **成立日期**，若无则 **注册日期**
- 年份解析复用 `parse_found_year`

**读取方式（高效）**：
- 使用 **openpyxl read_only**，只对日期列做 **iter_rows** 流式扫描，不把整列载入 pandas DataFrame。
- 运行中维护 **ymin / ymax**（等价于排序后首尾，不排序）。
- 可选 **--workers N**：多进程并行处理多个 xlsx（受磁盘带宽限制，默认 4）。

用法：
  python stats_enterprise_found_year_range.py
  python stats_enterprise_found_year_range.py --workers 8
"""

from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

try:
    from openpyxl import load_workbook
except ImportError as e:
    print("需要安装 openpyxl: pip install openpyxl", file=sys.stderr)
    raise SystemExit(1) from e

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from extract_enterprises_to_township import iter_enterprise_xlsx, parse_found_year  # noqa: E402


def _pick_date_col_index(header: tuple) -> int | None:
    names = [str(c).strip() if c is not None else "" for c in header]
    for want in ("成立日期", "注册日期"):
        for i, n in enumerate(names):
            if n == want:
                return i + 1
    return None


def scan_file(path: str) -> tuple[str, int | None, int | None, int, int, str | None]:
    """
    单列流式扫描。返回 (path, ymin, ymax, n_ok, n_bad, err)。
    path 原样带回便于多进程合并时对应文件。
    """
    try:
        wb = load_workbook(path, read_only=True, data_only=True)
    except Exception as e:
        return path, None, None, 0, 0, str(e)
    try:
        ws = wb.worksheets[0]
        it = ws.iter_rows(values_only=True)
        header = next(it, None)
        if not header:
            return path, None, None, 0, 0, "空表"
        col = _pick_date_col_index(header)
        if col is None:
            return path, None, None, 0, 0, "无「成立日期」或「注册日期」列"

        ymin: int | None = None
        ymax: int | None = None
        n_ok = 0
        n_bad = 0
        for row in it:
            if col > len(row):
                continue
            val = row[col - 1]
            y = parse_found_year(val)
            if y is None:
                n_bad += 1
                continue
            n_ok += 1
            if ymin is None or y < ymin:
                ymin = y
            if ymax is None or y > ymax:
                ymax = y
        return path, ymin, ymax, n_ok, n_bad, None
    except Exception as e:
        return path, None, None, 0, 0, str(e)
    finally:
        wb.close()


def _default_workers() -> int:
    """机械盘过多并行易打满磁头，默认 4；SSD 可 `-j 8`。"""
    n = os.cpu_count() or 4
    return max(1, min(4, n))


def main() -> None:
    default_root = r"F:\BaiduNetdiskDownload\全国所有企业工商信息"
    ap = argparse.ArgumentParser(description="企业工商数据：成立/注册日期年份范围（read_only 单列 + min/max）")
    ap.add_argument("--root", default=default_root, help="全国企业工商根目录（与提取脚本相同）")
    ap.add_argument("--max-files", type=int, default=None, help="最多处理文件数（调试）")
    ap.add_argument(
        "--workers",
        "-j",
        type=int,
        default=_default_workers(),
        help=f"并行处理文件数（默认 {_default_workers()}，设为 1 则单进程）",
    )
    args = ap.parse_args()

    root = args.root
    if not os.path.isdir(root):
        print(f"目录不存在: {root}", file=sys.stderr)
        sys.exit(1)

    files = iter_enterprise_xlsx(root, None)
    if args.max_files is not None:
        files = files[: args.max_files]
    n_files = len(files)
    print(f"根目录: {root}", flush=True)
    print(f"xlsx 文件数: {n_files}", flush=True)
    print(
        f"模式: openpyxl read_only 单列流式扫描 + min/max；workers={args.workers}",
        flush=True,
    )

    global_min: int | None = None
    global_max: int | None = None
    total_ok = 0
    total_bad = 0
    n_err = 0
    n_skip_col = 0
    done = 0

    if args.workers <= 1:
        for i, fp in enumerate(files, start=1):
            _p, ymin, ymax, n_ok, n_bad, err = scan_file(fp)
            if err:
                n_err += 1
                if err == "无「成立日期」或「注册日期」列":
                    n_skip_col += 1
                print(f"[错误] {fp}\n  {err}", flush=True)
                continue
            total_ok += n_ok
            total_bad += n_bad
            if ymin is not None:
                if global_min is None or ymin < global_min:
                    global_min = ymin
            if ymax is not None:
                if global_max is None or ymax > global_max:
                    global_max = ymax
            if i % 50 == 0 or i == n_files:
                print(f"  进度 {i}/{n_files} …", flush=True)
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            futs = {ex.submit(scan_file, fp): fp for fp in files}
            for fut in as_completed(futs):
                fp = futs[fut]
                done += 1
                try:
                    _p, ymin, ymax, n_ok, n_bad, err = fut.result()
                except Exception as e:
                    n_err += 1
                    print(f"[错误] {fp}\n  {e}", flush=True)
                    continue
                if err:
                    n_err += 1
                    if err == "无「成立日期」或「注册日期」列":
                        n_skip_col += 1
                    print(f"[错误] {fp}\n  {err}", flush=True)
                    continue
                total_ok += n_ok
                total_bad += n_bad
                if ymin is not None:
                    if global_min is None or ymin < global_min:
                        global_min = ymin
                if ymax is not None:
                    if global_max is None or ymax > global_max:
                        global_max = ymax
                if done % 50 == 0 or done == n_files:
                    print(f"  进度 {done}/{n_files} …", flush=True)

    print("---", flush=True)
    print("口径：首张工作表；日期列=成立日期（无则注册日期）；年份解析同 extract_enterprises_to_township", flush=True)
    if global_min is not None and global_max is not None:
        print(f"全部有效年份范围: {global_min} — {global_max}", flush=True)
    else:
        print("全部有效年份范围: （无有效年份）", flush=True)
    print(f"解析到年份的行数: {total_ok:,}", flush=True)
    print(f"无法解析日期的行数: {total_bad:,}", flush=True)
    print(f"读取失败或其它错误文件数: {n_err}", flush=True)
    print(f"其中缺日期列文件数: {n_skip_col}", flush=True)


if __name__ == "__main__":
    main()
