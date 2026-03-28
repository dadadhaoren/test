# 1223 工商企业信息（分片 CSV）— 统计记录与后续脚本规划

本目录用于处理 **`1223工商企业信息（1989-2022）`** 这一套**分片 CSV** 工商数据，目标与 `test/scripts/enterprise/` 中 **`02_extract_enterprises_to_township.py` + `03_run_extract_enterprises_parallel.py`** 一致：构造**乡镇面板用的「按注册年份 × 乡镇 code」企业主体计数**。  

与网盘 **`全国所有企业工商信息`（各省子目录 + xlsx）** 的流程**并行独立**。  
此前 xlsx 流水线在试跑、按省分片时，默认将各省的 **`*_counts.csv` / `*_stats.json`** 写入仓库已忽略的 **`test/enterprise_parallel_partial/`**（由 `03_run_extract_enterprises_parallel.py` 的 `--partial-dir` 指定）。本套分片 CSV 的**处理口径与之一致**（见 §3.2），仅将「按省分片」改为「按 `part_*.csv` 分片」；输出目录可设为例如 **`anther_data_enterprise/enterprise_parallel_partial/`**（或本目录下其他 `output_partial`，避免与 xlsx 产物混放）。

---

## 1. 数据位置与结构

| 项目 | 说明 |
|------|------|
| 默认根目录 | `F:\BaiduNetdiskDownload\1223工商企业信息（1989-2022）` |
| 实际 CSV 目录 | 根目录下**唯一子目录**（名称多为「工商注册信息」类），内含 `part_000.csv` … `part_020.csv` |
| 分片数量 | **21** 个文件 |
| 体量（本机曾测） | 合计约 **107 GB** |
| 编码 | 表头可用 **`utf-8-sig`** 读取；正文中文列若异常可再试 `gb18030` |
| 列名体系 | **英文**（与全国 xlsx 中文列不同，需字段映射后再做区县/乡镇匹配） |

**主要字段（与乡镇提取相关）**

- `start_date`：成立/起始日期 → 解析**注册年份**（对标 xlsx 的「成立日期」）
- `district` / `district_code`：行政区划文字 / 代码 → 对标「所属省/市/县」与区县锁定（具体映射规则在实现脚本中定稿）
- `reg_addr`：注册地址 → 对标「注册地址」，用于**乡镇名称子串匹配**
- `industry`：见下节 **§1.1**（与 xlsx 中国标行业列**不是**同一套字段）

### 1.1 无《国民经济行业分类》拆列（与全国工商 xlsx 的重要差异）

**1223 分片 CSV（如 `part_020.csv`）中：**

- **没有**与全国企业工商 xlsx 中常见的 **`国标行业中类`、`国标行业小类`**（或门类/大类/中类/小类编码）等 **GB/T 4754 结构化字段**。
- 仅有 **`industry`** 一列：多为简短行业描述（如「餐饮业」），大量为 **`-` 或空**。

**对「公共产品属性」行业剔除的影响**（`02_extract_enterprises_csv_to_township.py`）：

- 仍默认读取 **`exclude_public_service_industry_gb2017.csv`**（与 xlsx 版 `02` 同一张表），但对 **`industry` 文本做子串包含判断**；xlsx 版是对国标中类/小类列做**整字段精确相等**。
- 二者**不等价**：短 `industry` 往往无法包含剔除表中的完整中类/小类名称，全量统计中 **`skip_industry` 可能接近 0**，不等于未做剔除逻辑。
- **公司名称关键词剔除**（医院、学校等）与 xlsx 一致，不受影响。

若需与论文或 xlsx 流水线**严格对齐**国标行业剔除，需另行引入带 **国标行业代码或中类/小类名称** 的数据源，或自建 **`industry` / `scope` → 国标类别** 映射表后再过滤。

---

## 2. 全库记录条数统计（换行计数法）

**脚本**：`01_count_part_csv_records.py`  

**口径**：每个分片**首行为表头**，**数据行数 = 文件内换行数 − 1**（与 `scripts/enterprise/06_count_enterprise_registrations_total.py` 对 xlsx 的「数据行」口径一致）。  
**实现**：按二进制块统计 `\n`，不解析 CSV；若极少数字段内含未转义换行，条数可能略高估。

| 指标 | 数值 |
|------|------|
| 分片文件数 | 21（`part_000.csv` … `part_020.csv`） |
| **合计企业注册记录条数** | **179,053,067** |
| 换行合计（含各分片表头行） | 179,053,088 |
| 本机一次全量扫描耗时（参考） | 约 25～26 分钟（顺序读盘，视磁盘而定） |

**运行示例**：

```text
python test/anther_data_enterprise/01_count_part_csv_records.py
python test/anther_data_enterprise/01_count_part_csv_records.py --verbose
```

---

## 3. 后续脚本目标（对齐 enterprise 流水线，但年份与数据源不同）

### 3.1 与现有脚本的对应关系

| 现有（xlsx 流水线） | 本套（分片 CSV）预期 |
|---------------------|----------------------|
| `01_build_township_county_division_table.py` | **复用**同一套区县—乡镇区划表（如 `township_county_division_2023.csv`） |
| `02_extract_enterprises_to_township.py` | **新写**：读 `part_*.csv`，字段映射 + 同一套「区县三元组锁定 + 注册地址乡镇子串」逻辑 |
| `03_run_extract_enterprises_parallel.py` | **新写**：按 **`part_*.csv` 分片**（或省域子集若后处理拆分）并行子进程，再 **merge** 为全国的 `年份 × code × n` |
| `04_merge_division_to_enterprise_counts.py` | **本套对应**：`04_merge_division_to_enterprise_counts_csv.py` — 将合并后的 `年份×code×n` 并入区划表，得到 **县级以上地名**（`区县_省级`、`区县_地级`、`区县_县级` 等）及乡镇名 `Name` |
| `enterprise_parallel_partial/`（xlsx 试跑默认） | 本套建议 **`anther_data_enterprise/enterprise_parallel_partial/`**（或等价路径）：每分片 `part_XXX_counts.csv` / `part_XXX_stats.json`，再合并为全国表 |

### 3.2 注册年份 + 与 `enterprise_parallel_partial` 一致的其它要求

**注册年份（唯一与旧 xlsx 全量跑可能不同的显式条件）**

- **`--year-min 2000`（含 2000 年）**；**`--year-max`** 与数据一致（如 **2022**）或由参数指定。
- 即：剔除 **1999 年及以前**的注册记录；**2000-01-01 及当年成立**均计入。

**其余与此前 `enterprise_parallel_partial` / `02` + `03` 试跑相同**（实现 CSV 版时应对齐下列默认行为）：

| 项目 | 与 `02_extract_enterprises_to_township.py` / `03_run_extract_enterprises_parallel.py` 一致 |
|------|---------------------------------------------------------------------------------------------|
| 区划表 | `test/township_county_division_2023.csv`（`--division-csv`） |
| 行业剔除 | `test/exclude_public_service_industry_gb2017.csv`（`--industry-exclude-csv`）；可用 `--no-exclude-industry` 关闭 |
| 公司名称关键词剔除 | 与 02 默认列表一致（医院/学校等）；可用 `--no-exclude-name-keywords` 关闭 |
| 额外关键词 | `--extra-exclude-keywords` 逗号分隔 |
| 匹配逻辑 | 省/市/县三元组与区划表 **字符串相等**（strip 后）锁定区县 → **注册地址** 按乡镇 **Name 长度降序** 子串命中；直辖市 **(省, 省, 县)** 别名与 02 相同 |
| 分片产物 | 与 03 类似：每任务输出 **`{任务名}_counts.csv`**、**`{任务名}_stats.json`**，再合并为全国的 **`年份, code, n`** 与汇总 `stats` |
| 合并后主表 | 与 02 默认一致，便于接 **`04_merge_division_to_enterprise_counts.py`**、**`05_balance_township_enterprise_panel.py`**（列名、编码 `utf-8-sig`） |

**1223 CSV 特有**：字段为英文，需在脚本内映射到上述逻辑（如 `start_date`→成立年、`reg_addr`→注册地址；区县锁定以 **`district_code`** 为主，见 §1）。**行业剔除与国标字段的关系见 §1.1**。

### 3.3 建议输出（与 02 一致，便于接 04/05）

- 主表列：**`年份`, `乡镇 code`, `n`**（或沿用现有命名 `年份`, `code`, `n`），编码 **`utf-8-sig`**。
- **并入县级以上区划地名**：在合并全国计数表后运行 **`04_merge_division_to_enterprise_counts_csv.py`**，按 `code` 左连接 `township_county_division_2023.csv`，追加 **`区县_省级`、`区县_地级`、`区县_县级`**（及区划码、类型等）与 **`Name`（乡镇/街道名）**，输出例如 `township_enterprise_counts_by_year_csv_2000_2022_with_division.csv`（与 `scripts/enterprise/04_merge_division_to_enterprise_counts.py` 口径一致）。
- 可选：按分片输出再 `groupby` 合并，避免单次载入百 GB。

### 3.4 脚本用法（已实现）

```text
python test/anther_data_enterprise/02_extract_enterprises_csv_to_township.py --csv-path "F:\...\part_000.csv"
python test/anther_data_enterprise/02_extract_enterprises_csv_to_township.py --csv-path ... --max-rows 5000
python test/anther_data_enterprise/03_run_extract_csv_parallel.py --dry-run
python test/anther_data_enterprise/03_run_extract_csv_parallel.py --workers 4
python test/anther_data_enterprise/04_merge_division_to_enterprise_counts_csv.py
```

- **`start_date`**：默认按**日/月/年**解析（`dayfirst`）；若需美式月/日/年，对 02 传 `--date-usa`，对 03 同样传 `--date-usa`。  
- **后处理**：`04_merge_division_to_enterprise_counts_csv.py` 并入区划名后，可与 `05_balance_township_enterprise_panel.py` 等衔接（列名与 xlsx 流水线 `04` 产出一致）；平衡面板年份需与 POI（如 2012–2021）再对齐。

---

## 4. 文件索引（本目录）

| 文件 | 说明 |
|------|------|
| `01_count_part_csv_records.py` | 全库分片行数/记录数快速统计 |
| `02_extract_enterprises_csv_to_township.py` | 单分片 CSV → `年份×code×n`（依赖 `district_code`+区划表；默认成立年 2000–2022） |
| `03_run_extract_csv_parallel.py` | 并行跑全部分片并合并；输出默认 `township_enterprise_counts_by_year_csv_2000_2022.csv` |
| `04_merge_division_to_enterprise_counts_csv.py` | 计数表并入区划：**省/市/县地名**与乡镇 `Name`；默认输出 `*_with_division.csv` |
| `enterprise_parallel_partial/` | 各分片 `part_XXX_counts.csv` / `*_stats.json`（运行时生成） |
| `README.md` | 本文：统计结果与后续脚本约定 |
