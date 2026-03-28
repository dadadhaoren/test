# -*- coding: utf-8 -*-
"""
统计 `全国所有企业工商信息` 目录下**全部** xlsx 中的企业记录条数（按工作表行数计，
默认：**活动工作表**（与 Excel 打开时选中的表一致，对应 workbookView activeTab），
首行视为表头，**数据行 = 总行数 − 1**）。

与 `02_extract_enterprises_to_township.py` 目录结构一致：根目录下各省子文件夹，内为 `*.xlsx`。

**性能**：优先用 zip + 工作表 XML 中 `<row` 计数（不解析单元格），比 openpyxl 逐行迭代快一个数量级以上；
解析失败时回退到 openpyxl（需安装 openpyxl）。

用法：
  python 06_count_enterprise_registrations_total.py
  python 06_count_enterprise_registrations_total.py --root "F:\\...\\全国所有企业工商信息"
  python 06_count_enterprise_registrations_total.py --all-sheets
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

try:
    from openpyxl import load_workbook

    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

# 工作表行：`<row r="1"` / `<row>`；排除 `<rowBreaks` 等
_ROW_OPEN_RE = re.compile(rb"<row(?=[\s>])")


def iter_xlsx_files(root: str) -> list[str]:
    root = os.path.abspath(root)
    paths: list[str] = []
    for sub in sorted(os.listdir(root)):
        d = os.path.join(root, sub)
        if not os.path.isdir(d):
            continue
        for fp in glob.glob(os.path.join(d, "*.xlsx")):
            if os.path.isfile(fp):
                paths.append(fp)
    return sorted(paths)


def _parse_workbook_rels(z: zipfile.ZipFile) -> dict[str, str]:
    """Id -> Target（如 worksheets/sheet1.xml，相对 xl/）。"""
    data = z.read("xl/_rels/workbook.xml.rels")
    root = ET.fromstring(data)
    out: dict[str, str] = {}
    for rel in root:
        if not rel.tag.endswith("Relationship"):
            continue
        rid = rel.get("Id")
        target = rel.get("Target")
        if not rid or not target:
            continue
        # 只关心 worksheets/（排除 chartsheets、外部链接等）
        if "worksheets" not in target.replace("\\", "/").lower():
            continue
        out[rid] = target.replace("\\", "/")
    return out


def _ordered_sheet_rids(wb_xml: bytes) -> list[str]:
    """按工作簿中 sheet 元素出现顺序列出 r:id（兼容 `main:sheet` 等前缀）。"""
    pat = re.compile(rb'<(?:[\w.]+:)?sheet\b[^>]*r:id="([^"]+)"', re.IGNORECASE)
    return [m.decode("ascii", errors="replace") for m in pat.findall(wb_xml)]


def _active_tab_index(wb_xml: bytes) -> int:
    m = re.search(rb'activeTab="(\d+)"', wb_xml)
    if not m:
        return 0
    return int(m.group(1))


def _xl_path_for_sheet_target(target: str) -> str:
    t = target.replace("\\", "/").lstrip("/")
    if t.startswith("xl/"):
        return t
    return "xl/" + t


def _count_row_tags_in_bytes(data: bytes) -> int:
    return len(_ROW_OPEN_RE.findall(data))


def _count_rows_worksheet_member(z: zipfile.ZipFile, member: str) -> int:
    """member 为 zip 内路径，如 xl/worksheets/sheet1.xml。"""
    info = z.getinfo(member)
    # 大表用分块扫描，避免整文件进内存；小块重叠避免跨块截断漏计
    overlap = 64
    if info.file_size <= 32 * 1024 * 1024:
        return _count_row_tags_in_bytes(z.read(member))

    total = 0
    carry = b""
    with z.open(member, "r") as f:
        while True:
            chunk = f.read(4 * 1024 * 1024)
            if not chunk:
                break
            buf = carry + chunk
            if len(buf) > overlap:
                scan = buf[:-overlap]
                total += _count_row_tags_in_bytes(scan)
                carry = buf[len(scan) :]
            else:
                carry = buf
        total += _count_row_tags_in_bytes(carry)
    return total


def count_file_fast(path: str, all_sheets: bool) -> tuple[int, str | None]:
    """ZIP/XML 快速计数。失败返回 (0, err)。"""
    try:
        with zipfile.ZipFile(path, "r") as z:
            try:
                wb_xml = z.read("xl/workbook.xml")
            except KeyError:
                return 0, "缺少 xl/workbook.xml"

            rid_to_target = _parse_workbook_rels(z)
            rids = _ordered_sheet_rids(wb_xml)
            if not rids:
                return 0, "未解析到任何 sheet"

            active_idx = _active_tab_index(wb_xml)
            if active_idx >= len(rids):
                active_idx = 0

            def rows_for_rid(rid: str) -> int:
                target = rid_to_target.get(rid)
                if not target:
                    return 0
                full = _xl_path_for_sheet_target(target)
                try:
                    z.getinfo(full)
                except KeyError:
                    return 0
                nrows = _count_rows_worksheet_member(z, full)
                if nrows > 0:
                    nrows -= 1  # 表头
                return max(0, nrows)

            if all_sheets:
                total = 0
                for rid in rids:
                    total += rows_for_rid(rid)
                return total, None

            rid = rids[active_idx]
            return rows_for_rid(rid), None
    except zipfile.BadZipFile as e:
        return 0, f"非有效 zip/xlsx: {e}"
    except Exception as e:
        return 0, str(e)


def count_rows_one_sheet(ws, subtract_header: bool = True) -> int:
    n = 0
    for _ in ws.iter_rows():
        n += 1
    if subtract_header and n > 0:
        n -= 1
    return max(0, n)


def count_file_openpyxl(path: str, all_sheets: bool) -> tuple[int, str | None]:
    if not HAS_OPENPYXL:
        return 0, "需要 openpyxl: pip install openpyxl"
    try:
        wb = load_workbook(path, read_only=True, data_only=True)
    except Exception as e:
        return 0, str(e)
    try:
        total = 0
        if all_sheets:
            for ws in wb.worksheets:
                total += count_rows_one_sheet(ws, subtract_header=True)
        else:
            ws = wb.active
            total = count_rows_one_sheet(ws, subtract_header=True)
        return total, None
    except Exception as e:
        return 0, str(e)
    finally:
        wb.close()


def count_file(path: str, all_sheets: bool) -> tuple[int, str | None]:
    n, err = count_file_fast(path, all_sheets)
    if err is None:
        return n, None
    # 快速路径失败时用 openpyxl（列宽/宏表等异常结构）
    n2, err2 = count_file_openpyxl(path, all_sheets)
    if err2 is None:
        return n2, None
    return 0, f"fast: {err}; openpyxl: {err2}"


def main() -> None:
    default_root = r"F:\BaiduNetdiskDownload\全国所有企业工商信息"
    ap = argparse.ArgumentParser(description="统计全国企业工商 xlsx 总记录条数（ZIP 快速计数）")
    ap.add_argument("--root", default=default_root, help="全国企业工商根目录")
    ap.add_argument(
        "--all-sheets",
        action="store_true",
        help="统计工作簿内所有工作表（默认仅活动表，与 wb.active 一致）",
    )
    ap.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="每个文件打印一行计数",
    )
    ap.add_argument(
        "--openpyxl-only",
        action="store_true",
        help="强制仅用 openpyxl（调试用，较慢）",
    )
    args = ap.parse_args()

    root = args.root
    if not os.path.isdir(root):
        print(f"目录不存在: {root}", file=sys.stderr)
        sys.exit(1)

    files = iter_xlsx_files(root)
    print(f"根目录: {root}", flush=True)
    print(f"xlsx 文件数: {len(files)}", flush=True)

    grand = 0
    n_err = 0
    for i, fp in enumerate(files, start=1):
        if args.openpyxl_only:
            n, err = count_file_openpyxl(fp, args.all_sheets)
        else:
            n, err = count_file(fp, args.all_sheets)
        if err:
            n_err += 1
            print(f"[错误] {fp}\n  {err}", flush=True)
            continue
        grand += n
        if args.verbose:
            print(f"[{i}/{len(files)}] {n:>8}  {os.path.basename(fp)}", flush=True)
        elif i % 50 == 0 or i == len(files):
            print(f"  进度 {i}/{len(files)}，累计 {grand:,} 条 …", flush=True)

    print("---", flush=True)
    print(f"合计数据行（首行表头已减）: {grand:,}", flush=True)
    print(f"失败文件数: {n_err}", flush=True)


if __name__ == "__main__":
    main()
