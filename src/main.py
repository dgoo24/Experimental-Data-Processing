"""Command-line entry point.

Examples
--------
    python -m src.main init-db
    python -m src.main process
    python -m src.main process --skip-db
    python -m src.main history --experiment EXP-001
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from .analysis import analyze_measurements
from .cleaning import export_processed_measurements, select_valid_measurements
from .config import (
    DATA_PROCESSED_DIR,
    DATA_RAW_DIR,
    DEFAULT_DATABASE_URL,
    OUTPUT_DIR,
)
from .database import (
    check_connection,
    database_summary,
    fetch_import_history,
    fetch_measurements,
    fetch_regression_results,
    get_engine,
    init_db,
    persist_dataset,
    store_regression_results,
)
from .ingestion import CSVFormatError, load_input_files
from .reports import generate_reports
from .validation import ValidationConfig, build_quality_report, validate_measurements


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="experimental-data-tool",
        description="Process, validate, store and analyze optical polarization measurements.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init-db", help="Create the database tables.")
    init_parser.add_argument(
        "--database-url",
        default=DEFAULT_DATABASE_URL,
        help="SQLAlchemy database URL (default: DATABASE_URL or local Docker database).",
    )

    process_parser = subparsers.add_parser(
        "process",
        help="Validate CSV files, store measurements, run regressions and write reports.",
    )
    process_parser.add_argument(
        "--input",
        type=Path,
        default=DATA_RAW_DIR,
        help=f"Directory containing input CSV files (default: {DATA_RAW_DIR}).",
    )
    process_parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_DIR,
        help=f"Directory for plots and reports (default: {OUTPUT_DIR}).",
    )
    process_parser.add_argument(
        "--processed-dir",
        type=Path,
        default=DATA_PROCESSED_DIR,
        help=f"Directory for the cleaned measurement CSV (default: {DATA_PROCESSED_DIR}).",
    )
    process_parser.add_argument(
        "--database-url",
        default=DEFAULT_DATABASE_URL,
        help="SQLAlchemy database URL (default: DATABASE_URL or local Docker database).",
    )
    process_parser.add_argument(
        "--skip-db",
        action="store_true",
        help="Run validation and reports without connecting to PostgreSQL.",
    )
    defaults = ValidationConfig()
    process_parser.add_argument(
        "--angle-min",
        type=float,
        default=defaults.angle_min,
        help=f"Minimum accepted measurement angle in degrees (default: {defaults.angle_min:g}).",
    )
    process_parser.add_argument(
        "--angle-max",
        type=float,
        default=defaults.angle_max,
        help=f"Maximum accepted measurement angle in degrees (default: {defaults.angle_max:g}).",
    )
    process_parser.add_argument(
        "--rotation-min",
        type=float,
        default=defaults.rotation_min,
        help=f"Minimum accepted observed rotation in degrees (default: {defaults.rotation_min:g}).",
    )
    process_parser.add_argument(
        "--rotation-max",
        type=float,
        default=defaults.rotation_max,
        help=f"Maximum accepted observed rotation in degrees (default: {defaults.rotation_max:g}).",
    )
    process_parser.add_argument(
        "--max-id-length",
        type=int,
        default=defaults.max_id_length,
        help=f"Maximum experiment/sample identifier length (default: {defaults.max_id_length}).",
    )

    history_parser = subparsers.add_parser(
        "history",
        help="Show stored measurement/regression history.",
    )
    history_parser.add_argument(
        "--database-url",
        default=DEFAULT_DATABASE_URL,
        help="SQLAlchemy database URL (default: DATABASE_URL or local Docker database).",
    )
    history_parser.add_argument(
        "--experiment",
        default=None,
        help="Restrict measurement and regression output to one experiment_id.",
    )

    return parser


def _print_summary(
    sources,
    validated: pd.DataFrame,
    processed: pd.DataFrame,
    bundle,
    outcomes,
    artifacts,
    db_error: str | None,
) -> None:
    quality = build_quality_report(validated)

    print("")
    print("Run summary")
    print("-----------")
    print(f"Input files: {len(sources)}")
    print(f"Input rows: {len(validated)}")
    print(f"Valid measurements: {len(processed)}")
    print(f"Rejected rows: {int(validated['status'].ne('valid').sum())}")
    print("")
    print("Data quality by source file")
    print(quality.to_string(index=False))
    print("")

    if not bundle.regressions.empty:
        print("Regression results")
        print(bundle.regressions.to_string(index=False))
        print("")
    elif not processed.empty:
        print("No regressions could be computed (each group needs >= 2 points).")
        print("")

    if bundle.skipped:
        print("Skipped analysis groups")
        print(pd.DataFrame(bundle.skipped).to_string(index=False))
        print("")

    if outcomes:
        print("Database imports")
        print(
            pd.DataFrame([outcome.__dict__ for outcome in outcomes]).to_string(index=False)
        )
        print("")

    if db_error:
        print(f"DATABASE ERROR: {db_error}")
        print("Reports were still written locally. Use --skip-db for offline runs.")
        print("")

    print("Generated files")
    for path in sorted(set(artifacts.values())):
        print(f"  {path}")


def _run_process(args: argparse.Namespace) -> int:
    try:
        config = ValidationConfig(
            angle_min=args.angle_min,
            angle_max=args.angle_max,
            rotation_min=args.rotation_min,
            rotation_max=args.rotation_max,
            max_id_length=args.max_id_length,
        )
    except ValueError as exc:
        print(f"CONFIG ERROR: {exc}")
        return 2

    try:
        raw, sources = load_input_files(args.input)
    except (FileNotFoundError, NotADirectoryError, CSVFormatError) as exc:
        print(f"INPUT ERROR: {exc}")
        return 1

    try:
        validated = validate_measurements(raw, config=config)
    except ValueError as exc:
        print(f"VALIDATION ERROR: {exc}")
        return 1

    processed = select_valid_measurements(validated)
    processed_path = export_processed_measurements(
        processed, args.processed_dir / "processed_measurements.csv"
    )

    bundle = analyze_measurements(processed)

    outcomes = None
    db_error = None
    if not args.skip_db:
        try:
            engine = get_engine(args.database_url)
            check_connection(engine)
            init_db(engine)
            outcomes = persist_dataset(engine, validated, sources)
            regression_store = store_regression_results(engine, bundle.regressions)
            if regression_store.skipped:
                print("WARNING: some regressions could not be stored:")
                print(pd.DataFrame(regression_store.skipped).to_string(index=False))
        except Exception as exc:  # noqa: BLE001 - CLI boundary
            db_error = str(exc)

    artifacts = generate_reports(
        processed=processed,
        validated=validated,
        bundle=bundle,
        output_dir=args.output,
        import_outcomes=outcomes,
    )
    artifacts["processed_measurements"] = processed_path

    _print_summary(
        sources,
        validated,
        processed,
        bundle,
        outcomes,
        artifacts,
        db_error,
    )
    return 1 if db_error else 0


def _run_init_db(args: argparse.Namespace) -> int:
    try:
        engine = get_engine(args.database_url)
        check_connection(engine)
        init_db(engine)
        summary = database_summary(engine)
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(f"DATABASE ERROR: {exc}")
        print("Start PostgreSQL with: docker compose up -d db")
        return 1

    print("Database initialized.")
    print(summary)
    return 0


def _run_history(args: argparse.Namespace) -> int:
    try:
        engine = get_engine(args.database_url)
        check_connection(engine)
        summary = database_summary(engine)
        regressions = fetch_regression_results(engine, args.experiment)
        measurements = fetch_measurements(engine, args.experiment)
        imports = fetch_import_history(engine)
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        print(f"DATABASE ERROR: {exc}")
        return 1

    print("Database summary")
    print(summary)
    print("")

    if measurements.empty:
        print("No processed measurements stored.")
    else:
        counts = (
            measurements.groupby(["experiment_id", "sample_id"], sort=True)
            .size()
            .rename("measurements")
            .reset_index()
        )
        print("Stored measurements")
        print(counts.to_string(index=False))
        print("")

    print("Stored regression results")
    if regressions.empty:
        print("None.")
    else:
        print(regressions.to_string(index=False))
    print("")

    print("Import history")
    if imports.empty:
        print("None.")
    else:
        print(imports.to_string(index=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    pd.set_option("display.max_columns", 50)
    pd.set_option("display.width", 200)

    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "init-db":
        return _run_init_db(args)
    if args.command == "process":
        return _run_process(args)
    if args.command == "history":
        return _run_history(args)

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
