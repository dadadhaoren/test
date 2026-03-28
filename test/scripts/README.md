# 脚本归档说明

脚本按主题分子目录，默认输入/输出仍相对 **`test/`**（与 `Path(__file__).parent.parent.parent` 对齐）。

| 目录 | 内容 |
|------|------|
| [`enterprise/`](./enterprise/) | 工商注册、乡镇匹配、区划表、并行提取、行数/年份统计等 |
| [`poi/`](./poi/) | POI 解压与解析、乡镇 POI 宽表、县域属性并入面板等 |

运行示例（在仓库根目录 `gbif/` 下）：

```text
python test/scripts/enterprise/extract_enterprises_to_township.py --max-files 2
python test/scripts/poi/extract_poi_to_folder.py
```
