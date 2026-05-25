
import csv
from pathlib import Path
from typing import Any

import numpy as np

from .Channel import Channel
from .RPC3 import RPC3
from .rpc3meta import (
    adapt_headers_for_csv,
    headers_from_metadata_payload,
    load_rpc3_metadata,
    load_template_headers,
    resolve_metadata_path,
)
from .writter import RPC3WriteOptions


def convert_xlsx_to_csv(xlsx_file_path: str | Path, csv_file_path: str | Path) -> Path:
    rows = _load_xlsx_rows(Path(xlsx_file_path))
    output_path = Path(csv_file_path)
    with output_path.open("w", newline="", encoding="utf-8") as file_handle:
        writer = csv.writer(file_handle)
        writer.writerows(rows)
    return output_path


def read_csv_file(file_path: str | Path) -> tuple[np.ndarray, list[np.ndarray], list[str], list[str], float]:
    table = read_table_file(file_path)
    return (
        table["time"],
        table["channel_data"],
        table["names"],
        table["units"],
        table["dt"],
    )


def read_table_file(file_path: str | Path) -> dict[str, Any]:
    input_path = Path(file_path)
    if input_path.suffix.lower() == ".xlsx":
        rows = _load_xlsx_rows(input_path)
    elif input_path.suffix.lower() == ".csv":
        rows = _load_csv_rows(input_path)
    else:
        raise ValueError("Unsupported file format. Use CSV or XLSX.")

    if len(rows) < 2:
        raise ValueError("The input file must contain at least a header row and one data row.")

    headers = [_cell_to_text(value) or f"Column_{index}" for index, value in enumerate(rows[0])]
    if len(headers) < 2:
        raise ValueError("The input file must contain at least one time column and one data channel.")

    units = [""] * len(headers)
    data_start = 1
    if len(rows) > 1 and not _is_numeric_row(rows[1]):
        units = [_cell_to_text(value) for value in rows[1]]
        data_start = 2

    numeric_rows: list[list[float]] = []
    for row_index, row in enumerate(rows[data_start:], start=data_start + 1):
        if not any(_cell_to_text(value) for value in row):
            continue
        padded_row = list(row) + [""] * (len(headers) - len(row))
        try:
            numeric_rows.append(
                [float(_cell_to_text(value)) for value in padded_row[: len(headers)]]
            )
        except ValueError as exc:
            raise ValueError(f"Non-numeric value found in data row {row_index}.") from exc

    if not numeric_rows:
        raise ValueError("The input file does not contain any numeric data rows.")

    matrix = np.asarray(numeric_rows, dtype=np.float64)
    time = matrix[:, 0]
    dt = _infer_dt(time)
    channel_data = [matrix[:, column_index].astype(np.float32) for column_index in range(1, matrix.shape[1])]

    return {
        "time": time,
        "channel_data": channel_data,
        "names": headers[1:],
        "units": units[1:],
        "dt": dt,
    }


def csv_to_rpc3(
    csv_file_path: str | Path,
    output_rsp_file_path: str | Path | None = None,
    dt: float | None = None,
    write_options: RPC3WriteOptions | None = None,
    metadata_path: str | Path | None = None,
    template_rsp_path: str | Path | None = None,
    write_option_overrides: dict[str, Any] | None = None,
) -> Path:
    table = read_table_file(csv_file_path)
    output_path = Path(output_rsp_file_path) if output_rsp_file_path else Path(csv_file_path).with_suffix(".rsp")
    resolved_dt = float(dt) if dt is not None else table["dt"]
    if resolved_dt <= 0:
        raise ValueError("dt must be positive. Provide dt explicitly if the input time column is too short.")

    source_headers = resolve_source_headers(
        csv_file_path=csv_file_path,
        names=table["names"],
        units=table["units"],
        dt=resolved_dt,
        metadata_path=metadata_path,
        template_rsp_path=template_rsp_path,
    )
    resolved_write_options = build_write_options(
        source_headers=source_headers,
        write_options=write_options,
        write_option_overrides=write_option_overrides,
    )

    channels: list[Channel] = []
    for index, (data, name, unit) in enumerate(
        zip(table["channel_data"], table["names"], table["units"]),
        start=1,
    ):
        channel = Channel(number=index, name=name, units=unit, dt=resolved_dt, scale=1.0)
        channel.values = np.asarray(data, dtype=np.float32)
        channels.append(channel)

    rpc3 = RPC3.from_channels(str(output_path), resolved_dt, channels, headers=source_headers)
    rpc3.save(str(output_path), write_options=resolved_write_options)
    return output_path


def file_to_rpc3(
    input_file_path: str | Path,
    output_rsp_file_path: str | Path | None = None,
    dt: float | None = None,
    write_options: RPC3WriteOptions | None = None,
    metadata_path: str | Path | None = None,
    template_rsp_path: str | Path | None = None,
    write_option_overrides: dict[str, Any] | None = None,
) -> Path:
    input_path = Path(input_file_path)
    if input_path.suffix.lower() not in {".csv", ".xlsx"}:
        raise ValueError("Unsupported file format. Use CSV or XLSX.")
    return csv_to_rpc3(
        csv_file_path=input_path,
        output_rsp_file_path=output_rsp_file_path,
        dt=dt,
        write_options=write_options,
        metadata_path=metadata_path,
        template_rsp_path=template_rsp_path,
        write_option_overrides=write_option_overrides,
    )


def resolve_source_headers(
    csv_file_path: str | Path,
    names: list[str],
    units: list[str],
    dt: float,
    metadata_path: str | Path | None = None,
    template_rsp_path: str | Path | None = None,
) -> dict[str, Any]:
    resolved_metadata_path = resolve_metadata_path(csv_file_path, metadata_path)
    if resolved_metadata_path is not None:
        payload = load_rpc3_metadata(resolved_metadata_path)
        return adapt_headers_for_csv(
            names=names,
            units=units,
            dt=dt,
            source_headers=headers_from_metadata_payload(payload),
        )

    if template_rsp_path is not None:
        return adapt_headers_for_csv(
            names=names,
            units=units,
            dt=dt,
            source_headers=load_template_headers(template_rsp_path),
        )

    return {}


def build_write_options(
    source_headers: dict[str, Any],
    write_options: RPC3WriteOptions | None = None,
    write_option_overrides: dict[str, Any] | None = None,
) -> RPC3WriteOptions | None:
    if write_options is not None and write_option_overrides:
        raise ValueError("Use either write_options or write_option_overrides, not both.")

    if write_options is not None:
        return write_options

    if not write_option_overrides:
        return None

    from .writter import make_write_options_from_headers

    options = make_write_options_from_headers(source_headers)
    for key, value in write_option_overrides.items():
        setattr(options, key, value)
    return options


def _load_csv_rows(file_path: Path) -> list[list[str]]:
    with file_path.open("r", newline="", encoding="utf-8-sig") as file_handle:
        return [row for row in csv.reader(file_handle)]


def _load_xlsx_rows(file_path: Path) -> list[list[Any]]:
    try:
        import pandas as pd
    except ImportError as exc:
        raise ImportError("pandas is required for XLSX input support.") from exc

    dataframe = pd.read_excel(file_path, header=None)
    return dataframe.where(dataframe.notna(), "").values.tolist()


def _cell_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and np.isnan(value):
        return ""
    return str(value).strip()


def _is_numeric_row(row: list[Any]) -> bool:
    if not row:
        return False
    has_value = False
    for value in row:
        text = _cell_to_text(value)
        if text == "":
            return False
        has_value = True
        try:
            float(text)
        except ValueError:
            return False
    return has_value


def _infer_dt(time: np.ndarray) -> float:
    if time.size < 2:
        return 0.0

    deltas = np.diff(time)
    if np.any(deltas <= 0):
        raise ValueError("Time values must be strictly increasing.")

    median_delta = float(np.median(deltas))
    if not np.allclose(
        deltas,
        median_delta,
        rtol=1e-4,
        atol=max(1e-9, abs(median_delta) * 1e-6),
    ):
        raise ValueError("Time values are not evenly spaced. Provide dt explicitly.")

    return median_delta

