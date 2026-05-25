# pyRPC3

pyRPC3 是一组用于处理 RPC3/RSP 时域数据文件的 Python 工具，可以读取二进制 RSP 文件、导出通道数据到 CSV，并从 CSV 或 XLSX 重建 RPC3 兼容的 `.rsp` 文件。

本项目重点覆盖实用的 RSP/CSV 双向链路：

- 解析二进制 RPC3/RSP 文件头和通道数据
- 导出通道数据到 CSV，并可生成 `.rpc3meta.json` 元数据旁路文件
- 从 CSV/XLSX 重建 `.rsp` 文件
- 尽可能保留源文件中的关键头信息和通道 scale 元数据
- 使用样例文件执行 RSP -> CSV -> RSP 双阶段 roundtrip 校验

## 环境要求

- Python 3.10 或更新版本
- NumPy
- pandas，仅在读取 XLSX 输入时需要
- matplotlib，仅在使用 `Channel.plot()` 时需要

安装基础依赖：

```bash
pip install -r requirements.txt
```

## 命令行用法

通过 `python -m src.cli` 运行命令行工具。

将 RPC3/RSP 文件转换为 CSV：

```bash
python -m src.cli to-csv sample_rsp_files/WM0826rsp.rsp -o output/WM0826rsp.csv --overwrite
```

只导出指定通道，通道编号从 1 开始：

```bash
python -m src.cli to-csv sample_rsp_files/WM0826rsp.rsp --channels 1 2 3 --overwrite
```

将 CSV 转回 RSP：

```bash
python -m src.cli to-rsp output/WM0826rsp.csv -o output/WM0826rsp_roundtrip.rsp
```

如果 CSV 旁边存在匹配的 `.rpc3meta.json` 文件，转换器会自动复用其中保留的头信息。也可以显式指定 metadata 文件或模板 RSP：

```bash
python -m src.cli to-rsp output/WM0826rsp.csv --metadata output/WM0826rsp.rpc3meta.json
python -m src.cli to-rsp data.csv --template-rsp sample_rsp_files/WM0826rsp.rsp
```

## 图形界面

启动本地图形界面：

```bash
python -m src.gui
```

默认访问地址为 `http://127.0.0.1:8765`。界面包含两个区域：

- `RSP -> CSV + JSON`：上传 `.rsp` 文件，输出 `.csv` 和 `.rpc3meta.json`
- `CSV + JSON -> RSP`：上传 `.csv` 和对应的 `.rpc3meta.json`，输出 `.rsp`

## 打包 Windows EXE

安装 PyInstaller 后运行：

```powershell
.\build_exe.ps1
```

生成文件位于 `dist\pyRPC3-GUI.exe`。双击 exe 后会启动本地服务并自动打开浏览器界面。

## Python API

```python
from src import RPC3, rsp_to_csv, csv_to_rpc3

rpc = RPC3("sample_rsp_files/WM0826rsp.rsp")
if rpc.get_errors():
    raise RuntimeError("; ".join(rpc.get_errors()))

rpc.info()
rsp_to_csv("sample_rsp_files/WM0826rsp.rsp", "output/WM0826rsp.csv", overwrite=True)
csv_to_rpc3("output/WM0826rsp.csv", "output/WM0826rsp_roundtrip.rsp")
```

## 校验

运行内置样例的完整双向链路校验：

```bash
python validate_roundtrip_samples.py full
```

校验脚本会把生成的 CSV/RSP 文件和汇总报告写入 `output/roundtrip_validation/`。该目录可由样例文件重新生成，因此默认被 Git 忽略。

默认情况下，校验要求 RSP -> CSV 和 CSV -> RSP 的最大绝对误差都为 0。一旦出现非零误差或通道数、采样点数、采样间隔不匹配，脚本会直接失败。

## 项目结构

```text
src/
  Channel.py        通道模型和绘图辅助
  RPC3.py           RPC3/RSP 读取器和高级保存 API
  writter.py        RPC3 二进制写入实现
  readtocsv.py      RSP 导出 CSV 的辅助函数
  csvtorsp.py       CSV/XLSX 导入 RSP 的辅助函数
  rpc3meta.py       元数据旁路文件辅助函数
  cli.py            命令行入口
sample_rsp_files/   校验使用的样例输入文件
validate_roundtrip_samples.py
RPC3_Format.txt     RPC3 格式参考文本
```

## 注意事项

- 当前不支持 ASCII RPC3 数据。
- 当前读取器会拒绝 `HALF_FRAMES` 输入文件。
- 当没有源 metadata 或模板 RSP 时，短整型 RSP 输出会根据 RPC3 scale 重新量化。内置的 RSP -> CSV -> RSP 校验路径会保留源 scale 元数据，并且对当前样例应当精确 roundtrip。

---

# English

pyRPC3 is a set of Python tools for reading RPC3/RSP time-history files, exporting channel data to CSV, and rebuilding RPC3-compatible `.rsp` files from CSV or XLSX data.

The project focuses on practical RSP/CSV roundtrips:

- parse binary RPC3/RSP headers and channel data
- export channels to CSV with optional `.rpc3meta.json` metadata sidecars
- rebuild `.rsp` files from CSV/XLSX inputs
- preserve important source header fields and channel scale metadata where possible
- validate sample files with a two-phase RSP -> CSV -> RSP roundtrip check

## Requirements

- Python 3.10 or newer
- NumPy
- pandas, only for XLSX input support
- matplotlib, only for `Channel.plot()`

Install the basic dependencies:

```bash
pip install -r requirements.txt
```

## Command Line Usage

Run the package CLI with `python -m src.cli`.

Convert an RPC3/RSP file to CSV:

```bash
python -m src.cli to-csv sample_rsp_files/WM0826rsp.rsp -o output/WM0826rsp.csv --overwrite
```

Export selected 1-based channels:

```bash
python -m src.cli to-csv sample_rsp_files/WM0826rsp.rsp --channels 1 2 3 --overwrite
```

Convert CSV back to RSP:

```bash
python -m src.cli to-rsp output/WM0826rsp.csv -o output/WM0826rsp_roundtrip.rsp
```

If the CSV has a matching `.rpc3meta.json` sidecar, the converter reuses preserved header metadata automatically. You can also provide a metadata file or template RSP explicitly:

```bash
python -m src.cli to-rsp output/WM0826rsp.csv --metadata output/WM0826rsp.rpc3meta.json
python -m src.cli to-rsp data.csv --template-rsp sample_rsp_files/WM0826rsp.rsp
```

## Graphical Interface

Start the local graphical interface:

```bash
python -m src.gui
```

The default URL is `http://127.0.0.1:8765`. The interface has two work areas:

- `RSP -> CSV + JSON`: upload an `.rsp` file and export `.csv` plus `.rpc3meta.json`
- `CSV + JSON -> RSP`: upload a `.csv` file and its matching `.rpc3meta.json`, then export `.rsp`

## Build Windows EXE

Install PyInstaller, then run:

```powershell
.\build_exe.ps1
```

The generated executable is `dist\pyRPC3-GUI.exe`. Double-clicking the exe starts the local service and opens the browser interface automatically.

## Python API

```python
from src import RPC3, rsp_to_csv, csv_to_rpc3

rpc = RPC3("sample_rsp_files/WM0826rsp.rsp")
if rpc.get_errors():
    raise RuntimeError("; ".join(rpc.get_errors()))

rpc.info()
rsp_to_csv("sample_rsp_files/WM0826rsp.rsp", "output/WM0826rsp.csv", overwrite=True)
csv_to_rpc3("output/WM0826rsp.csv", "output/WM0826rsp_roundtrip.rsp")
```

## Validation

Run the bundled sample roundtrip validation:

```bash
python validate_roundtrip_samples.py full
```

The validator writes generated CSV/RSP files and summaries under `output/roundtrip_validation/`. That directory is intentionally ignored by Git because it can be regenerated from the checked-in samples.

By default, validation requires both the RSP -> CSV phase and the CSV -> RSP phase to have zero maximum absolute difference. The script fails if any non-zero difference, channel-count mismatch, sample-count mismatch, or sampling-interval mismatch is detected.

## Project Layout

```text
src/
  Channel.py        Channel model and plotting helper
  RPC3.py           RPC3/RSP reader and high-level save API
  writter.py        RPC3 binary writer implementation
  readtocsv.py      RSP to CSV export helpers
  csvtorsp.py       CSV/XLSX to RSP import helpers
  rpc3meta.py       Metadata sidecar helpers
  cli.py            Command line interface
sample_rsp_files/   Sample input files used by validation
validate_roundtrip_samples.py
RPC3_Format.txt     RPC3 format reference text
```

## Notes

- ASCII RPC3 data is currently not supported.
- `HALF_FRAMES` input files are currently rejected by the reader.
- Short-integer RSP output is quantized through the RPC3 scale factor when no source metadata or template RSP is available. The bundled RSP -> CSV -> RSP validation path preserves source scale metadata and is expected to roundtrip exactly for the included samples.
