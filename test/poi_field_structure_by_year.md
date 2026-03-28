# 地级市 POI（`poi_extracted`）各年份内容字段结构说明

**数据根目录**：`F:\BaiduNetdiskDownload\地级市POI兴趣点\poi_extracted`  

**生成方式**：原为脚本扫描 + 手工整理；**辅助脚本已移除**，本文与 `poi_field_structure_scan.json` / `poi_field_structure_samples.xlsx` 以仓库内版本为准，数据路径变更时请自行核对。

**样例 Excel（各格式几行真实数据）**：`test/poi_field_structure_samples.xlsx`（多工作表：SHP_2012_2017、CSV_2018/2020/2021/2022、XLSX_2023、**2019B/C/D** 等）。

**用途**：DuckDB / 分析脚本设计统一表结构、列映射与编码处理时的字段字典。

---

## 总览

| 年份 | 主要载体 | 坐标 / 几何 | 分类与名称字段特点 |
|------|-----------|-------------|-------------------|
| 2012–2017 | 多图层 **Shapefile**（点） | `LON` / `LAT` 或同目录几何，`EPSG:4326` | 英文属性：`TYPECODE`、`BASETYPE`、`SUBTYPE`、`CATEGORY` 等 |
| 2018 | 顶层 **CSV** | **`location`** 字符串解析经纬度 | 乡镇脚本：仅 **`type`** 与「小类」**包含**匹配 |
| 2019 | **本复现 POI 仅用** `zip_extracted\\{100000|…|600000}\\**\\d_*.csv` | **D=纬度、E=经度**（无表头第 4–5 列）；与 Excel 列字母一致 | 乡镇脚本：仅 **G 列（第 7 列，细类）** 与「小类」包含匹配 |
| 2020 | 各地级市子目录 **CSV**，UTF-8 BOM | **`wgs84lon`、`wgs84lat`**（WGS84） | 乡镇脚本：仅 **`小类`** 与标准表「小类」**完全相等**（同 2012–2017） |
| 2021 | 顶层多 **CSV**，中文表头 | **`经纬度`** 字符串解析 | 乡镇脚本：仅 **`类别`** 与「小类」包含匹配 |
| 2022 | 分区目录 **CSV** | `经度`、`纬度` | `大类`、`中类` |
| 2023 | 省级包内 **xlsx** | `location`（字符串，需解析） | `type`、`typecode`；无大中类三列 |

---

## 2012、2013、2014、2015、2016、2017

### 组织方式

- 路径：`poi_extracted\YYYY\YYYY\`
- **多个** `.shp` 分图层（如交通设施服务、住宿服务、事件活动等），**点数图层**，**CRS 抽样为 `EPSG:4326`**。

### 属性字段（各图层一致，抽样验证）

| 字段名 | 含义（概要） |
|--------|----------------|
| `NAME` | 名称 |
| `ADDRESS` | 地址 |
| `TELEPHONE` | 电话 |
| `PROVINCE` / `CITY` / `COUNTY` | 省 / 市 / 县 |
| `CODE` | 内部或类型编码 |
| `LON` / `LAT` | 经纬度（与 geometry 一致时可二选一使用） |
| `TYPECODE` | 类型码 |
| `BASETYPE` | 大类/基础类 |
| `SUBTYPE` | 子类 |
| `CATEGORY` | 类别描述 |
| `geometry` | 点几何 |

### 备注

- 图层数量随年份略有增减（如 2012 抽样约 20 个 shp，2015–2017 约 23 个）。
- 与论文「小类」映射时，优先用 `TYPECODE` / `SUBTYPE` / `CATEGORY` 与 `公共产品供给分类标准.csv` 对照。

---

## 2018

### 组织方式

- 路径：`poi_extracted\2018\`
- **多个 CSV** 在顶层（文件名多为数字时间戳）。

### 字段（抽样文件 `1540880282990.csv`）

| 字段名 | 说明 |
|--------|------|
| `address` | 地址 |
| `adname` | 区县级名称 |
| `page_publish_time` | 时间 |
| `adcode` / `pname` / `cityname` | 区划与上级地名 |
| `name` | POI 名称 |
| `location` | 位置字符串（**需解析**为经纬度） |
| `_id` | 记录 id |
| `type` | 类型 |
| `Unnamed: 10` | 空列/冗余，可丢弃 |

**编码**：抽样可读为 **GB18030**（以实际文件为准，建议探测）。

**乡镇面板**（`05_township_poi_panel_wide_2018_2021_contains_last_segment.py`）：仅用 **`type`** 做「小类」包含匹配；坐标仅用 **`location`**。

---

## 2019

**乡镇面板与 `05_township_poi_panel_wide_2018_2021_contains_last_segment.py` 使用的 POI 仅来自**：

`poi_extracted\2019\2019\zip_extracted\` 下 **`100000`、`200000`、`300000`、`400000`、`500000`、`600000`** 六个子目录内的 `d_*.csv`（可含子路径，如 `100000\d_110000.csv`）。

本机示例：`F:\BaiduNetdiskDownload\地级市POI兴趣点\poi_extracted\2019\2019\zip_extracted\100000` … `600000`。  
**不扫描** `zip_extracted` 下其它目录名；**同目录外**按类 Shapefile 等 **不作为** 本项目 2019 POI。

### A. 分包 POI 表（**唯一用于本统计的 POI**）`zip_extracted\{100000|…|600000}\**\d_*.csv`

- **348** 个 `d_XXXXXX.csv`（地级市代码），**无表头**，**GB18030**。
- **约 8 列**（语义，与 Excel **A–H** 对应）：A 序号、B 名称、C 地址、**D 纬度、E 经度**、F 大类(分号)、**G 细类(分号)**、H 电话。
- 乡镇面板脚本：经纬度取 **D、E**；与「小类」匹配**仅扫 G 列（细类）**。
- **常州** `d_320200` 曾为 **嵌套 zip**，解压后得到同名 **csv**。

### B. 城市清单 `2019\2019\ministreet_map_city.csv`

- **无表头**，**GBK**、**逗号分隔**，约 **4** 列：**列表索引**（非连续 1,2,3…，与包内排序有关）、**地级市 adcode（6 位）**、**市名**、**省级 adcode（6 位）**。
- **非**逐条 POI 点表；样例 Excel 工作表名为 **`2019B_ministreet_map_city`**。

### C. 分类说明 `2019\2019\ministreet_category.xls`

- **xls**，需 **xlrd** 或转 xlsx 后读取。

### D. 按业务类别的 Shapefile（`poi_extracted\2019\<中文类别目录>\`，**本复现不用**）

- 数据包内可能仍有 **约 18** 个 `.shp`（在 `zip_extracted` 外），多数为 `NAME`、`KIND`、`WGS_Lon`、`WGS_Lat` 等；**仅作备查**，**不参与**乡镇 POI 面板统计。

---

## 2020

### 组织方式

- `poi_extracted\2020\<地级市名>\*.csv`，**368** 个地级市文件夹；**各市下多 CSV**（按 POI 业务类分文件）。
- **编码**：**UTF-8（带 BOM）**；抽样多市**列名一致**。

### 字段（22 列）

`id`, `tag`, `name`, `dtype`, `typecode`, `address`, `tel`, `pcode`, `pname`, `citycode`, `cityname`, `adcode`, `adname`, `business_area`, `marlon`, `marlat`, `wgs84lon`, `wgs84lat`, `timestamp`, **`大类`**, **`中类`**, **`小类`**

### 备注

- 论文复现筛选公共产品 POI 时，优先用 **`大类`/`中类`/`小类`** 与分类标准表对应。
- 坐标建议主用 **`wgs84lon` / `wgs84lat`**。

**乡镇面板**（`05_township_poi_panel_wide_2018_2021_contains_last_segment.py`）：仅用 **`小类`** 与标准表「小类」**完全相等**（与 2012–2017 `CATEGORY` 规则同类）；坐标 **`wgs84lon`、`wgs84lat`**。

---

## 2021

### 组织方式

- `poi_extracted\2021\*.csv`，**中文表头**；抽样约 **340** 个 csv（与解压结果一致）。

### 字段（16 列）

`序号`, `状态`, `查询时间`, `城市`, `关键字`, `方式`, `PoiID`, `名称`, `类别`, `经纬度`, `地址`, `距离中心(仅圆形范围)`, `固话`, `手机`, `电话(原值)`, `轮廓坐标`

### 备注

- **`经纬度`** 多为合并字符串，需拆分规则。
- **编码**：抽样为 **UTF-8 BOM**。

**乡镇面板**（`05_township_poi_panel_wide_2018_2021_contains_last_segment.py`）：仅用 **`类别`** 做「小类」包含匹配；坐标 **`经纬度`** 解析。

---

## 2022

### 组织方式

- 分区子目录下 CSV（如按大区/省）。

### 字段（8 列）

`名称`, `大类`, `中类`, `经度`, `纬度`, `省份`, `城市`, `区域`

### 备注

- **编码**：抽样 **UTF-8 BOM**。

---

## 2023

### 组织方式

- `poi_extracted\2023\<省级包>\...\*.xlsx`

### 字段（13 列）

`id`, `name`, `type`, `address`, `location`, `typecode`, `pcode`, `pname`, `citycode`, `cityname`, `adcode`, `adname`, `tel`

### 备注

- **无** 与 2020 完全一致的「大类/中类/小类」三列；需用 `type` / `typecode` 映射到标准分类。
- **`location`** 为字符串，需解析坐标。
- 读取：**openpyxl**。

---

## 维护说明

- 机器可读快照：`test/poi_field_structure_scan.json`（与本文同批生成；若需更新字段结构，请自行对照数据源修订）。
