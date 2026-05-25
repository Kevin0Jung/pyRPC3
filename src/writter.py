import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

import numpy as np

from .Channel import Channel

VALID_PTS_PER_FRAME = {256, 512, 1024, 2048}
SUPPORTED_BINARY_FORMATS = {"BINARY", "BINARY_IEEE_LITTLE_END", "BINARY_IEEE_BIG_END"}
STANDARD_HEADER_KEYS = {
    "FORMAT",
    "NUM_HEADER_BLOCKS",
    "NUM_PARAMS",
    "FILE_TYPE",
    "TIME_TYPE",
    "DELTA_T",
    "CHANNELS",
    "DATE",
    "OPERATION",
    "REPEATS",
    "DATA_TYPE",
    "PTS_PER_FRAME",
    "PTS_PER_GROUP",
    "FRAMES",
    "HALF_FRAMES",
    "INT_FULL_SCALE",
}
GENERATED_CHANNEL_PREFIXES = (
    "DESC.CHAN_",
    "UNITS.CHAN_",
    "SCALE.CHAN_",
    "LOWER_LIMIT.CHAN_",
    "UPPER_LIMIT.CHAN_",
)


def _is_power_of_two(value: int) -> bool:
    return value > 0 and (value & (value - 1)) == 0


def _is_little_endian_format(format_type: str) -> bool:
    return format_type in {"BINARY", "BINARY_IEEE_LITTLE_END"}


@dataclass(slots=True)
class RPC3WriteOptions:
    pts_per_frame: int = 1024
    frames_per_group: int = 2
    file_type: str = "TIME_HISTORY"
    time_type: str = "RESPONSE"
    format_type: str = "BINARY"
    data_type: str = "SHORT_INTEGER"
    repeats: int = 0
    half_frames: int = 0
    int_full_scale: int = 32768
    operation: str = "Codex RPC3 Converter"
    date: str | None = None
    lower_limit: float = -1.0
    upper_limit: float = 1.0
    extra_headers: dict[str, Any] = field(default_factory=dict)

    @property
    def pts_per_group(self) -> int:
        return self.pts_per_frame * self.frames_per_group

    def validate(self) -> None:
        if self.pts_per_frame not in VALID_PTS_PER_FRAME:
            raise ValueError(
                f"PTS_PER_FRAME must be one of {sorted(VALID_PTS_PER_FRAME)}."
            )
        if self.format_type not in SUPPORTED_BINARY_FORMATS:
            raise ValueError(
                "Only BINARY, BINARY_IEEE_LITTLE_END, and BINARY_IEEE_BIG_END are supported."
            )
        if not _is_power_of_two(self.frames_per_group):
            raise ValueError("frames_per_group must be a power of two.")
        if self.frames_per_group < 1:
            raise ValueError("frames_per_group must be at least 1.")
        if self.data_type not in {"SHORT_INTEGER", "FLOATING_POINT"}:
            raise ValueError("Only SHORT_INTEGER and FLOATING_POINT are supported.")
        if self.half_frames != 0:
            raise ValueError("HALF_FRAMES writing is not implemented; use 0.")
        if self.int_full_scale <= 0:
            raise ValueError("INT_FULL_SCALE must be positive.")


def make_write_options_from_headers(
    headers: Mapping[str, Any] | None = None,
) -> RPC3WriteOptions:
    options = RPC3WriteOptions()
    if not headers:
        return options

    def _get_int(name: str, default: int) -> int:
        try:
            return int(headers.get(name, default))
        except (TypeError, ValueError):
            return default

    options.format_type = str(headers.get("FORMAT", options.format_type))
    options.file_type = str(headers.get("FILE_TYPE", options.file_type))
    options.time_type = str(headers.get("TIME_TYPE", options.time_type))
    options.data_type = str(headers.get("DATA_TYPE", options.data_type))
    options.repeats = _get_int("REPEATS", options.repeats)
    options.half_frames = _get_int("HALF_FRAMES", options.half_frames)
    options.int_full_scale = _get_int("INT_FULL_SCALE", options.int_full_scale)
    options.pts_per_frame = _get_int("PTS_PER_FRAME", options.pts_per_frame)
    options.operation = str(headers.get("OPERATION", options.operation))
    options.date = headers.get("DATE")

    pts_per_group = _get_int("PTS_PER_GROUP", options.pts_per_group)
    if options.pts_per_frame > 0 and pts_per_group >= options.pts_per_frame:
        frames_per_group = pts_per_group // options.pts_per_frame
        if _is_power_of_two(frames_per_group):
            options.frames_per_group = frames_per_group

    extras: dict[str, Any] = {}
    for key, value in headers.items():
        if key in STANDARD_HEADER_KEYS:
            continue
        if any(key.startswith(prefix) for prefix in GENERATED_CHANNEL_PREFIXES):
            continue
        extras[key] = value
    options.extra_headers = extras
    return options


def normalize_int16(
    array: np.ndarray,
    int_full_scale: int = 32768,
) -> tuple[np.ndarray, float]:
    values = np.asarray(array, dtype=np.float64)
    if values.size == 0:
        return np.array([], dtype=np.int16), 1.0

    absmax_value = float(np.max(np.abs(values)))
    if absmax_value == 0.0:
        return np.zeros(values.shape, dtype=np.int16), 1.0

    scale = absmax_value / float(int_full_scale)
    normalized = np.rint(values / scale)
    lower_bound, upper_bound = _int_bounds(int_full_scale)
    normalized = np.clip(normalized, lower_bound, upper_bound).astype(np.int16)
    return normalized, scale


def write_rpc3(
    filename: str,
    dt: float,
    channels: list[Channel],
    write_options: RPC3WriteOptions | None = None,
    source_headers: Mapping[str, Any] | None = None,
    extra_headers: Mapping[str, Any] | None = None,
) -> None:
    _write_file(
        filename,
        dt,
        channels,
        write_options=write_options,
        source_headers=source_headers,
        extra_headers=extra_headers,
    )


def _write_file(
    filename: str,
    dt: float,
    channels: list[Channel],
    write_options: RPC3WriteOptions | None = None,
    source_headers: Mapping[str, Any] | None = None,
    extra_headers: Mapping[str, Any] | None = None,
) -> None:
    if not channels:
        raise ValueError("At least one channel is required to write an RPC3 file.")
    if dt <= 0:
        raise ValueError("dt must be positive.")

    source_options = make_write_options_from_headers(source_headers)
    options = write_options or source_options
    options.extra_headers = {**source_options.extra_headers, **options.extra_headers}
    if extra_headers:
        options.extra_headers = {**options.extra_headers, **dict(extra_headers)}
    options.extra_headers = _apply_time_history_defaults(options.extra_headers, channels)
    options.validate()

    max_chan_len = max(len(channel.values) for channel in channels)
    if max_chan_len == 0:
        raise ValueError("Cannot write an RPC3 file with empty channel data.")

    frames = math.ceil(max_chan_len / options.pts_per_frame)
    group_count = math.ceil(frames / options.frames_per_group)
    total_points = group_count * options.pts_per_group

    payloads: list[np.ndarray] = []
    scales: list[float] = []
    storage_dtype = _get_storage_dtype(options.format_type, options.data_type)
    for index, channel in enumerate(channels, start=1):
        values = np.asarray(channel.values)
        if options.data_type == "SHORT_INTEGER":
            preferred_scale = _preferred_input_scale(source_headers, index)
            normalized, scale = encode_short_integer_channel(
                values,
                int_full_scale=options.int_full_scale,
                preferred_scale=preferred_scale,
            )
            padded = np.zeros(total_points, dtype=np.int16)
            padded[: normalized.size] = normalized
            scales.append(scale)
        else:
            padded = np.zeros(total_points, dtype=np.float32)
            padded[: values.size] = values.astype(np.float32, copy=False)
            scales.append(1.0)
        payloads.append(padded.astype(storage_dtype, copy=False))

    header_bytes = _write_header(
        dt=dt,
        channels=channels,
        channel_scales=scales,
        frames=frames,
        write_options=options,
    )
    data_bytes = _write_data(payloads, options.pts_per_group)

    with open(filename, "wb") as file_handle:
        file_handle.write(header_bytes)
        file_handle.write(data_bytes)


def _write_header(
    dt: float,
    channels: list[Channel],
    channel_scales: list[float],
    frames: int,
    write_options: RPC3WriteOptions,
) -> bytes:
    created_at = write_options.date or _default_header_date(datetime.now())
    records: list[tuple[str, str]] = [
        ("FORMAT", write_options.format_type),
        ("NUM_HEADER_BLOCKS", "0"),
        ("NUM_PARAMS", "0"),
        ("FILE_TYPE", write_options.file_type),
        ("DATA_TYPE", write_options.data_type),
        ("TIME_TYPE", write_options.time_type),
        ("DELTA_T", _format_float(dt)),
        ("PTS_PER_FRAME", str(write_options.pts_per_frame)),
        ("PTS_PER_GROUP", str(write_options.pts_per_group)),
        ("CHANNELS", str(len(channels))),
        ("FRAMES", str(frames)),
        ("HALF_FRAMES", str(write_options.half_frames)),
        ("REPEATS", str(write_options.repeats)),
        ("INT_FULL_SCALE", str(write_options.int_full_scale)),
        ("DATE", created_at),
        ("OPERATION", write_options.operation),
    ]

    for index, channel in enumerate(channels, start=1):
        records.extend(
            [
                (f"DESC.CHAN_{index}", channel.name),
                (f"UNITS.CHAN_{index}", channel.units),
                (f"SCALE.CHAN_{index}", _format_float(channel_scales[index - 1])),
                (f"LOWER_LIMIT.CHAN_{index}", _format_float(write_options.lower_limit)),
                (f"UPPER_LIMIT.CHAN_{index}", _format_float(write_options.upper_limit)),
            ]
        )

    for key, value in write_options.extra_headers.items():
        if key in STANDARD_HEADER_KEYS:
            continue
        if any(key.startswith(prefix) for prefix in GENERATED_CHANNEL_PREFIXES):
            continue
        records.append((key, str(value)))

    num_params = len(records)
    num_header_blocks = math.ceil(num_params / 4)
    records[1] = ("NUM_HEADER_BLOCKS", str(num_header_blocks))
    records[2] = ("NUM_PARAMS", str(num_params))

    header_bytes = bytearray()
    for key, value in records:
        header_bytes.extend(_encode_header_field(key, 32))
        header_bytes.extend(_encode_header_field(value, 96))

    header_bytes.extend(b"\x00" * (512 * num_header_blocks - len(header_bytes)))
    return bytes(header_bytes)


def _write_data(data: list[np.ndarray], pts_per_group: int) -> bytes:
    group_count = len(data[0]) // pts_per_group
    data_bytes = bytearray()
    for group_index in range(group_count):
        start = group_index * pts_per_group
        end = start + pts_per_group
        for channel_data in data:
            data_bytes.extend(channel_data[start:end].tobytes())
    return bytes(data_bytes)


def encode_short_integer_channel(
    values: np.ndarray,
    int_full_scale: int,
    preferred_scale: float | None = None,
) -> tuple[np.ndarray, float]:
    if preferred_scale is not None and preferred_scale > 0:
        normalized = np.rint(np.asarray(values, dtype=np.float64) / preferred_scale)
        lower_bound, upper_bound = _int_bounds(int_full_scale)
        if normalized.size == 0 or (
            np.all(normalized >= lower_bound) and np.all(normalized <= upper_bound)
        ):
            return normalized.astype(np.int16), float(preferred_scale)

    return normalize_int16(values, int_full_scale=int_full_scale)


def _preferred_input_scale(
    source_headers: Mapping[str, Any] | None,
    channel_index: int,
) -> float | None:
    if not source_headers:
        return None
    key = f"SCALE.CHAN_{channel_index}"
    if key not in source_headers:
        return None
    try:
        scale = float(source_headers[key])
    except (TypeError, ValueError):
        return None
    return scale if scale > 0 else None


def _get_storage_dtype(format_type: str, data_type: str) -> np.dtype:
    little_endian = _is_little_endian_format(format_type)
    if data_type == "SHORT_INTEGER":
        return np.dtype("<i2" if little_endian else ">i2")
    return np.dtype("<f4" if little_endian else ">f4")


def _int_bounds(int_full_scale: int) -> tuple[int, int]:
    max_int16 = np.iinfo(np.int16).max
    min_int16 = np.iinfo(np.int16).min
    upper_bound = min(int_full_scale, max_int16)
    lower_bound = max(-int_full_scale, min_int16)
    return lower_bound, upper_bound


def _apply_time_history_defaults(
    extra_headers: Mapping[str, Any],
    channels: list[Channel],
) -> dict[str, Any]:
    defaults = dict(extra_headers)
    defaults.setdefault("BYPASS_FILTER", 0)
    defaults.setdefault("PARTITIONS", 1)
    defaults.setdefault("PART.CHAN_1", 1)
    defaults.setdefault("PART.NCHAN_1", len(channels))
    for index, channel in enumerate(channels, start=1):
        defaults.setdefault(f"MAP.CHAN_{index}", channel.number or index)
    return defaults


def _encode_header_field(value: str, width: int) -> bytes:
    encoded = str(value).encode("windows-1252", "replace")
    if len(encoded) > width:
        raise ValueError(f"Header value is too long for a {width}-byte field: {value!r}")
    return encoded.ljust(width, b"\x00")


def _default_header_date(current_time: datetime) -> str:
    return (
        f"{current_time.hour}:{current_time.minute}:{current_time.second} "
        f"{current_time.day}-{current_time.month}-{current_time.year}"
    )


def _format_float(value: float) -> str:
    return f"{float(value):.6E}"
