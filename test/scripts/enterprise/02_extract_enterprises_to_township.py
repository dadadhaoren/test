# -*- coding: utf-8 -*-
"""
工商企业 xlsx → 乡镇级匹配与按年汇总（提取脚本）。

匹配逻辑（与约定一致）：
1. 所属省份 / 所属城市 / 所属区县 与 `township_county_division_2023.csv` 的
   区县_省级、区县_地级、区县_县级 **字符串相等**（strip 后）。
2. 三者均匹配到同一县后，在 **注册地址** 中按 **乡镇 Name 长度降序** 做子串包含，
   命中第一个则归入该乡镇 `code`。
3. **成立日期** 解析年份；原数据县错、地址对的情况 **不纠错**，区县无法锁定的行跳过。
4. 区县字段为 `-`、空、无效占位视为缺失，跳过。

默认输出：按 **年份 × 乡镇 code** 的注册主体计数 CSV（utf-8-sig）。

剔除「公共产品属性」市场主体（在乡镇匹配 **之前**）：
1. **国标行业**：见 `test/exclude_public_service_industry_gb2017.csv`（依据 GB/T 4754-2017 扁平化表
   的 **中类** MID_CLASS_NAME，及表中中类缺失时的 **小类**），含医院/基层医疗/公卫/医药批零、
   各级教育、学前教育与托儿所服务等。
2. **公司名称关键词**（可选）：`--no-exclude-name-keywords` 可关。

用法：
  python 02_extract_enterprises_to_township.py --max-files 2
  python 02_extract_enterprises_to_township.py --provinces 上海,北京
  python 02_extract_enterprises_to_township.py --year-min 2012 --year-max 2021

全国按省并行（合并各省输出）见：`03_run_extract_enterprises_parallel.py`。
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd


def load_industry_exclude_csv(path: str) -> Tuple[Set[str], Set[str]]:
    """返回 (国标行业中类 剔除集合, 国标行业小类 剔除集合)。CSV 列：level∈{mid,small}, name"""
    df = pd.read_csv(path, encoding="utf-8-sig")
    if "level" not in df.columns or "name" not in df.columns:
        raise ValueError("行业剔除表需含列: level, name")
    mids: Set[str] = set()
    smalls: Set[str] = set()
    for _, r in df.iterrows():
        lv = clean_cell(r["level"]).lower()
        nm = clean_cell(r["name"])
        if not nm:
            continue
        if lv == "mid":
            mids.add(nm)
        elif lv == "small":
            smalls.add(nm)
    return mids, smalls


def should_exclude_by_industry(
    mid: str,
    small: str,
    mids: Set[str],
    smalls: Set[str],
) -> bool:
    if mid and mid in mids:
        return True
    if small and small in smalls:
        return True
    return False

# 区县三元组 -> [(乡镇code, Name), ...]，Name 已按长度降序
CountyKey = Tuple[str, str, str]
TownshipList = List[Tuple[str, str]]

REQUIRED_COLS = ["所属省份", "所属城市", "所属区县", "注册地址", "成立日期"]

# 默认剔除：名称中含以下子串则不计入（可关）
DEFAULT_EXCLUDE_NAME_KEYWORDS = (
    "医院",
    "卫生院",
    "诊所",
    "卫生室",
    "疾病预防",
    "疾控中心",
    "妇幼保健",
    "小学",
    "中学",
    "幼儿园",
    "学校",
    "大学",
    "学院",
)


def clean_cell(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and pd.isna(v):
        return ""
    s = str(v).strip()
    if s.lower() in ("nan", "none", "<na>"):
        return ""
    return s


def is_invalid_county(s: str) -> bool:
    if not s:
        return True
    if s in ("-", "—", "--", "无", "暂无", "未知"):
        return True
    return False


def parse_found_year(v: Any) -> Optional[int]:
    """成立日期 → 年份。"""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, datetime):
        return int(v.year)
    if hasattr(v, "year") and not isinstance(v, str):
        try:
            return int(v.year)  # pandas Timestamp
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
        dt = pd.to_datetime(s, errors="coerce")
        if pd.isna(dt):
            return None
        return int(dt.year)
    except Exception:
        return None


def load_county_township_map(division_csv: str) -> Dict[CountyKey, TownshipList]:
    df = pd.read_csv(division_csv, encoding="utf-8-sig", dtype=str)
    need = ["code", "Name", "区县_省级", "区县_地级", "区县_县级"]
    for c in need:
        if c not in df.columns:
            raise ValueError(f"区划表缺少列: {c}，当前: {list(df.columns)}")

    groups: Dict[CountyKey, List[Tuple[str, str]]] = defaultdict(list)
    for _, row in df.iterrows():
        p = clean_cell(row["区县_省级"])
        c = clean_cell(row["区县_地级"])
        co = clean_cell(row["区县_县级"])
        if not p or not c or not co:
            continue
        code = clean_cell(row["code"]).replace(".0", "")
        if not code.isdigit():
            continue
        name = clean_cell(row["Name"])
        if not name:
            continue
        groups[(p, c, co)].append((code, name))

    out: Dict[CountyKey, TownshipList] = {}
    for k, pairs in groups.items():
        # 同一县内：长名优先，避免短名抢先匹配
        pairs = list(dict.fromkeys(pairs))  # 去重保序
        pairs.sort(key=lambda t: (-len(t[1]), t[1]))
        out[k] = pairs

    # 直辖市：区划表中 区县_地级 常为「不统计」，工商侧为「北京市」「上海市」等，补 (省, 省, 县) 别名
    _add_municipality_aliases(out)
    return out


def _add_municipality_aliases(out: Dict[CountyKey, TownshipList]) -> None:
    """区划表地级为「不统计」时（直辖市常见），补键 (省, 省, 县) 以对齐工商「市」字段。"""
    for (p, c, co), towns in list(out.items()):
        if clean_cell(c) != "不统计":
            continue
        alt: CountyKey = (p, p, co)
        if alt not in out:
            out[alt] = towns


def should_exclude_by_name(name: str, keywords: Tuple[str, ...]) -> bool:
    if not name or not keywords:
        return False
    for kw in keywords:
        if kw and kw in name:
            return True
    return False


def match_township_code(
    prov: str,
    city: str,
    county: str,
    address: str,
    cmap: Dict[CountyKey, TownshipList],
) -> Tuple[Optional[str], Optional[str], str]:
    """
    返回 (乡镇code, 乡镇Name, 原因)。
    原因: ok | county_miss | addr_empty | township_miss
    """
    if is_invalid_county(county):
        return None, None, "county_miss"
    addr = address.strip() if address else ""
    if not addr:
        return None, None, "addr_empty"

    key = (prov, city, county)
    towns = cmap.get(key)
    if not towns:
        return None, None, "county_miss"

    for code, tname in towns:
        if tname and tname in addr:
            return code, tname, "ok"
    return None, None, "township_miss"


def iter_enterprise_xlsx(root: str, province_filter: Optional[Set[str]]) -> List[str]:
    """
    枚举待处理 xlsx。

    - **全国根目录**：下一级子文件夹为各省包，再取其中 `*.xlsx`。
    - **单省文件夹**（并行任务传入 `.../全国所有企业工商信息/河北所有企业`）：若该目录下**直接**有
      `*.xlsx`，则只返回这些文件（不再要求子文件夹）。
    """
    root = os.path.abspath(root)
    direct = sorted(glob.glob(os.path.join(root, "*.xlsx")))
    if direct:
        return [p for p in direct if os.path.isfile(p)]

    paths: List[str] = []
    for sub in sorted(os.listdir(root)):
        d = os.path.join(root, sub)
        if not os.path.isdir(d):
            continue
        if province_filter:
            if not any(p in sub for p in province_filter):
                continue
        for fp in glob.glob(os.path.join(d, "*.xlsx")):
            if os.path.isfile(fp):
                paths.append(fp)
    return sorted(paths)


def process_dataframe(
    df: pd.DataFrame,
    cmap: Dict[CountyKey, TownshipList],
    year_min: Optional[int],
    year_max: Optional[int],
    exclude_keywords: Tuple[str, ...],
    use_name_exclude: bool,
    industry_mid: Set[str],
    industry_small: Set[str],
    use_industry_exclude: bool,
    stats: Dict[str, int],
    counts: Counter,
) -> None:
    """原地累计 stats 与 counts[(year, code)]。"""
    for col in REQUIRED_COLS:
        if col not in df.columns:
            raise ValueError(f"企业表缺少列: {col}")

    name_col = "公司名称" if "公司名称" in df.columns else None
    has_mid = "国标行业中类" in df.columns
    has_small = "国标行业小类" in df.columns
    if use_industry_exclude and industry_mid | industry_small:
        if not has_mid and not has_small:
            stats["industry_cols_missing"] = stats.get("industry_cols_missing", 0) + 1

    for _, row in df.iterrows():
        stats["rows_total"] += 1

        prov = clean_cell(row["所属省份"])
        city = clean_cell(row["所属城市"])
        co = clean_cell(row["所属区县"])
        addr = clean_cell(row["注册地址"])
        year = parse_found_year(row["成立日期"])

        if year is None:
            stats["skip_no_year"] += 1
            continue
        if year_min is not None and year < year_min:
            stats["skip_year_range"] += 1
            continue
        if year_max is not None and year > year_max:
            stats["skip_year_range"] += 1
            continue

        if use_industry_exclude and (industry_mid or industry_small):
            mid_val = clean_cell(row["国标行业中类"]) if has_mid else ""
            small_val = clean_cell(row["国标行业小类"]) if has_small else ""
            if should_exclude_by_industry(mid_val, small_val, industry_mid, industry_small):
                stats["skip_industry"] = stats.get("skip_industry", 0) + 1
                continue

        if use_name_exclude and name_col:
            nm = clean_cell(row[name_col])
            if should_exclude_by_name(nm, exclude_keywords):
                stats["skip_name_keyword"] += 1
                continue

        code, _tname, reason = match_township_code(prov, city, co, addr, cmap)
        stats[f"match_{reason}"] = stats.get(f"match_{reason}", 0) + 1

        if reason != "ok" or code is None:
            continue
        counts[(year, code)] += 1


def main() -> None:
    test_dir = Path(__file__).resolve().parent.parent.parent
    default_division = test_dir / "township_county_division_2023.csv"
    default_root = r"F:\BaiduNetdiskDownload\全国所有企业工商信息"
    default_out = test_dir / "township_enterprise_counts_by_year.csv"
    default_stats = test_dir / "township_enterprise_extract_stats.json"
    default_industry_exclude = test_dir / "exclude_public_service_industry_gb2017.csv"

    ap = argparse.ArgumentParser(description="工商企业按乡镇、成立年份汇总")
    ap.add_argument(
        "--division-csv",
        default=str(default_division),
        help="乡镇区划 CSV（含区县_省/地/县与乡镇 code、Name）",
    )
    ap.add_argument(
        "--enterprise-root",
        default=default_root,
        help="全国根目录（省下分子文件夹）或单省文件夹（其下直接为 xlsx，供并行任务使用）",
    )
    ap.add_argument("-o", "--output", default=str(default_out), help="输出：年份×乡镇 code 计数 CSV")
    ap.add_argument(
        "--stats-json",
        default=str(default_stats),
        help="运行统计 JSON（匹配失败原因计数等）",
    )
    ap.add_argument(
        "--provinces",
        default=None,
        help="只处理文件夹名包含所列子串的省，逗号分隔，如 上海,浙江",
    )
    ap.add_argument("--year-min", type=int, default=None, help="成立年份下限（含）")
    ap.add_argument("--year-max", type=int, default=None, help="成立年份上限（含）")
    ap.add_argument(
        "--max-files",
        type=int,
        default=None,
        help="最多处理 xlsx 文件数（调试用）",
    )
    ap.add_argument(
        "--no-exclude-name-keywords",
        action="store_true",
        help="不按公司名称默认关键词剔除医院/学校等",
    )
    ap.add_argument(
        "--industry-exclude-csv",
        default=str(default_industry_exclude),
        help="GB/T 行业中类/小类剔除表（level=mid|small, name=名称）；空路径表示不读文件",
    )
    ap.add_argument(
        "--no-exclude-industry",
        action="store_true",
        help="不按国标行业中类/小类剔除公共产品相关行业",
    )
    ap.add_argument(
        "--extra-exclude-keywords",
        default="",
        help="额外剔除：公司名称包含的子串，逗号分隔",
    )
    args = ap.parse_args()

    province_filter: Optional[Set[str]] = None
    if args.provinces:
        province_filter = {p.strip() for p in args.provinces.split(",") if p.strip()}

    print("加载乡镇区划映射 …", flush=True)
    cmap = load_county_township_map(args.division_csv)
    print(f"  县级单元（省+市+县）数: {len(cmap)}", flush=True)

    files = iter_enterprise_xlsx(args.enterprise_root, province_filter)
    if args.max_files is not None:
        files = files[: args.max_files]
    print(f"待处理 xlsx 文件数: {len(files)}", flush=True)
    if not files:
        print("未找到任何 xlsx，请检查 --enterprise-root 与 --provinces", file=sys.stderr)
        sys.exit(1)

    kw = list(DEFAULT_EXCLUDE_NAME_KEYWORDS)
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
            industry_mid, industry_small = load_industry_exclude_csv(str(iep))
            print(
                f"行业剔除：中类 {len(industry_mid)} 项，小类 {len(industry_small)} 项（{iep.name}）",
                flush=True,
            )
        else:
            print(f"警告：未找到行业剔除表 {iep}，跳过行业剔除", flush=True)
            use_industry_exclude = False

    stats: Dict[str, int] = {
        "rows_total": 0,
        "skip_no_year": 0,
        "skip_year_range": 0,
        "skip_name_keyword": 0,
    }
    counts: Counter = Counter()

    for i, fp in enumerate(files):
        print(f"[{i+1}/{len(files)}] {fp}", flush=True)
        try:
            df = pd.read_excel(fp, engine="openpyxl", dtype=object)
        except Exception as e:
            print(f"  跳过（读取失败）: {e}", flush=True)
            stats["files_read_error"] = stats.get("files_read_error", 0) + 1
            continue
        missing_cols = [c for c in REQUIRED_COLS if c not in df.columns]
        if missing_cols:
            print(
                f"  跳过（非企业表或缺列 {missing_cols}）: {os.path.basename(fp)}",
                flush=True,
            )
            stats["files_skip_missing_columns"] = (
                stats.get("files_skip_missing_columns", 0) + 1
            )
            continue
        process_dataframe(
            df,
            cmap,
            args.year_min,
            args.year_max,
            exclude_tuple,
            use_exclude,
            industry_mid,
            industry_small,
            use_industry_exclude,
            stats,
            counts,
        )

    # 长表：年份, code, n
    rows = [{"年份": y, "code": c, "n": counts[(y, c)]} for (y, c) in sorted(counts.keys())]
    out_df = pd.DataFrame(rows)
    if not out_df.empty:
        out_df["code"] = out_df["code"].astype(str).str.replace(r"\.0$", "", regex=True)
        out_df = out_df.sort_values(["年份", "code"]).reset_index(drop=True)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"已写入: {out_path}（{len(out_df)} 行）", flush=True)

    stats["files_processed"] = len(files)
    stats["county_keys_in_map"] = len(cmap)
    stats_path = Path(args.stats_json)
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"统计已写入: {stats_path}", flush=True)


if __name__ == "__main__":
    main()
