# 脚本归档说明

脚本按主题分子目录，默认输入/输出仍相对 **`test/`**（与 `Path(__file__).parent.parent.parent` 对齐）。

| 目录 | 内容 | 序号 |
|------|------|------|
| [`enterprise/`](./enterprise/) | 工商注册、区划表、乡镇匹配、并行提取、面板与统计 | `01_`…`07_` |
| [`poi/`](./poi/) | POI 解压、解析、乡镇宽表、县域属性并入 | `01_`…`06_` |
| [`../anther_data_enterprise/`](../anther_data_enterprise/) | 1223 分片 CSV：行数统计、提取、并行合并、并入区划（与 `enterprise/` 并列，见该目录 `README.md`） | `01_`…`04_` |

**说明**：`enterprise/07_*.py` 内用 `importlib` 加载 `02_extract_enterprises_to_township.py`（因模块名以数字开头，不能写 `from 02_... import`）。

运行示例（在仓库根目录 `gbif/` 下）：

```text
python test/scripts/enterprise/02_extract_enterprises_to_township.py --max-files 2
python test/scripts/poi/01_extract_poi_to_folder.py
python test/anther_data_enterprise/03_run_extract_csv_parallel.py --dry-run
```
