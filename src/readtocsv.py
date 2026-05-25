import csv
from pathlib import Path

import numpy as np

from .RPC3 import RPC3
from .rpc3meta import default_metadata_path, save_rpc3_metadata


def save_npy_data_to_file(rpc3_obj: RPC3, overwrite: bool = False) -> Path:
    file_path = Path(rpc3_obj.filename)
    file_path_data = file_path.with_suffix(".npz")

    if file_path_data.is_file() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing file: {file_path_data}")

    data = np.array([channel.values for channel in rpc3_obj.channels], dtype=np.float32).T
    times = np.arange(rpc3_obj.sample_count, dtype=np.float64) * rpc3_obj.dt
    headers = rpc3_obj.headers
    channels = [{"Description": ch.name, "Units": ch.units} for ch in rpc3_obj.channels]

    np.savez(file_path_data, data=data, time=times, headers=headers, channels=channels)
    return file_path_data


def export_data_to_csv(
    rpc3_obj: RPC3,
    output_file: str | Path,
    overwrite: bool = False,
    float_format: str | None = None,
    write_metadata: bool = True,
    metadata_file: str | Path | None = None,
) -> Path:
    file_path_data = Path(output_file).with_suffix(".csv")
    if file_path_data.is_file() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing file: {file_path_data}")

    names = ["Time", *[channel.name for channel in rpc3_obj.channels]]
    units = ["s", *[channel.units for channel in rpc3_obj.channels]]
    times = np.arange(rpc3_obj.sample_count, dtype=np.float64) * rpc3_obj.dt

    with file_path_data.open("w", newline="", encoding="utf-8") as file_handle:
        writer = csv.writer(file_handle)
        writer.writerow(names)
        writer.writerow(units)

        for sample_index in range(rpc3_obj.sample_count):
            row = [times[sample_index], *[channel.values[sample_index] for channel in rpc3_obj.channels]]
            writer.writerow([_format_value(value, float_format) for value in row])

    if write_metadata:
        resolved_metadata_path = Path(metadata_file) if metadata_file else default_metadata_path(file_path_data)
        save_rpc3_metadata(
            rpc3_obj=rpc3_obj,
            metadata_path=resolved_metadata_path,
            overwrite=overwrite,
        )

    return file_path_data


def rsp_to_csv(
    input_file: str | Path,
    output_file: str | Path | None = None,
    overwrite: bool = False,
    read_channels: list[int] | None = None,
    float_format: str | None = None,
    write_metadata: bool = True,
    metadata_file: str | Path | None = None,
) -> Path:
    input_path = Path(input_file)
    output_path = Path(output_file) if output_file else input_path.with_suffix(".csv")
    rpc3_obj = RPC3(str(input_path), read_channels=read_channels)
    if rpc3_obj.get_errors():
        raise ValueError("; ".join(rpc3_obj.get_errors()))
    return export_data_to_csv(
        rpc3_obj,
        output_path,
        overwrite=overwrite,
        float_format=float_format,
        write_metadata=write_metadata,
        metadata_file=metadata_file,
    )


def _format_value(value: float, float_format: str | None) -> str:
    if float_format is None:
        return repr(float(value))
    return format(float(value), float_format)
