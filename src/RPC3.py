import math
import os
import struct
import sys
from io import BufferedReader
from typing import Any

import numpy as np

from .Channel import Channel
from .writter import RPC3WriteOptions, make_write_options_from_headers, write_rpc3

DATA_TYPES = {
    "FLOATING_POINT": {"numpy_dtype": "f4", "bytes": 4},
    "SHORT_INTEGER": {"numpy_dtype": "i2", "bytes": 2},
}


class RPC3:
    """
    Reader/writer for RPC3 time-history files.
    """

    def __init__(
        self,
        filename: str = "",
        debug: bool = False,
        extra_headers: dict[str, Any] | None = None,
        read_channels: list[int] | None = None,
    ) -> None:
        self.filename = filename
        self.debug = debug
        self.headers: dict[str, Any] = {}
        self.channels: list[Channel] = []
        self.errors: list[str] = []
        self._extra_headers = {
            "INT_FULL_SCALE": 32768,
            "DATA_TYPE": "SHORT_INTEGER",
            **(extra_headers or {}),
        }
        self.dt = 0.0
        self._channels_to_read = read_channels
        self._file_size = 0
        self._data_type = self._extra_headers["DATA_TYPE"]

        if self.filename:
            self._read_file()

    @classmethod
    def from_channels(
        cls,
        filename: str,
        dt: float,
        channels: list[Channel],
        headers: dict[str, Any] | None = None,
        debug: bool = False,
    ) -> "RPC3":
        rpc3 = cls(filename="", debug=debug, extra_headers=headers)
        rpc3.filename = filename
        rpc3.dt = float(dt)
        rpc3.headers = dict(headers or {})
        rpc3.channels = [channel.copy() for channel in channels]
        return rpc3

    @property
    def sample_count(self) -> int:
        if not self.channels:
            return 0
        return len(self.channels[0].values)

    def info(self) -> None:
        print("\n" + "=" * 90)
        sys.stdout.write(
            "{:<15s} {:<30s} {:<15s} {:<15s} {:<15s}\n".format(
                "Channel", "Name", "Units", "Min", "Max"
            )
        )
        print("-" * 90)
        for channel in sorted(self.channels, key=lambda item: item.number):
            sys.stdout.write(
                "{:<15s} {:<30s} {:<15s} {:<15.3e} {:<15.3e}\n".format(
                    str(channel.number),
                    channel.name,
                    channel.units,
                    channel.get_min(),
                    channel.get_max(),
                )
            )
        print("=" * 90 + "\n")

    def save(
        self,
        filename: str,
        exclude_channels: list[int | str] | None = None,
        write_options: RPC3WriteOptions | None = None,
        extra_headers: dict[str, Any] | None = None,
    ) -> None:
        if self.dt <= 0:
            raise ValueError("dt must be positive before saving.")

        if exclude_channels is None:
            channels_to_write = self.channels
        else:
            def is_excluded(channel: Channel) -> bool:
                for excluded in exclude_channels:
                    if isinstance(excluded, int) and channel.number == excluded:
                        return True
                    if isinstance(excluded, str) and channel.name == excluded:
                        return True
                return False

            channels_to_write = [channel for channel in self.channels if not is_excluded(channel)]

        if not channels_to_write:
            raise ValueError("No channels remain after applying the exclusion filter.")

        resolved_write_options = write_options or make_write_options_from_headers(self.headers)
        write_rpc3(
            filename=filename,
            dt=self.dt,
            channels=channels_to_write,
            write_options=resolved_write_options,
            source_headers=self.headers,
            extra_headers=extra_headers,
        )

    def get_errors(self) -> list[str]:
        return self.errors

    def _read_file(self) -> bool:
        if not os.path.isfile(self.filename):
            self.errors.append(f"File not found: {self.filename}")
            return False

        with open(self.filename, "rb") as file_handle:
            file_handle.seek(0, os.SEEK_END)
            self._file_size = file_handle.tell()
            file_handle.seek(0, 0)

            if not self._read_header(file_handle):
                return False
            return self._read_data(file_handle)

    def _read_header(self, file_handle: BufferedReader) -> bool:
        def read_header_entry() -> tuple[str | None, str | None]:
            raw = file_handle.read(128)
            if len(raw) != 128:
                self.errors.append("Header does not contain a full 128-byte record.")
                return None, None

            try:
                head_bytes, value_bytes = struct.unpack("<32s96s", raw)
                value = (
                    value_bytes.replace(b"\0", b"")
                    .decode("windows-1252", "ignore")
                    .replace("\n", "")
                    .strip()
                )
                head = (
                    head_bytes.replace(b"\0", b"")
                    .decode("windows-1252", "ignore")
                    .replace("\n", "")
                    .strip()
                )
                return head, value
            except struct.error:
                self.errors.append("Header unpack failed.")
                return None, None

        for expected_name in ("FORMAT", "NUM_HEADER_BLOCKS", "NUM_PARAMS"):
            head_name, head_value = read_header_entry()
            if head_name != expected_name or head_value is None:
                self.errors.append("Header is missing the required first three records.")
                return False

            self.headers[head_name] = (
                int(head_value) if head_name in {"NUM_HEADER_BLOCKS", "NUM_PARAMS"} else head_value
            )
            if self.debug:
                print(f"{head_name:18s}: {self.headers[head_name]}")

        if int(self.headers["NUM_PARAMS"]) <= 3:
            self.errors.append("The file does not contain channel metadata.")
            return False

        for _ in range(3, int(self.headers["NUM_PARAMS"])):
            head_name, head_value = read_header_entry()
            if head_name:
                self.headers[head_name] = head_value
                if self.debug:
                    print(f"{head_name:32s}: {head_value}")

        for header_name, header_value in self._extra_headers.items():
            self.headers.setdefault(header_name, header_value)

        try:
            self.headers["NUM_HEADER_BLOCKS"] = int(self.headers["NUM_HEADER_BLOCKS"])
            self.headers["CHANNELS"] = int(self.headers["CHANNELS"])
            self.headers["DELTA_T"] = float(self.headers["DELTA_T"])
            self.headers["PTS_PER_FRAME"] = int(self.headers["PTS_PER_FRAME"])
            self.headers["PTS_PER_GROUP"] = int(self.headers["PTS_PER_GROUP"])
            self.headers["FRAMES"] = int(self.headers["FRAMES"])
            self.headers["INT_FULL_SCALE"] = int(self.headers["INT_FULL_SCALE"])
            self.headers["HALF_FRAMES"] = int(self.headers.get("HALF_FRAMES", 0))
            self.headers["REPEATS"] = int(self.headers.get("REPEATS", 0))
        except KeyError as missing_header:
            self.errors.append(f"Missing required header: {missing_header}")
            return False
        except ValueError as invalid_header:
            self.errors.append(f"Header conversion failed: {invalid_header}")
            return False

        self._data_type = str(self.headers["DATA_TYPE"])
        if self._data_type not in DATA_TYPES:
            self.errors.append(f"Unsupported DATA_TYPE: {self._data_type}")
            return False

        self.dt = float(self.headers["DELTA_T"])
        self.channels = []
        for index in range(self.headers["CHANNELS"]):
            scale = 1.0
            if self._data_type == "SHORT_INTEGER":
                scale = float(self.headers.get(f"SCALE.CHAN_{index + 1}", 1.0))
            self.channels.append(
                Channel(
                    index + 1,
                    self.headers.get(f"DESC.CHAN_{index + 1}", f"Channel {index + 1}"),
                    self.headers.get(f"UNITS.CHAN_{index + 1}", ""),
                    self.dt,
                    scale,
                )
            )

        return True

    def _read_data(self, file_handle: BufferedReader) -> bool:
        channels = self.headers["CHANNELS"]
        pts_per_frame = self.headers["PTS_PER_FRAME"]
        pts_per_group = self.headers["PTS_PER_GROUP"]
        frames = self.headers["FRAMES"]

        if pts_per_frame <= 0 or pts_per_group <= 0:
            self.errors.append("PTS_PER_FRAME and PTS_PER_GROUP must be positive.")
            return False
        if pts_per_group % pts_per_frame != 0:
            self.errors.append("PTS_PER_GROUP must be an integer multiple of PTS_PER_FRAME.")
            return False
        if self.headers.get("HALF_FRAMES", 0) != 0:
            self.errors.append("HALF_FRAMES files are not supported by this reader.")
            return False

        frames_per_group = pts_per_group // pts_per_frame
        if frames_per_group <= 0:
            self.errors.append("Derived frames_per_group is invalid.")
            return False

        number_of_groups = int(math.ceil(frames / frames_per_group))
        data_info = DATA_TYPES[self._data_type]
        data_type_bytes = data_info["bytes"]
        file_offset = self.headers["NUM_HEADER_BLOCKS"] * 512
        actual_data_size = self._file_size - file_offset
        full_group_expected_size = pts_per_group * data_type_bytes * number_of_groups * channels
        unpadded_expected_size = frames * pts_per_frame * data_type_bytes * channels

        if actual_data_size == full_group_expected_size:
            pad_last_group = True
        elif actual_data_size == unpadded_expected_size:
            pad_last_group = False
        else:
            self.errors.append(
                "Data size does not match the header values. "
                f"actual={actual_data_size}, padded_expected={full_group_expected_size}, "
                f"unpadded_expected={unpadded_expected_size}"
            )
            return False

        format_name = str(self.headers.get("FORMAT", "BINARY"))
        if format_name == "ASCII":
            self.errors.append("ASCII RPC3 data is not supported.")
            return False

        endian_prefix = ">"
        if format_name in {"BINARY", "BINARY_IEEE_LITTLE_END"}:
            endian_prefix = "<"

        numpy_dtype = np.dtype(endian_prefix + data_info["numpy_dtype"])
        total_points = frames * pts_per_frame
        selected_indices = (
            set(range(channels)) if self._channels_to_read is None else set(self._channels_to_read)
        )

        for channel in self.channels:
            channel.values = np.zeros(total_points, dtype=np.float32)

        file_handle.seek(file_offset, 0)
        write_offset = 0
        remaining_frames = frames

        for group_index in range(number_of_groups):
            actual_group_frames = min(frames_per_group, remaining_frames)
            actual_points = actual_group_frames * pts_per_frame
            stored_points = pts_per_group
            if not pad_last_group and group_index == number_of_groups - 1:
                stored_points = actual_points
            stored_bytes = stored_points * data_type_bytes

            for channel_index in range(channels):
                if channel_index in selected_indices:
                    raw_bytes = file_handle.read(stored_bytes)
                    if len(raw_bytes) != stored_bytes:
                        self.errors.append("Unexpected end of file while reading channel data.")
                        return False

                    unpacked = np.frombuffer(raw_bytes, dtype=numpy_dtype)
                    values = unpacked[:actual_points].astype(np.float32, copy=False)
                    self.channels[channel_index].values[
                        write_offset : write_offset + actual_points
                    ] = values
                else:
                    file_handle.seek(stored_bytes, 1)

            write_offset += actual_points
            remaining_frames -= actual_group_frames

        if self._data_type == "SHORT_INTEGER":
            for channel_index in selected_indices:
                self.channels[channel_index]._apply_scale()

        if self._channels_to_read is not None:
            self.channels = [
                channel for index, channel in enumerate(self.channels) if index in selected_indices
            ]

        return True
