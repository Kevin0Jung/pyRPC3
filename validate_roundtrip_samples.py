import argparse
import json
import math
from pathlib import Path

import numpy as np

from src.RPC3 import RPC3
from src.csvtorsp import csv_to_rpc3, read_csv_file
from src.readtocsv import export_data_to_csv

ROOT = Path(__file__).resolve().parent
SAMPLE_DIR = ROOT / "sample_rsp_files"
DEFAULT_OUTPUT_ROOT = ROOT / "output" / "roundtrip_validation"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate RPC3 sample roundtrips in two phases: rsp->csv and csv->rsp."
    )
    parser.add_argument(
        "phase",
        choices=("csv-only", "rsp-only", "full"),
        help="Run only rsp->csv, only csv->rsp, or both phases.",
    )
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_OUTPUT_ROOT),
        help="Directory used for generated CSV/RSP files and summary reports.",
    )
    parser.add_argument(
        "--samples",
        nargs="*",
        help="Optional specific sample file names under sample_rsp_files. Defaults to all .rsp files there.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    sample_paths = resolve_sample_paths(args.samples)
    if not sample_paths:
        raise SystemExit(f"No .rsp sample files found in {SAMPLE_DIR}")

    summary: dict[str, object] = {
        "phase": args.phase,
        "output_root": str(output_root),
        "samples": [],
    }

    for sample_path in sample_paths:
        sample_report: dict[str, object] = {
            "sample": sample_path.name,
            "source_rsp": str(sample_path),
        }
        sample_output_dir = output_root / sample_path.stem
        sample_output_dir.mkdir(parents=True, exist_ok=True)
        csv_path = sample_output_dir / f"{sample_path.stem}.csv"
        rsp_path = sample_output_dir / f"{sample_path.stem}_roundtrip.rsp"

        if args.phase in {"csv-only", "full"}:
            csv_report = run_csv_phase(sample_path, csv_path)
            sample_report["csv_phase"] = csv_report
            print_csv_phase(csv_report)

        if args.phase in {"rsp-only", "full"}:
            rsp_report = run_rsp_phase(sample_path, csv_path, rsp_path)
            sample_report["rsp_phase"] = rsp_report
            print_rsp_phase(rsp_report)

        summary["samples"].append(sample_report)

    write_summary_files(summary, output_root)
    print(f"\nSummary written to: {output_root}")
    return 0


def resolve_sample_paths(sample_names: list[str] | None) -> list[Path]:
    if sample_names:
        paths = [SAMPLE_DIR / name for name in sample_names]
    else:
        paths = sorted(SAMPLE_DIR.glob("*.rsp"))
    return [path for path in paths if path.is_file()]


def run_csv_phase(sample_path: Path, csv_path: Path) -> dict[str, object]:
    rpc = load_rpc(sample_path)
    export_data_to_csv(rpc, csv_path, overwrite=True)

    time, channel_data, names, units, csv_dt = read_csv_file(csv_path)
    original_names = [channel.name for channel in rpc.channels]
    original_units = [channel.units for channel in rpc.channels]
    original_matrix = np.vstack([channel.values for channel in rpc.channels]).T
    csv_matrix = np.vstack(channel_data).T

    max_abs_diff = float(np.max(np.abs(original_matrix - csv_matrix)))
    mean_abs_diff = float(np.mean(np.abs(original_matrix - csv_matrix)))

    return {
        "status": "ok",
        "csv_path": str(csv_path),
        "rows": int(time.shape[0]),
        "channels": len(names),
        "dt_original": float(rpc.dt),
        "dt_csv": float(csv_dt),
        "dt_match": bool(math.isclose(float(rpc.dt), float(csv_dt), rel_tol=1e-9, abs_tol=1e-12)),
        "names_match": names == original_names,
        "units_match": units == original_units,
        "max_abs_diff": max_abs_diff,
        "mean_abs_diff": mean_abs_diff,
        "time_start": float(time[0]),
        "time_end": float(time[-1]),
    }


def run_rsp_phase(sample_path: Path, csv_path: Path, rsp_path: Path) -> dict[str, object]:
    if not csv_path.is_file():
        raise FileNotFoundError(
            f"CSV phase output is missing for {sample_path.name}: {csv_path}"
        )

    regenerated_rsp = csv_to_rpc3(csv_path, rsp_path)
    original = load_rpc(sample_path)
    roundtrip = load_rpc(regenerated_rsp)

    original_matrix = np.vstack([channel.values for channel in original.channels]).T
    roundtrip_matrix = np.vstack([channel.values for channel in roundtrip.channels]).T
    max_abs_diff = float(np.max(np.abs(original_matrix - roundtrip_matrix)))
    rmse = float(np.sqrt(np.mean((original_matrix - roundtrip_matrix) ** 2)))

    return {
        "status": "ok",
        "csv_path": str(csv_path),
        "roundtrip_rsp_path": str(regenerated_rsp),
        "sample_count_match": int(original.sample_count) == int(roundtrip.sample_count),
        "channel_count_match": len(original.channels) == len(roundtrip.channels),
        "dt_original": float(original.dt),
        "dt_roundtrip": float(roundtrip.dt),
        "dt_match": bool(
            math.isclose(float(original.dt), float(roundtrip.dt), rel_tol=1e-9, abs_tol=1e-12)
        ),
        "max_abs_diff": max_abs_diff,
        "rmse": rmse,
        "headers_roundtrip": {
            key: roundtrip.headers.get(key)
            for key in ("CHANNELS", "DELTA_T", "PTS_PER_FRAME", "PTS_PER_GROUP", "FRAMES", "DATA_TYPE")
        },
    }


def load_rpc(path: Path) -> RPC3:
    rpc = RPC3(str(path))
    if rpc.get_errors():
        raise ValueError(f"Failed to read {path}: {'; '.join(rpc.get_errors())}")
    return rpc


def print_csv_phase(report: dict[str, object]) -> None:
    print(
        "[csv] {path} | rows={rows} channels={channels} dt_match={dt_match} "
        "names_match={names_match} units_match={units_match} max_abs_diff={max_abs_diff:.3e}".format(
            path=report["csv_path"],
            rows=report["rows"],
            channels=report["channels"],
            dt_match=report["dt_match"],
            names_match=report["names_match"],
            units_match=report["units_match"],
            max_abs_diff=float(report["max_abs_diff"]),
        )
    )


def print_rsp_phase(report: dict[str, object]) -> None:
    print(
        "[rsp] {path} | dt_match={dt_match} sample_count_match={sample_count_match} "
        "channel_count_match={channel_count_match} max_abs_diff={max_abs_diff:.3e} rmse={rmse:.3e}".format(
            path=report["roundtrip_rsp_path"],
            dt_match=report["dt_match"],
            sample_count_match=report["sample_count_match"],
            channel_count_match=report["channel_count_match"],
            max_abs_diff=float(report["max_abs_diff"]),
            rmse=float(report["rmse"]),
        )
    )


def write_summary_files(summary: dict[str, object], output_root: Path) -> None:
    json_path = output_root / "summary.json"
    md_path = output_root / "summary.md"

    with json_path.open("w", encoding="utf-8") as file_handle:
        json.dump(summary, file_handle, ensure_ascii=False, indent=2)

    with md_path.open("w", encoding="utf-8") as file_handle:
        file_handle.write(render_markdown(summary))


def render_markdown(summary: dict[str, object]) -> str:
    lines = [
        "# Roundtrip Validation Summary",
        "",
        f"- Phase: `{summary['phase']}`",
        f"- Output root: `{summary['output_root']}`",
        "",
    ]

    for sample in summary["samples"]:
        sample_name = sample["sample"]
        lines.append(f"## {sample_name}")
        lines.append("")
        lines.append(f"- Source RSP: `{sample['source_rsp']}`")

        csv_phase = sample.get("csv_phase")
        if csv_phase:
            lines.append(f"- CSV output: `{csv_phase['csv_path']}`")
            lines.append(f"- CSV rows/channels: `{csv_phase['rows']}` / `{csv_phase['channels']}`")
            lines.append(
                "- CSV checks: "
                f"dt_match=`{csv_phase['dt_match']}`, "
                f"names_match=`{csv_phase['names_match']}`, "
                f"units_match=`{csv_phase['units_match']}`, "
                f"max_abs_diff=`{float(csv_phase['max_abs_diff']):.3e}`"
            )

        rsp_phase = sample.get("rsp_phase")
        if rsp_phase:
            lines.append(f"- Roundtrip RSP output: `{rsp_phase['roundtrip_rsp_path']}`")
            lines.append(
                "- Roundtrip checks: "
                f"dt_match=`{rsp_phase['dt_match']}`, "
                f"sample_count_match=`{rsp_phase['sample_count_match']}`, "
                f"channel_count_match=`{rsp_phase['channel_count_match']}`, "
                f"max_abs_diff=`{float(rsp_phase['max_abs_diff']):.3e}`, "
                f"rmse=`{float(rsp_phase['rmse']):.3e}`"
            )
            lines.append(f"- Roundtrip headers: `{rsp_phase['headers_roundtrip']}`")

        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
