import argparse
from pathlib import Path

from .RPC3 import RPC3
from .csvtorsp import file_to_rpc3
from .readtocsv import export_data_to_csv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert RPC3/RSP time-history files to CSV and back."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    to_csv = subparsers.add_parser("to-csv", help="Convert .rsp/.drv RPC3 data to CSV.")
    to_csv.add_argument("input", help="Input RPC3 file path.")
    to_csv.add_argument("-o", "--output", help="Output CSV path. Defaults to input stem + .csv.")
    to_csv.add_argument(
        "--channels",
        nargs="*",
        type=int,
        help="Optional 1-based channel numbers to export.",
    )
    to_csv.add_argument("--overwrite", action="store_true", help="Overwrite the output file.")
    to_csv.add_argument(
        "--float-format",
        help="Python format specifier used for time and signal values, for example '.10f'.",
    )
    to_csv.add_argument(
        "--metadata-output",
        help="Optional output path for the generated .rpc3meta.json sidecar.",
    )
    to_csv.add_argument(
        "--no-metadata",
        action="store_true",
        help="Do not write the .rpc3meta.json sidecar.",
    )

    to_rsp = subparsers.add_parser("to-rsp", help="Convert CSV/XLSX data to an RPC3 .rsp file.")
    to_rsp.add_argument("input", help="Input CSV or XLSX file path.")
    to_rsp.add_argument("-o", "--output", help="Output RSP path. Defaults to input stem + .rsp.")
    to_rsp.add_argument("--dt", type=float, help="Sampling interval to use for the output file.")
    to_rsp.add_argument(
        "--metadata",
        help="Optional .rpc3meta.json file. If omitted, the tool looks for one next to the input CSV.",
    )
    to_rsp.add_argument(
        "--template-rsp",
        help="Fallback template/source RSP whose header metadata should be reused when no metadata sidecar is available.",
    )
    to_rsp.add_argument(
        "--pts-per-frame",
        type=int,
        default=None,
        help="RPC3 PTS_PER_FRAME value. Must be one of 256, 512, 1024, 2048.",
    )
    to_rsp.add_argument(
        "--frames-per-group",
        type=int,
        default=None,
        help="Power-of-two number of frames stored per channel group.",
    )
    to_rsp.add_argument(
        "--time-type",
        default=None,
        help="Optional RPC3 TIME_TYPE override, for example RESPONSE or DRIVE.",
    )
    to_rsp.add_argument(
        "--operation",
        default=None,
        help="Optional RPC3 OPERATION header override.",
    )
    to_rsp.add_argument(
        "--format-type",
        default=None,
        help="Optional RPC3 FORMAT override, for example BINARY or BINARY_IEEE_LITTLE_END.",
    )
    to_rsp.add_argument(
        "--int-full-scale",
        type=int,
        default=None,
        help="Optional INT_FULL_SCALE override.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "to-csv":
        input_path = Path(args.input)
        output_path = Path(args.output) if args.output else input_path.with_suffix(".csv")
        read_channels = [channel_number - 1 for channel_number in args.channels] if args.channels else None
        rpc3_obj = RPC3(str(input_path), read_channels=read_channels)
        if rpc3_obj.get_errors():
            raise SystemExit("; ".join(rpc3_obj.get_errors()))
        export_data_to_csv(
            rpc3_obj=rpc3_obj,
            output_file=output_path,
            overwrite=args.overwrite,
            float_format=args.float_format,
            write_metadata=not args.no_metadata,
            metadata_file=args.metadata_output,
        )
        print(output_path)
        return 0

    if args.command == "to-rsp":
        input_path = Path(args.input)
        output_path = Path(args.output) if args.output else input_path.with_suffix(".rsp")
        write_option_overrides = {}
        for arg_name, option_key in (
            ("pts_per_frame", "pts_per_frame"),
            ("frames_per_group", "frames_per_group"),
            ("time_type", "time_type"),
            ("operation", "operation"),
            ("format_type", "format_type"),
            ("int_full_scale", "int_full_scale"),
        ):
            value = getattr(args, arg_name)
            if value is not None:
                write_option_overrides[option_key] = value

        file_to_rpc3(
            input_file_path=input_path,
            output_rsp_file_path=output_path,
            dt=args.dt,
            metadata_path=args.metadata,
            template_rsp_path=args.template_rsp,
            write_option_overrides=write_option_overrides or None,
        )
        print(output_path)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
