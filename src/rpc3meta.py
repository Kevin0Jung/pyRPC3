import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from .RPC3 import RPC3

METADATA_SUFFIX = ".rpc3meta.json"
STANDARD_HEADER_KEYS = (
    "FORMAT",
    "FILE_TYPE",
    "DATA_TYPE",
    "TIME_TYPE",
    "DELTA_T",
    "PTS_PER_FRAME",
    "PTS_PER_GROUP",
    "FRAMES",
    "HALF_FRAMES",
    "REPEATS",
    "INT_FULL_SCALE",
    "BYPASS_FILTER",
    "DATE",
    "OPERATION",
)
COPY_PREFIXES = ("PARENT_",)


def default_metadata_path(data_file: str | Path) -> Path:
    return Path(data_file).with_suffix(METADATA_SUFFIX)


def save_rpc3_metadata(
    rpc3_obj: RPC3,
    metadata_path: str | Path | None = None,
    overwrite: bool = False,
) -> Path:
    output_path = Path(metadata_path) if metadata_path else default_metadata_path(rpc3_obj.filename)
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing metadata file: {output_path}")

    payload = {
        "rpc3meta_version": 1,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_rsp": str(rpc3_obj.filename),
        "headers": snapshot_headers_for_export(rpc3_obj),
    }

    with output_path.open("w", encoding="utf-8") as file_handle:
        json.dump(_json_ready(payload), file_handle, ensure_ascii=False, indent=2)

    return output_path


def load_rpc3_metadata(metadata_path: str | Path) -> dict[str, Any]:
    with Path(metadata_path).open("r", encoding="utf-8") as file_handle:
        payload = json.load(file_handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Metadata file is not a JSON object: {metadata_path}")
    return payload


def resolve_metadata_path(
    data_file: str | Path,
    explicit_metadata_path: str | Path | None = None,
) -> Path | None:
    if explicit_metadata_path is not None:
        path = Path(explicit_metadata_path)
        if not path.is_file():
            raise FileNotFoundError(f"Metadata file not found: {path}")
        return path

    candidate = default_metadata_path(data_file)
    if candidate.is_file():
        return candidate
    return None


def headers_from_metadata_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    if "headers" not in payload:
        raise ValueError("Metadata payload does not contain a 'headers' object.")
    headers = payload["headers"]
    if not isinstance(headers, dict):
        raise ValueError("Metadata payload 'headers' is not an object.")
    return dict(headers)


def snapshot_headers_for_export(rpc3_obj: RPC3) -> dict[str, Any]:
    source_headers = dict(rpc3_obj.headers)
    headers: dict[str, Any] = {}

    for key in STANDARD_HEADER_KEYS:
        if key in source_headers:
            headers[key] = source_headers[key]

    for prefix in COPY_PREFIXES:
        for key, value in source_headers.items():
            if key.startswith(prefix):
                headers[key] = value

    headers["DELTA_T"] = rpc3_obj.dt
    headers["CHANNELS"] = len(rpc3_obj.channels)
    headers["PARTITIONS"] = 1
    headers["PART.CHAN_1"] = 1
    headers["PART.NCHAN_1"] = len(rpc3_obj.channels)
    headers["BYPASS_FILTER"] = source_headers.get("BYPASS_FILTER", 0)

    for export_index, channel in enumerate(rpc3_obj.channels, start=1):
        source_index = channel.number
        headers[f"DESC.CHAN_{export_index}"] = channel.name
        headers[f"UNITS.CHAN_{export_index}"] = channel.units
        headers[f"SCALE.CHAN_{export_index}"] = source_headers.get(
            f"SCALE.CHAN_{source_index}",
            getattr(channel, "scale", 1.0),
        )
        headers[f"LOWER_LIMIT.CHAN_{export_index}"] = source_headers.get(
            f"LOWER_LIMIT.CHAN_{source_index}",
            -1.0,
        )
        headers[f"UPPER_LIMIT.CHAN_{export_index}"] = source_headers.get(
            f"UPPER_LIMIT.CHAN_{source_index}",
            1.0,
        )
        headers[f"MAP.CHAN_{export_index}"] = source_headers.get(
            f"MAP.CHAN_{source_index}",
            source_index,
        )

    return headers


def adapt_headers_for_csv(
    names: list[str],
    units: list[str],
    dt: float,
    source_headers: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    source = dict(source_headers or {})
    headers: dict[str, Any] = {}

    for key in STANDARD_HEADER_KEYS:
        if key in source:
            headers[key] = source[key]

    for prefix in COPY_PREFIXES:
        for key, value in source.items():
            if key.startswith(prefix):
                headers[key] = value

    channel_count = len(names)
    headers["DELTA_T"] = dt
    headers["CHANNELS"] = channel_count
    headers["BYPASS_FILTER"] = source.get("BYPASS_FILTER", 0)
    headers["PARTITIONS"] = 1
    headers["PART.CHAN_1"] = 1
    headers["PART.NCHAN_1"] = channel_count

    source_channel_count = _safe_int(source.get("CHANNELS"), 0)
    preserve_channel_metadata = source_channel_count == channel_count

    for index, (name, unit) in enumerate(zip(names, units), start=1):
        headers[f"DESC.CHAN_{index}"] = name
        headers[f"UNITS.CHAN_{index}"] = unit
        if preserve_channel_metadata:
            headers[f"MAP.CHAN_{index}"] = source.get(f"MAP.CHAN_{index}", index)
        else:
            headers[f"MAP.CHAN_{index}"] = index

        if preserve_channel_metadata:
            if f"SCALE.CHAN_{index}" in source:
                headers[f"SCALE.CHAN_{index}"] = source[f"SCALE.CHAN_{index}"]
            if f"LOWER_LIMIT.CHAN_{index}" in source:
                headers[f"LOWER_LIMIT.CHAN_{index}"] = source[f"LOWER_LIMIT.CHAN_{index}"]
            if f"UPPER_LIMIT.CHAN_{index}" in source:
                headers[f"UPPER_LIMIT.CHAN_{index}"] = source[f"UPPER_LIMIT.CHAN_{index}"]

    return headers


def load_template_headers(template_rsp_path: str | Path) -> dict[str, Any]:
    template_rpc = RPC3(str(template_rsp_path), read_channels=[])
    if template_rpc.get_errors():
        raise ValueError(
            f"Failed to read template RSP {template_rsp_path}: {'; '.join(template_rpc.get_errors())}"
        )
    return dict(template_rpc.headers)


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if isinstance(value, Path):
        return str(value)
    return value
