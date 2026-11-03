"""Data access helpers for the optional Streamlit dashboard.

This module contains no Streamlit imports on purpose.  Everything here is plain
pandas/SQLAlchemy so it can be unit-tested without starting a web server and
reused from scripts.

Two sources are supported:

* ``database`` - the PostgreSQL tables written by ``python -m src.main process``.
* ``files``    - the CSV artifacts under ``data/processed`` and ``output/reports``.

``auto`` tries PostgreSQL first and falls back to the local files, so the
dashboard still works when Docker is not running.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd

from .analysis import (
    AnalysisBundle,
    analyze_measurements,
    compare_experiments,
    descriptive_statistics,
)
from .config import (
    DATA_PROCESSED_DIR,
    DEFAULT_DATABASE_URL,
    DEMO_PROCESSED_PATH,
    DEMO_REPORTS_DIR,
    REPORTS_DIR,
)
from .database import (
    check_connection,
    fetch_import_history,
    fetch_measurements,
    fetch_quality_issues,
    fetch_regression_results,
    get_engine,
)

MEASUREMENT_COLUMNS = [
    "experiment_id",
    "sample_id",
    "measurement_angle",
    "observed_rotation",
    "measurement_timestamp",
]

REGRESSION_COLUMNS = [
    "experiment_id",
    "sample_id",
    "n_points",
    "slope",
    "intercept",
    "r_squared",
    "slope_std_error",
    "intercept_std_error",
    "residual_std_error",
]

RESIDUAL_COLUMNS = [
    "experiment_id",
    "sample_id",
    "measurement_angle",
    "observed_rotation",
    "predicted_rotation",
    "residual",
]

QUALITY_COLUMNS = [
    "source_file",
    "total_rows",
    "valid_rows",
    "invalid_rows",
    "duplicate_rows",
    "rejected_rows",
]

ISSUE_COLUMNS = [
    "source_file",
    "source_row",
    "status",
    "experiment_id",
    "sample_id",
    "measurement_angle",
    "observed_rotation",
    "measurement_timestamp",
    "validation_errors",
]

IMPORT_COLUMNS = [
    "source_file",
    "imported_at",
    "n_rows",
    "n_valid",
    "n_invalid",
    "n_duplicates",
]

SOURCE_AUTO = "auto"
SOURCE_DATABASE = "database"
SOURCE_FILES = "files"


@dataclass(frozen=True)
class DashboardData:
    """Everything the dashboard needs for one render."""

    measurements: pd.DataFrame
    regressions: pd.DataFrame
    descriptive: pd.DataFrame
    residuals: pd.DataFrame
    comparison: pd.DataFrame
    quality: pd.DataFrame
    issues: pd.DataFrame
    imports: pd.DataFrame
    source_label: str
    warning: str | None = None


def _empty(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def _combine_warnings(message: str, warning: str | None) -> str:
    return f"{message} {warning}" if warning else message


def _coerce_measurements(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return _empty(MEASUREMENT_COLUMNS)

    result = frame.copy()
    result["measurement_angle"] = pd.to_numeric(result["measurement_angle"], errors="coerce")
    result["observed_rotation"] = pd.to_numeric(
        result["observed_rotation"], errors="coerce"
    )
    result = result.dropna(subset=["measurement_angle", "observed_rotation"])
    return result.reset_index(drop=True)


def _coerce_regressions(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return _empty(REGRESSION_COLUMNS)

    result = frame.copy()
    for column in ("n_points", "slope", "intercept"):
        result[column] = pd.to_numeric(result[column], errors="coerce")
    for column in (
        "r_squared",
        "slope_std_error",
        "intercept_std_error",
        "residual_std_error",
    ):
        if column in result.columns:
            result[column] = pd.to_numeric(result[column], errors="coerce")
    return result.dropna(subset=["slope", "intercept"]).reset_index(drop=True)


def _analysis(measurements: pd.DataFrame, regressions: pd.DataFrame) -> AnalysisBundle:
    """Descriptive statistics and residuals for an already-loaded dataset."""
    descriptive = descriptive_statistics(measurements)
    if regressions.empty and not measurements.empty:
        regressions = analyze_measurements(measurements).regressions

    return AnalysisBundle(
        descriptive=descriptive,
        regressions=regressions,
        residuals=attach_residuals(measurements, regressions),
        comparison=compare_experiments(regressions),
    )


def attach_residuals(
    measurements: pd.DataFrame, regressions: pd.DataFrame
) -> pd.DataFrame:
    """Compute per-point residuals from stored/fitted slope and intercept."""
    if measurements.empty or regressions.empty:
        return _empty(RESIDUAL_COLUMNS)

    merged = measurements.merge(
        regressions[["experiment_id", "sample_id", "slope", "intercept"]],
        on=["experiment_id", "sample_id"],
        how="inner",
    )
    if merged.empty:
        return _empty(RESIDUAL_COLUMNS)

    merged["predicted_rotation"] = (
        merged["slope"] * merged["measurement_angle"] + merged["intercept"]
    )
    merged["residual"] = merged["observed_rotation"] - merged["predicted_rotation"]
    return merged[RESIDUAL_COLUMNS].reset_index(drop=True)


def quality_from_imports(imports: pd.DataFrame) -> pd.DataFrame:
    """Turn the ``imports`` table into a compact data-quality table."""
    if imports.empty:
        return _empty(QUALITY_COLUMNS)

    frame = pd.DataFrame(
        {
            "source_file": [
                Path(str(value)).name for value in imports["source_file"]
            ],
            "total_rows": imports["n_rows"].astype(int),
            "valid_rows": imports["n_valid"].astype(int),
            "invalid_rows": imports["n_invalid"].astype(int),
            "duplicate_rows": imports["n_duplicates"].astype(int),
        }
    )
    frame["rejected_rows"] = frame["invalid_rows"] + frame["duplicate_rows"]
    if len(frame) > 1:
        totals = frame.drop(columns=["source_file"]).sum()
        frame = pd.concat(
            [
                frame,
                pd.DataFrame(
                    [
                        {
                            "source_file": "ALL",
                            "total_rows": int(totals["total_rows"]),
                            "valid_rows": int(totals["valid_rows"]),
                            "invalid_rows": int(totals["invalid_rows"]),
                            "duplicate_rows": int(totals["duplicate_rows"]),
                            "rejected_rows": int(totals["rejected_rows"]),
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )
    return frame[QUALITY_COLUMNS]


def read_optional_csv(path: Path, columns: list[str] | None = None) -> pd.DataFrame:
    """Read a CSV if it exists, otherwise return an empty frame."""
    path = Path(path)
    if not path.is_file():
        return _empty(columns or [])
    frame = pd.read_csv(path)
    if columns is not None and frame.empty:
        return _empty(columns)
    return frame


def load_local(
    processed_path: Path | None = None,
    reports_dir: Path | None = None,
) -> DashboardData:
    """Load the artifacts written by the batch pipeline.

    If the default processed file does not exist yet (for example in a fresh
    Streamlit Community Cloud deployment), the bundled synthetic demo artifacts
    under ``data/demo`` are used instead.  Explicit paths never fall back, so
    tests and scripts still get a clear ``FileNotFoundError``.
    """
    explicit_processed = processed_path is not None
    explicit_reports = reports_dir is not None
    processed_path = Path(processed_path or DATA_PROCESSED_DIR / "processed_measurements.csv")
    reports_dir = Path(reports_dir or REPORTS_DIR)
    using_demo = False

    if not processed_path.is_file():
        if not explicit_processed and DEMO_PROCESSED_PATH.is_file():
            processed_path = DEMO_PROCESSED_PATH
            if not explicit_reports:
                reports_dir = DEMO_REPORTS_DIR
            using_demo = True
        else:
            raise FileNotFoundError(
                f"{processed_path} not found. Run 'python -m src.main process' first."
            )

    measurements = _coerce_measurements(pd.read_csv(processed_path))
    regressions = _coerce_regressions(
        read_optional_csv(reports_dir / "regression_results.csv", REGRESSION_COLUMNS)
    )
    bundle = _analysis(measurements, regressions)

    return DashboardData(
        measurements=measurements,
        regressions=bundle.regressions,
        descriptive=bundle.descriptive,
        residuals=bundle.residuals,
        comparison=bundle.comparison,
        quality=read_optional_csv(reports_dir / "data_quality_report.csv", QUALITY_COLUMNS),
        issues=read_optional_csv(reports_dir / "quality_issues.csv", ISSUE_COLUMNS),
        imports=_empty(IMPORT_COLUMNS),
        source_label="Lokale Dateien",
        warning=(
            "Es werden die mitgelieferten synthetischen Demo-Daten angezeigt. "
            "Für eigene Daten `python -m src.main process` ausführen."
            if using_demo
            else None
        ),
    )


def load_from_database(database_url: str | None = None) -> DashboardData:
    """Load measurements, regressions and import history from PostgreSQL."""
    engine = get_engine(database_url or DEFAULT_DATABASE_URL)
    try:
        check_connection(engine)
        measurements = _coerce_measurements(fetch_measurements(engine))
        regressions = _coerce_regressions(fetch_regression_results(engine))
        imports = fetch_import_history(engine)
        issues = fetch_quality_issues(engine)
    finally:
        engine.dispose()

    bundle = _analysis(measurements, regressions)

    return DashboardData(
        measurements=measurements,
        regressions=bundle.regressions,
        descriptive=bundle.descriptive,
        residuals=bundle.residuals,
        comparison=bundle.comparison,
        quality=quality_from_imports(imports),
        issues=issues[ISSUE_COLUMNS] if not issues.empty else _empty(ISSUE_COLUMNS),
        imports=imports[IMPORT_COLUMNS] if not imports.empty else _empty(IMPORT_COLUMNS),
        source_label="PostgreSQL",
    )


def load_dashboard_data(
    source: str = SOURCE_AUTO,
    database_url: str | None = None,
    processed_path: Path | None = None,
    reports_dir: Path | None = None,
) -> DashboardData:
    """Load dashboard data from PostgreSQL, local files, or both (``auto``)."""
    if source == SOURCE_DATABASE:
        return load_from_database(database_url)

    if source == SOURCE_FILES:
        return load_local(processed_path, reports_dir)

    try:
        database = load_from_database(database_url)
    except Exception as exc:  # noqa: BLE001 - the dashboard must stay usable offline
        local = load_local(processed_path, reports_dir)
        return replace(
            local,
            warning=_combine_warnings(
                "PostgreSQL ist nicht erreichbar "
                f"({type(exc).__name__}). Angezeigt werden die lokalen Dateien.",
                local.warning,
            ),
        )

    if not database.measurements.empty:
        return database

    try:
        local = load_local(processed_path, reports_dir)
    except FileNotFoundError:
        return database

    return replace(
        local,
        warning=_combine_warnings(
            "Die Datenbank enthält noch keine Messungen. "
            "Angezeigt werden die lokalen Dateien.",
            local.warning,
        ),
    )


def filter_measurements(
    measurements: pd.DataFrame,
    experiments: list[str] | None = None,
    samples: list[str] | None = None,
    angle_range: tuple[float, float] | None = None,
) -> pd.DataFrame:
    """Apply the sidebar filters to a measurement frame."""
    if measurements.empty:
        return measurements

    mask = pd.Series(True, index=measurements.index)
    if experiments is not None:
        mask &= measurements["experiment_id"].isin(experiments)
    if samples is not None:
        mask &= measurements["sample_id"].isin(samples)
    if angle_range is not None:
        low, high = angle_range
        mask &= measurements["measurement_angle"].between(low, high)

    return measurements[mask].reset_index(drop=True)


def filter_regressions(
    regressions: pd.DataFrame,
    experiments: list[str] | None = None,
    samples: list[str] | None = None,
) -> pd.DataFrame:
    """Keep regressions that belong to the selected experiment/sample filters."""
    if regressions.empty:
        return regressions

    mask = pd.Series(True, index=regressions.index)
    if experiments is not None:
        mask &= regressions["experiment_id"].isin(experiments)
    if samples is not None:
        mask &= regressions["sample_id"].isin(samples)
    return regressions[mask].reset_index(drop=True)


def build_view(
    data: DashboardData,
    measurements: pd.DataFrame,
    regressions: pd.DataFrame,
) -> DashboardData:
    """Rebuild derived tables after the sidebar filters were applied."""
    return replace(
        data,
        measurements=measurements,
        regressions=regressions,
        descriptive=descriptive_statistics(measurements),
        residuals=attach_residuals(measurements, regressions),
        comparison=compare_experiments(regressions),
    )


def fitted_lines(
    measurements: pd.DataFrame,
    regressions: pd.DataFrame,
    points: int = 80,
) -> pd.DataFrame:
    """Return evenly spaced line coordinates for each fitted regression."""
    columns = ["experiment_id", "sample_id", "measurement_angle", "fitted_rotation"]
    if measurements.empty or regressions.empty:
        return _empty(columns)

    ranges = (
        measurements.groupby(["experiment_id", "sample_id"])["measurement_angle"]
        .agg(["min", "max"])
        .reset_index()
    )
    ranges = ranges.merge(
        regressions[["experiment_id", "sample_id", "slope", "intercept"]],
        on=["experiment_id", "sample_id"],
        how="inner",
    )

    rows: list[dict[str, object]] = []
    for row in ranges.itertuples(index=False):
        for angle in np.linspace(float(row.min), float(row.max), points):
            rows.append(
                {
                    "experiment_id": row.experiment_id,
                    "sample_id": row.sample_id,
                    "measurement_angle": float(angle),
                    "fitted_rotation": float(row.slope * angle + row.intercept),
                }
            )
    return pd.DataFrame(rows, columns=columns)


def summarize(
    data: DashboardData,
) -> dict[str, float | int]:
    """Small set of headline numbers for the KPI cards."""
    measurements = data.measurements
    regressions = data.regressions

    if measurements.empty:
        experiments = samples = 0
    else:
        experiments = int(measurements["experiment_id"].nunique())
        samples = int(
            measurements[["experiment_id", "sample_id"]].drop_duplicates().shape[0]
        )

    r_squared = (
        float(regressions["r_squared"].mean())
        if not regressions.empty and regressions["r_squared"].notna().any()
        else float("nan")
    )

    rejected = 0
    if not data.quality.empty and "rejected_rows" in data.quality.columns:
        all_rows = data.quality[data.quality["source_file"] == "ALL"]
        rejected = int((all_rows if not all_rows.empty else data.quality)["rejected_rows"].sum())

    return {
        "measurements": int(len(measurements)),
        "experiments": experiments,
        "samples": samples,
        "regressions": int(len(regressions)),
        "mean_r_squared": r_squared,
        "rejected": rejected,
    }


def equation(row: pd.Series) -> str:
    """Format ``y = slope x + intercept`` with a proper sign."""
    sign = "+" if float(row["intercept"]) >= 0 else "-"
    return f"y = {float(row['slope']):.6g} x {sign} {abs(float(row['intercept'])):.6g}"


def group_label(experiment_id: str, sample_id: str) -> str:
    return f"{experiment_id} / {sample_id}"
