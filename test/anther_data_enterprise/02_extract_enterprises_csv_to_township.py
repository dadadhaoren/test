# -*- coding: utf-8 -*-
"""
1223 分片 CSV（`part_*.csv`）→ 乡镇级匹配与按年汇总。

与 `scripts/enterprise/02_extract_enterprises_to_township.py` 口径对齐：
- 区县锁定：优先用 **`district_code`（6 位）** 与 `township_county_division_2023.csv` 中
  **`区县_县级码`** 对齐；若为**地级码**（如深圳市 `440300`），则在该地级市下**逐区县**
  尝试乡镇子串匹配，直至命中（县级名按长度降序尝试，减少误匹配）。
- `district` 常为 `-`，不作为主键；若日后需文本解析可再扩展。
- **注册地址** `reg_addr` 与区划表乡镇 **Name** 子串匹配（同 02）。
- **成立年份**：`start_date`（对标 xlsx「成立日期」）。
- **剔除**：`ent_name` 默认关键词；`industry` 与国标剔除表做**子串**匹配（1223 无国标中类/小类列，与 xlsx 精确匹配不等价，见 **`README.md` §1.1**）。
- **性能**：分块内用 **NumPy / pandas 向量化**解析成立年并做行业、公司名过滤，仅对剩余行做乡镇匹配（瓶颈仍在字符串匹配）。

用法：
  python 02_extract_enterprises_csv_to_township.py --csv-path "F:\\...\\part_000.csv"
  python 02_extract_enterprises_csv_to_township.py --csv-path ... --max-rows 5000
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd

CountyKey = Tuple[str, str, str]

SCRIPT_DIR = Path(__file__).resolve().parent
TEST_DIR = SCRIPT_DIR.parent
ENTERPRISE_DIR = TEST_DIR / "scripts" / "enterprise"
EXTRACT_XLSX_PATH = ENTERPRISE_DIR / "02_extract_enterprises_to_township.py"


def load_ext02():
    if not EXTRACT_XLSX_PATH.is_file():
        raise FileNotFoundError(f"未找到: {EXTRACT_XLSX_PATH}")
    spec = importlib.util.spec_from_file_location("ext02", EXTRACT_XLSX_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 02_extract_enterprises_to_township")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def norm_code6(v: Any) -> Optional[str]:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    if not s or s.lower() in ("nan", "none", "<na>"):
        return None
    if s.endswith(".0") and s[:-2].replace(".", "").isdigit():
        s = s[:-2]
    if not s.replace(".", "").isdigit():
        return None
    try:
        return str(int(float(s))).zfill(6)
    except (ValueError, OverflowError):
        return None


def norm_district_code(v: Any) -> Optional[str]:
    """企业表 district_code → 6 位字符串；无效返回 None。"""
    c = norm_code6(v)
    if c is None or c == "000000":
        return None
    return c


def load_county_and_prefecture_maps(
    division_csv: str,
    clean_cell,
) -> Tuple[Dict[str, CountyKey], Dict[str, List[CountyKey]]]:
    df = pd.read_csv(division_csv, encoding="utf-8-sig", dtype=str)
    county_map: Dict[str, CountyKey] = {}
    pref_groups: Dict[str, Set[CountyKey]] = defaultdict(set)

    for _, row in df.iterrows():
        p = clean_cell(row["区县_省级"])
        c = clean_cell(row["区县_地级"])
        co = clean_cell(row["区县_县级"])
        if not p or not c or not co:
            continue
        cc = norm_code6(row.get("区县_县级码"))
        dc = norm_code6(row.get("区县_地级码"))
        if cc:
            county_map[cc] = (p, c, co)
        if dc and dc != "000000":
            pref_groups[dc].add((p, c, co))

    pref_map: Dict[str, List[CountyKey]] = {}
    for dc, keys in pref_groups.items():
        pref_map[dc] = sorted(keys, key=lambda t: (-len(t[2]), t[2]))

    return county_map, pref_map


def parse_found_year_csv(v: Any, dayfirst: bool) -> Optional[int]:
    """
    成立日期 → 年份。与 02 的 parse_found_year 一致，但对 `pd.to_datetime` 增加 `dayfirst`
    （1223 导出多为日/月/年，如 9/4/2015）。
    """
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, datetime):
        return int(v.year)
    if hasattr(v, "year") and not isinstance(v, str):
        try:
            return int(v.year)
        except Exception:
            pass
    s = str(v).strip()
    if not s or s.lower() == "nan":
        return None
    m = re.match(r"^(\d{4})", s)
    if m:
        y = int(m.group(1))
        if 1800 <= y <= 2100:
            return y
    try:
        dt = pd.to_datetime(s, errors="coerce", dayfirst=dayfirst)
        if pd.isna(dt):
            return None
        return int(dt.year)
    except Exception:
        return None


def should_exclude_industry_csv(
    industry_str: str,
    mids: Set[str],
    smalls: Set[str],
    clean_cell,
) -> bool:
    """行业列多为简短中文描述：剔除名称为子串即排除。"""
    s = clean_cell(industry_str)
    if not s:
        return False
    for m in mids:
        if m and m in s:
            return True
    for sm in smalls:
        if sm and sm in s:
            return True
    return False


def vectorize_years(start_date: pd.Series, dayfirst: bool) -> np.ndarray:
    """
    与 `parse_found_year_csv` 口径一致：先 `YYYY` 前缀，再 `pd.to_datetime`。
    返回 float64，无效为 nan。
    """
    s = start_date.fillna("").astype(str).str.strip()
    n = len(s)
    years = np.full(n, np.nan, dtype=np.float64)
    y4 = s.str.extract(r"^(\d{4})", expand=False)
    y4_num = pd.to_numeric(y4, errors="coerce")
    ok_prefix = (y4_num >= 1800) & (y4_num <= 2100)
    if ok_prefix.any():
        years[ok_prefix.to_numpy(copy=False)] = y4_num[ok_prefix].astype(float).to_numpy()

    need_dt = (~ok_prefix) & s.ne("") & s.str.lower().ne("nan")
    if need_dt.any():
        sub = s[need_dt]
        dt_y = pd.to_datetime(sub, errors="coerce", dayfirst=dayfirst).dt.year
        idx = need_dt.to_numpy(copy=False)
        v = np.asarray(dt_y, dtype=np.float64)
        years[idx] = np.where(np.isfinite(v), v, years[idx])
    return years


def build_industry_exclude_mask(industry: pd.Series, mids: Set[str], smalls: Set[str]) -> np.ndarray:
    """向量化：行业字符串包含任一剔除名则 True。"""
    if not mids and not smalls:
        return np.zeros(len(industry), dtype=bool)
    ind = industry.fillna("").astype(str)
    bad = np.zeros(len(industry), dtype=bool)
    for m in mids:
        if m:
            bad |= ind.str.contains(re.escape(m), regex=True, na=False)
    for sm in smalls:
        if sm:
            bad |= ind.str.contains(re.escape(sm), regex=True, na=False)
    return bad


def build_name_exclude_mask(ent_name: pd.Series, keywords: Tuple[str, ...]) -> np.ndarray:
    """向量化：公司名包含任一关键词则 True。"""
    if not keywords:
        return np.zeros(len(ent_name), dtype=bool)
    n = ent_name.fillna("").astype(str)
    bad = np.zeros(len(ent_name), dtype=bool)
    for kw in keywords:
        if kw:
            bad |= n.str.contains(kw, regex=False, na=False)
    return bad


def match_township_with_code(
    district_code_raw: Any,
    reg_addr: str,
    cmap: Dict[CountyKey, Any],
    county_map: Dict[str, CountyKey],
    pref_map: Dict[str, List[CountyKey]],
    mod,
) -> Tuple[Optional[str], Optional[str], str]:
    """
    返回 (乡镇 code, 乡镇 Name, 原因)。
    原因: ok | county_miss | addr_empty | township_miss
    """
    clean_cell = mod.clean_cell
    match_township_code = mod.match_township_code

    code = norm_district_code(district_code_raw)
    if code is None:
        return None, None, "county_miss"

    addr = clean_cell(reg_addr)
    if not addr:
        return None, None, "addr_empty"

    if code in county_map:
        p, c, co = county_map[code]
        return match_township_code(p, c, co, addr, cmap)

    if code in pref_map:
        for p, c, co in pref_map[code]:
            tc, tn, reason = match_township_code(p, c, co, addr, cmap)
            if reason == "ok" and tc:
                return tc, tn, "ok"
        return None, None, "township_miss"

    return None, None, "county_miss"


def process_csv(
    csv_path: str,
    cmap: Dict[CountyKey, Any],
    county_map: Dict[str, CountyKey],
    pref_map: Dict[str, List[CountyKey]],
    mod,
    year_min: Optional[int],
    year_max: Optional[int],
    date_dayfirst: bool,
    exclude_keywords: Tuple[str, ...],
    use_name_exclude: bool,
    industry_mid: Set[str],
    industry_small: Set[str],
    use_industry_exclude: bool,
    stats: Dict[str, int],
    counts: Counter,
    chunksize: int,
    encoding: str,
    max_rows: Optional[int],
) -> None:
    clean_cell = mod.clean_cell

    usecols = [
        "ent_name",
        "start_date",
        "district_code",
        "district",
        "reg_addr",
        "industry",
    ]

    rows_seen = 0
    reader = pd.read_csv(
        csv_path,
        encoding=encoding,
        encoding_errors="replace",
        dtype=str,
        chunksize=chunksize,
        usecols=usecols,
        low_memory=False,
    )

    for chunk in reader:
        chunk = chunk.reindex(columns=usecols)
        if max_rows is not None:
            remain = max_rows - rows_seen
            if remain <= 0:
                return
            if len(chunk) > remain:
                chunk = chunk.iloc[:remain].copy()

        n_chunk = len(chunk)
        rows_seen += n_chunk
        stats["rows_total"] += n_chunk

        years = vectorize_years(chunk["start_date"], date_dayfirst)
        has_year = np.isfinite(years)
        in_range = has_year.copy()
        if year_min is not None:
            in_range &= years >= year_min
        if year_max is not None:
            in_range &= years <= year_max

        stats["skip_no_year"] += int((~has_year).sum())
        stats["skip_year_range"] += int((has_year & ~in_range).sum())

        ind_bad = (
            build_industry_exclude_mask(chunk["industry"], industry_mid, industry_small)
            if use_industry_exclude and (industry_mid or industry_small)
            else np.zeros(n_chunk, dtype=bool)
        )
        stats["skip_industry"] = stats.get("skip_industry", 0) + int(
            (in_range & ind_bad).sum()
        )

        name_bad = (
            build_name_exclude_mask(chunk["ent_name"], exclude_keywords)
            if use_name_exclude
            else np.zeros(n_chunk, dtype=bool)
        )
        stats["skip_name_keyword"] += int((in_range & ~ind_bad & name_bad).sum())

        keep = in_range & ~ind_bad & ~name_bad
        if not keep.any():
            continue

        y_arr = years[keep].astype(np.int32)
        dc_arr = chunk.loc[keep, "district_code"].to_numpy(dtype=object, copy=False)
        ra_arr = chunk.loc[keep, "reg_addr"].to_numpy(dtype=object, copy=False)

        for i in range(len(y_arr)):
            code, _tname, reason = match_township_with_code(
                dc_arr[i],
                clean_cell(ra_arr[i]),
                cmap,
                county_map,
                pref_map,
                mod,
            )
            stats[f"match_{reason}"] = stats.get(f"match_{reason}", 0) + 1
            if reason != "ok" or code is None:
                continue
            yr = int(y_arr[i])
            counts[(yr, code)] += 1


def main() -> None:
    default_division = TEST_DIR / "township_county_division_2023.csv"
    default_industry_exclude = TEST_DIR / "exclude_public_service_industry_gb2017.csv"

    ap = argparse.ArgumentParser(
        description="1223 工商 CSV → 乡镇 × 成立年份计数",
    )
    ap.add_argument("--csv-path", required=True, help="单个分片 CSV，如 part_000.csv")
    ap.add_argument(
        "--division-csv",
        default=str(default_division),
        help="乡镇区划表",
    )
    ap.add_argument(
        "-o",
        "--output",
        default=None,
        help="输出 年份×code×n；默认写到 partial 目录下按文件名推导",
    )
    ap.add_argument("--stats-json", default=None, help="统计 JSON")
    ap.add_argument("--year-min", type=int, default=2000, help="成立年下限（含），默认 2000")
    ap.add_argument("--year-max", type=int, default=2022, help="成立年上限（含），默认 2022")
    ap.add_argument(
        "--chunksize",
        type=int,
        default=50_000,
        help="pandas 分块行数",
    )
    ap.add_argument(
        "--encoding",
        default="utf-8-sig",
        help="CSV 编码，默认 utf-8-sig",
    )
    ap.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="最多处理数据行（调试用）",
    )
    ap.add_argument(
        "--no-exclude-name-keywords",
        action="store_true",
        help="不按公司名称默认关键词剔除",
    )
    ap.add_argument(
        "--industry-exclude-csv",
        default=str(default_industry_exclude),
        help="行业剔除表；空路径表示不读",
    )
    ap.add_argument(
        "--no-exclude-industry",
        action="store_true",
        help="不按行业剔除表过滤",
    )
    ap.add_argument(
        "--extra-exclude-keywords",
        default="",
        help="额外剔除：公司名子串，逗号分隔",
    )
    ap.add_argument(
        "--date-usa",
        action="store_true",
        help="start_date 按月/日/年解析；默认日/月/年（适合 1223 导出）",
    )
    args = ap.parse_args()
    date_dayfirst = not args.date_usa

    mod = load_ext02()
    clean_cell = mod.clean_cell

    csv_path = os.path.abspath(args.csv_path)
    if not os.path.isfile(csv_path):
        print(f"文件不存在: {csv_path}", file=sys.stderr)
        sys.exit(1)

    stem = Path(csv_path).stem
    partial_dir = SCRIPT_DIR / "enterprise_parallel_partial"
    partial_dir.mkdir(parents=True, exist_ok=True)

    out_path = Path(args.output) if args.output else partial_dir / f"{stem}_counts.csv"
    stats_path = (
        Path(args.stats_json) if args.stats_json else partial_dir / f"{stem}_stats.json"
    )

    print("加载 02 模块与乡镇区划映射 …", flush=True)
    cmap = mod.load_county_township_map(args.division_csv)
    print(f"  县级单元（省+市+县）数: {len(cmap)}", flush=True)

    print("加载区县码 / 地级码映射 …", flush=True)
    county_map, pref_map = load_county_and_prefecture_maps(args.division_csv, clean_cell)
    print(f"  县级码条目: {len(county_map)}，地级码条目: {len(pref_map)}", flush=True)

    kw = list(mod.DEFAULT_EXCLUDE_NAME_KEYWORDS)
    if args.extra_exclude_keywords:
        kw.extend([x.strip() for x in args.extra_exclude_keywords.split(",") if x.strip()])
    exclude_tuple = tuple(kw)
    use_exclude = not args.no_exclude_name_keywords

    industry_mid: Set[str] = set()
    industry_small: Set[str] = set()
    use_industry_exclude = not args.no_exclude_industry
    if use_industry_exclude and args.industry_exclude_csv:
        iep = Path(args.industry_exclude_csv)
        if iep.is_file():
            industry_mid, industry_small = mod.load_industry_exclude_csv(str(iep))
            print(
                f"行业剔除：中类 {len(industry_mid)} 项，小类 {len(industry_small)} 项（{iep.name}）",
                flush=True,
            )
        else:
            print(f"警告：未找到行业剔除表 {iep}，跳过行业剔除", flush=True)
            use_industry_exclude = False

    stats: Dict[str, Any] = {
        "rows_total": 0,
        "skip_no_year": 0,
        "skip_year_range": 0,
        "skip_name_keyword": 0,
    }
    counts: Counter = Counter()

    print(f"处理: {csv_path}", flush=True)
    try:
        process_csv(
            csv_path,
            cmap,
            county_map,
            pref_map,
            mod,
            args.year_min,
            args.year_max,
            date_dayfirst,
            exclude_tuple,
            use_exclude,
            industry_mid,
            industry_small,
            use_industry_exclude,
            stats,
            counts,
            args.chunksize,
            args.encoding,
            args.max_rows,
        )
    except ValueError as e:
        print(f"读取失败（缺列或格式错误）: {e}", file=sys.stderr)
        sys.exit(1)

    rows_out = [
        {"年份": y, "code": c, "n": counts[(y, c)]} for (y, c) in sorted(counts.keys())
    ]
    out_df = pd.DataFrame(rows_out)
    if not out_df.empty:
        out_df["code"] = out_df["code"].astype(str).str.replace(r"\.0$", "", regex=True)
        out_df = out_df.sort_values(["年份", "code"]).reset_index(drop=True)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"已写入: {out_path}（{len(out_df)} 行）", flush=True)

    stats["files_processed"] = 1
    stats["csv_path"] = csv_path
    stats["county_keys_in_map"] = len(cmap)
    stats["county_code_map_size"] = len(county_map)
    stats["prefecture_code_map_size"] = len(pref_map)
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"统计已写入: {stats_path}", flush=True)


if __name__ == "__main__":
    main()
