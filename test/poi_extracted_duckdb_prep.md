# `poi_extracted` 各年份 POI 字段与结构概要（DuckDB 入库筹备）

数据根：`F:\BaiduNetdiskDownload\地级市POI兴趣点\poi_extracted`。  
下文基于**抽样文件**读取表头/字段（用于建库设计；全量以实际文件为准）。

## 与现有 DuckDB 脚本的对应关系（`gbif_scripts`）

| 脚本 | 用途 | 与 POI 的衔接 |
|------|------|----------------|
| [gbif_scripts/01_data_import/build_duckdb_from_csv.py](../gbif_scripts/01_data_import/build_duckdb_from_csv.py) | `duckdb.connect`、`read_csv` 批量入库、列筛选、线程数 | **2020、2018、2021、2022** 等 CSV；需统一编码、列名 |
| [gbif_scripts/01_data_import/import_shapefile_to_duckdb.py](../gbif_scripts/01_data_import/import_shapefile_to_duckdb.py) | `geopandas.read_file` → DataFrame → `CREATE TABLE`，可选 `INSTALL spatial` / WKT | **2012–2017、2019** 等 shapefile；几何可存 WKT 或 DuckDB Spatial |
| [gbif_scripts/02_data_preview/preview_duckdb.py](../gbif_scripts/02_data_preview/preview_duckdb.py) | `PRAGMA table_info`、抽样预览 | 建表后验收 |

入库时建议为每条记录增加 **`data_year`（四位年）**、**`source_relpath`**（相对 `poi_extracted` 的路径），便于追溯。

---

## 按年份：载体类型与字段结构

### 2012–2017：Shapefile（`EPSG:4326`）

- **位置**：`poi_extracted\YYYY\YYYY\`，按图层多个 `.shp`（如「交通设施服务」「事件活动」等）。
- **属性列（抽样各年一致）**：`NAME`, `ADDRESS`, `TELEPHONE`, `PROVINCE`, `CITY`, `COUNTY`, `CODE`, `LON`, `LAT`, `TYPECODE`, `BASETYPE`, `SUBTYPE`, `CATEGORY`，另加 **`geometry`**（点）。
- **与论文 POI 字段的对应**：英文列名；分类信息在 `TYPECODE` / `BASETYPE` / `SUBTYPE` / `CATEGORY`，需与 `公共产品供给分类标准.csv` 的「小类」做映射时再统一口径。
- **入库**：优先 `geopandas` 读入 → 几何转 WKT 或 `ST_GeomFromText`；属性列可直接进 DuckDB。

### 2020：各地级市子文件夹内多 CSV（UTF-8，带 BOM）

- **位置**：`poi_extracted\2020\<市名>\*.csv`。
- **列（抽样多市一致，22 列）**：`id`, `tag`, `name`, `dtype`, `typecode`, `address`, `tel`, `pcode`, `pname`, `citycode`, `cityname`, `adcode`, `adname`, `business_area`, `marlon`, `marlat`, `wgs84lon`, `wgs84lat`, `timestamp`, **`大类`**, **`中类`**, **`小类`**。
- **说明**：与论文「大类/中类/小类」筛选一致；坐标建议统一用 **`wgs84lon` / `wgs84lat`**（或确认与 `marlon`/`marlat` 分工后再定）。
- **入库**：`read_csv(..., encoding='utf-8-sig')`；可按市 `COPY` 追加到同一张表，并写 `data_year=2020`、`city_folder=<市名>`。

### 2023：省级包内 xlsx

- **位置**：`poi_extracted\2023\<省级包>\...\*.xlsx`。
- **列（抽样 13 列）**：`id`, `name`, `type`, `address`, `location`, `typecode`, `pcode`, `pname`, `citycode`, `cityname`, `adcode`, `adname`, `tel`。
- **说明**：**无**「大类/中类/小类」三列，`type` / `typecode` 需自行映射到分类标准；`location` 可能为字符串坐标，入库前需解析规则。
- **入库**：`pandas.read_excel` + `openpyxl`；或导出 CSV 后用 DuckDB `read_csv`。

### 2018：顶层多个 CSV

- **抽样列（11 列）**：`address`, `adname`, `page_publish_time`, `adcode`, `pname`, `cityname`, `name`, `location`, `_id`, `type`, `Unnamed: 10`。
- **说明**：存在无意义列 `Unnamed: 10`，清洗时可丢弃；`location` 需解析坐标。

### 2019：「分图层 Shapefile + 辅助表」为主（与 2012–2017 单目录多 shp 的组织方式不同）

**根目录**：`poi_extracted\2019\`。

#### 1）主数据：按**业务类别分子文件夹**，每类一套 **Shapefile**（点，`EPSG:4326`）

- 抽样约 **18 个** `.shp`，分布在多个子目录（如停车、加油站、公园、医疗、学校、酒店、收费站、公司企业点、住宿等；目录名为中文）。
- **多数图层**属性字段一致：**`NAME`**, **`KIND`**, **`WGS_Lon`**, **`WGS_Lat`**，另加 **`geometry`**。入库时可映射为统一 `name`、`kind`（或 `poi_type`）、`lon`、`lat`。
- **少数图层字段不一致**（需单独分支或后处理）：  
  - 例如「景区」类：含中文属性列（如名称、等级及 BD/WGS 经纬等多列）；  
  - 「零售店铺」类：除 `NAME`/`KIND` 外，坐标为 **`实地X` / `实地Y`**；  
  - 「文体服务」类：纬度列名为 **`WGS_lat`**（小写 `lat`），与多数图层的 **`WGS_Lat`** 不一致，合并表时注意列名统一。
- 各类目录下常伴有 **`.xls` / `.xlsx`「对照表」**（如 `*_对照表.xls`），需 **`xlrd`** 等库读取；可与 `ministreet_category.xls` 一起做分类码对照。

#### 2）城市清单：`2019\2019\ministreet_map_city.csv`

- **无表头**，**GBK** 编码，约 **387 行**，4 列逗号分隔。语义可理解为：  
  **`序号`（或内部编号）、地级市 adcode、地级市名称、所属省级 adcode**（具体命名可在入库时写死为 `seq`, `city_adcode`, `city_name`, `province_adcode`）。  
- 性质：**城市级索引/辅助表**，不是逐条 POI 点记录；可与各类 POI 图层通过 `adcode` / 名称等关联（按研究设计决定）。

#### 3）分类说明表：`2019\2019\ministreet_category.xls`

- 体量约几十 KB，**分类/代码说明**用；读取需 **`xlrd`**（或先另存为 xlsx 再用 `openpyxl`）。

#### 4）子目录 `2019\2019\` 内的 **分包 `100000.zip`～`600000.zip`**

- 每个 zip 内为 **`NNNNNN/d_XXXXXX.csv`**（及少量 `d_*.xls`），按**省级行政区划代码**分文件的 POI 文本表；六个包合起来约 **348 个** `d_*.csv`（已抽样统计）。
- 已在本机解压至同一目录下 **`zip_extracted\`**（与六个 zip 并列），解压时**跳过** `__MACOSX` 垃圾目录；解压后总占用约 **7.9 GB**（以实际为准）。
- **CSV 编码**多为 **GBK/GB18030**，**无标准表头行**，首行即为数据；字段顺序可理解为（需用中文环境核对列名）：**序号、名称、地址、纬度、经度、大类（分号分隔）、中类或小类（分号分隔）、电话**（具体以样本 `d_110000.csv` 为准）。
- 与上文「按类 Shapefile」并存：**同一 2019 年数据两种组织**（分图层 shp + 分省 csv 包），入库时勿混为同一套逻辑。

#### 入库提示（2019）

- POI 主体建议按 **「图层 + 路径」** 循环：`geopandas.read_file` → 统一列名（尤其 `WGS_Lat` / `WGS_lat`、`实地X/Y`）→ 增加列 **`layer_key`**（可用父文件夹名或 `KIND`）→ 再写入 DuckDB。  
- `ministreet_map_city.csv` 建议**单独表**；与 POI 点表是否外键关联按课题定。

### 2021：顶层大量按城市 CSV

- **抽样列（16 列）**：`序号`, `状态`, `查询时间`, `城市`, `关键字`, `方式`, `PoiID`, `名称`, `类别`, `经纬度`, `地址`, …, `轮廓坐标`。
- **说明**：字段为**中文表头**；`经纬度` 可能为合并字符串，需拆分；与 2020 列名不一致，入库需**统一映射层**。

### 2022：分区目录下 CSV

- **抽样列（8 列）**：`名称`, `大类`, `中类`, `经度`, `纬度`, `省份`, `城市`, `区域`。
- **说明**：与论文分类列较接近；**无** `wgs84lon/lat` 命名，用 `经度`/`纬度`。

---

## 建库层面的统一建议（后续实现）

1. **分「层」**：  
   - **点层**：统一 `poi_id`（或源 `id`）、`name`、`lon`、`lat`、`year`、`source_file`；  
   - **分类层**：`typecode` + 映射后的 `大类/中类/小类`（或标准表中的 `category`）。  
2. **异构年份**：用 **`ingest_format`** 标记 `gaode_csv_2020` / `shp_2012_2017` / `xlsx_2023` 等，便于分脚本导入。  
3. **编码**：CSV 优先 `utf-8-sig`，失败再试 `gb18030`；2019 单独 **GBK**。  
4. **几何**：Shapefile 与 CSV 点最终统一为 **WGS84 双精度经纬度** 两列，便于与乡镇面数据做空间连接。

---

## 抽样说明

- 字段列表来自对 `poi_extracted` 的抽样读表；若某年目录结构有更新，请重新抽样核对。
