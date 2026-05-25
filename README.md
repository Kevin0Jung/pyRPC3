# pyRPC3

Python tools for reading RPC3/RSP time-history files, exporting channel data to CSV, and rebuilding RPC3-compatible `.rsp` files from CSV or XLSX data.

The project focuses on practical RPC3 roundtrips:

- parse binary RPC3/RSP headers and channel data
- export channels to CSV with optional metadata sidecars
- rebuild `.rsp` files from CSV/XLSX inputs
- preserve important source header metadata where possible
- validate sample files with a two-phase roundtrip check

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
