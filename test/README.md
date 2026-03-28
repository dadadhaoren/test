# 复现工作区：乡村创业与基层公共产品供给

本目录为后续分析的主工作空间，目标是对照论文复现**核心被解释变量**与**核心解释变量**的构造口径，并与本地数据对齐。

### 复现范围：POI 数据年份

- **纳入复现**：**2012–2021 年**地级市 POI（`poi_extracted\2012` … `poi_extracted\2021`）。
- **暂不纳入**：**2022、2023** 年 POI 数据可保留在网盘作备查，**不作为本复现必须数据**；后续建库、清洗与论文对齐分析时可**不处理**这两年。

## 论文与数据路径

| 项目 | 路径 |
|------|------|
| 原文 PDF | `F:\BaiduNetdiskDownload\惠泽乡里：乡村创业活动提升基层公共产品供.pdf` |
| 数据根目录 | `F:\BaiduNetdiskDownload` |
| 地级市 POI 主目录 | `F:\BaiduNetdiskDownload\地级市POI兴趣点` |
| **解压后的 POI 数据（新建）** | `F:\BaiduNetdiskDownload\地级市POI兴趣点\poi_extracted` |

将 **rar / 分卷 7z** 等解压出的 csv、shp、xlsx 等，建议按年份建子目录放入上表最后一格，例如 `...\poi_extracted\2015\`，便于与脚本 `02_parse_prefecture_poi.py` 后续衔接。

### 脚本目录（归档）

脚本已按主题归入 **`scripts/enterprise/`**（工商与区划）与 **`scripts/poi/`**（POI 与乡镇面板），索引与运行说明见 **[scripts/README.md](./scripts/README.md)**。

**1223 分片 CSV（网盘「1223工商企业信息」）** 另有一套独立脚本，放在 **`anther_data_enterprise/`**（与全国工商 xlsx 流水线并行，默认成立年 2000–2022）：统计行数、按 `part_*.csv` 提取与并行合并、并入县级以上区划地名。说明与口径见 **[anther_data_enterprise/README.md](./anther_data_enterprise/README.md)**（含与 xlsx 在**国民行业分类字段**、**公司名剔除词表**上的差异）。

### POI 压缩包按年解压（脚本）

使用 **[scripts/poi/01_extract_poi_to_folder.py](./scripts/poi/01_extract_poi_to_folder.py)**，将各 `YYYYPOI` 下的压缩包解压到 `poi_extracted\YYYY\`（2020 为「一市一子文件夹」，2023 为「一省一子文件夹」）。

```text
python test/scripts/poi/01_extract_poi_to_folder.py
python test/scripts/poi/01_extract_poi_to_folder.py --years 2015,2016,2017
```

- 解压记录与合并结果见：`poi_extracted\extract_manifest.json`（多次运行会**按年份合并**，不覆盖已成功年份）。
- **ZIP**（2013、2020、2023）仅用 Python 标准库即可，已在本机跑通。
- **分卷 7z**（2015–2017）与 **RAR**（2012、2014、2018–2019、2021–2022）：可安装 **7-Zip** 并设置 **`SEVEN_ZIP`** 指向 `7z.exe`；或安装 **WinRAR**，脚本会自动使用同目录下的 **`UnRAR.exe`** 解压 RAR（优先），用 **`WinRAR.exe`** 作为 **7z** 的备选（也可显式传入 `--winrar "C:\Program Files\WinRAR\WinRAR.exe"` 或环境变量 **`WINRAR`**）。

## POI 解压目录说明（去重记录）

- **2016**：原始 7z 在 `poi_extracted\2016\2016\` 内曾出现**同一套 shapefile 两套路径**（根目录与 `2016\` 子目录各一份，内容一致），属**数据包内重复**，非脚本误解压两遍。其余年份核对后**无**此类「实质重复」；2020、2023 等同名文件多为**各市/各省各一份**，属正常结构。
- **处理**：已在本机**手动删除**其中一套重复，后续分析只保留一套即可。

### POI 入库（DuckDB）筹备

- **各年份字段与结构概要**（抽样）：见 **[poi_extracted_duckdb_prep.md](./poi_extracted_duckdb_prep.md)**。  
- **可参考**项目内 `gbif_scripts/01_data_import/`：`build_duckdb_from_csv.py`（CSV 批量入库）、`import_shapefile_to_duckdb.py`（shapefile → DuckDB / WKT）。

## 本目录配套文件

| 文件 | 说明 |
|------|------|
| [poi_extracted_duckdb_prep.md](./poi_extracted_duckdb_prep.md) | `poi_extracted` 各年载体类型、字段样例与 DuckDB 建库衔接说明。 |
| [poi_field_structure_by_year.md](./poi_field_structure_by_year.md) | **各年份 POI 字段结构说明**（总览表 + 分年字段字典）；静态文档，原辅助脚本已清理。 |
| [poi_field_structure_samples.xlsx](./poi_field_structure_samples.xlsx) | 各格式**几行样例数据**（多工作表）；历史生成物，保留作对照。 |
| [公共产品供给分类标准.csv](./公共产品供给分类标准.csv) | 参照《“十四五”公共服务规划》，将 POI **小类**归入「基本公共服务」「普惠性非基本公共服务」「生活服务」三大类，用于筛选具有公共产品属性的设施。 |
| [核心变量处理方式.txt](./核心变量处理方式.txt) | 论文对两个核心变量的文字说明（与下节一致，便于单独查阅）。 |
| [scripts/README.md](./scripts/README.md) | **Python 脚本归档索引**（`enterprise/`、`poi/` 子目录与示例命令）。 |

#### 工商与区划（`scripts/enterprise/`）

文件名前缀 **01–07** 表示推荐执行顺序；**06–07** 为独立统计工具。

| 脚本 | 说明 |
|------|------|
| `01_build_township_county_division_table.py` | 区县+乡镇矢量 → 区划属性表 CSV |
| `02_extract_enterprises_to_township.py` | 工商 xlsx → 乡镇匹配、按年×乡镇计数 CSV |
| `03_run_extract_enterprises_parallel.py` | 按省并行调用 02 并合并全国结果 |
| `04_merge_division_to_enterprise_counts.py` | 企业计数表并入区县区划字段 |
| `05_balance_township_enterprise_panel.py` | 稀疏企业计数 → 平衡面板 |
| `06_count_enterprise_registrations_total.py` | 全国工商 xlsx 行数统计（快速） |
| `07_stats_enterprise_found_year_range.py` | 成立/注册日期年份范围（min/max） |

#### POI 与面板（`scripts/poi/`）

文件名前缀 **01–06** 表示推荐流程顺序（解压 → 解析 → 各年宽表 → 并入区县属性）。

| 脚本 | 说明 |
|------|------|
| `01_extract_poi_to_folder.py` | 地级市 POI 压缩包 → `poi_extracted\年份\` |
| `02_parse_prefecture_poi.py` | 按年解析 POI → Parquet 等 |
| `03_township_poi_panel_wide.py` | 2012–2017 乡镇 POI 宽表（平衡面板） |
| `04_township_poi_panel_wide_cat_or_subtype.py` | 同上，CATEGORY 或 SUBTYPE 匹配 |
| `05_township_poi_panel_wide_2018_2021_contains_last_segment.py` | 2018–2021 乡镇 POI 宽表（末段匹配版） |
| `06_merge_county_attrs_to_township_panel.py` | 县域属性并入乡镇 POI 面板 |

---

## 1. 被解释变量：基层公共产品供给

### 论文定义与思路

- **空间单元**：乡镇层面。
- **数据**：多源地理 **POI**，用空间颗粒度刻画公共产品供给状况（替代问卷/年鉴中农业、教育、医疗等设施指标，以缓解农村数据不全、难反映乡镇差异等问题）。
- **概念口径**：因地理数据通常只有名称、类别与坐标，难以识别产权与出资，故**不从严格产权意义**界定公共产品，而以「能够在乡村地理边界内以**实物形态呈现**的建筑或设施」表征基层公共产品供给。
- **分类框架**：参照《“十四五”公共服务规划》分为三大类，从 POI 小类中抽取具公共产品属性的设施，再按分类标准统计各类 POI 数量。具体小类与一级类别对应关系见本目录 **`公共产品供给分类标准.csv`**（列：`一级类别`，`小类`）。

### 处理流程（与论文一致）

1. 使用 **Python Geopandas** 读取 POI，检查结构与**坐标系一致**。
2. 按 POI 自带分类，对照**公共产品分类标准**，保留符合公共产品供给的 POI，其余剔除。
3. 将 POI **经纬度**投射到中国**镇级矢量地图**，识别所属乡镇。
4. 剔除**街道、中心镇、城关镇**等，减轻县域核心区过高供给对农村样本的干扰。
5. 按 **年份—乡镇** 汇总，得到各镇各年基层公共产品供给水平。

### 回归中的变量形式（表 2）

| 项目 | 内容 |
|------|------|
| 变量含义 | 乡镇带有公共产品性质的 **POI 数量（个）** |
| 回归变换 | **取对数** |

---

## 2. 核心解释变量：乡村创业活动

### 论文定义与思路

- **代理变量**：乡镇层面**新注册企业数量**，衡量乡村创业活跃程度；数据来自**工商注册数据库**（论文处理约 2.48 亿条，按地级市加载）。
- **清洗工具**：**Python Pandas**。剔除企业名称、注册时间、注册地址、经营范围、行业分类等**关键信息缺失**样本。

### 空间匹配（与 POI 的差异）

- 工商数据中**经纬度缺失较多**，无法像 POI 一样主要靠坐标匹配。
- 使用**正则表达式**从**注册地址文本**中抽取企业所属**乡镇**。
- 按 **乡镇—注册年份** 汇总**新注册企业数**。
- 再与公共产品 POI 汇总结果按 **年份—乡镇** 合并，形成**镇级面板**。

### 回归中的变量形式（表 2）

| 项目 | 内容 |
|------|------|
| 变量含义 | 乡镇**当年新注册企业数量（家）** |
| 回归变换 | **取对数** |

### 测量偏差与额外清洗

- **注册地 ≠ 经营地**：可能带来内生性；论文采用**乡镇层面汇总**而非更小尺度，以减轻偏差。
- **避免与因变量概念混杂**：按**企业名称**与**所属行业**，剔除本身具公共产品属性的主体（如医院、诊所、药店、学校等），使变量更贴近「乡村创业活动」本身。

---

## 复现检查表（本地数据待填）

在 `F:\BaiduNetdiskDownload` 中打开实际使用的表后，将下列「本地对应」补全。

### 被解释变量

| 论文表述 | 本地数据对应（路径 / 主要字段） |
|----------|----------------------------------|
| 多源 POI | （待填：文件名、坐标字段、类别字段、年份字段） |
| 镇界 shapefile | （待填：路径、乡镇代码字段） |
| 剔除街道/中心镇/城关镇所用名单或属性 | （待填） |

### 核心解释变量

| 论文表述 | 本地数据对应（路径 / 主要字段） |
|----------|----------------------------------|
| 工商注册数据 | （待填：注册时间、地址、名称、行业等字段） |
| 乡镇汇总键 | （待填：与 POI 侧一致的乡镇代码与年份） |

### 主要控制变量（若论文列出）

| 变量 | 含义与口径 | 本地对应 |
|------|------------|----------|
| （待填） | | |

## 建议工作流

1. 用 **`公共产品供给分类标准.csv`** 核对 POI 小类是否全覆盖、是否与论文附录一致。
2. POI 与企业数据分别清洗到 **年份—乡镇** 面板，再合并；回归前对两个核心变量按论文取 **对数**。
3. 脚本已归档至 **`scripts/enterprise/`** 与 **`scripts/poi/`**，输出仍默认写在 **`test/`** 下；若使用 **1223 分片 CSV**，见 **`anther_data_enterprise/`** 及该目录下 README。记录所用数据版本与字段映射。

## 变更记录

- 初始化 README，约定论文路径与数据根目录。
- 纳入 **`核心变量处理方式.txt`** 与 **`公共产品供给分类标准.csv`** 对应的变量定义与处理流程说明。
- 脚本按主题归档到 **`scripts/enterprise/`**、**`scripts/poi/`**，并补充 **`scripts/README.md`** 索引。
- 补充 **`anther_data_enterprise/`**（1223 分片 CSV）说明与索引表，与全国工商 xlsx 流水线对照。
