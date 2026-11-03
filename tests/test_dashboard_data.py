from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.dashboard_data import (
    SOURCE_AUTO,
    SOURCE_FILES,
    DashboardData,
    attach_residuals,
    build_view,
    filter_measurements,
    filter_regressions,
    fitted_lines,
    load_dashboard_data,
    load_from_database,
    load_local,
    quality_from_imports,
    summarize,
)
import src.dashboard_data as dashboard_data
from src.database import get_engine, init_db, persist_dataset
from src.ingestion import SourceFile
from src.validation import validate_measurements


def _measurements() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "experiment_id": ["EXP-001", "EXP-001", "EXP-001", "EXP-002"],
            "sample_id": ["S-01", "S-01", "S-01", "S-02"],
            "measurement_angle": [0.0, 10.0, 20.0, 0.0],
            "observed_rotation": [1.0, 21.0, 41.0, 5.0],
            "measurement_timestamp": pd.to_datetime(
                [
                    "2026-01-01T10:00:00",
                    "2026-01-01T10:01:00",
                    "2026-01-01T10:02:00",
                    "2026-01-02T10:00:00",
                ]
            ),
        }
    )


def _regressions() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "experiment_id": ["EXP-001", "EXP-002"],
            "sample_id": ["S-01", "S-02"],
            "n_points": [3, 1],
            "slope": [2.0, 1.5],
            "intercept": [1.0, 5.0],
            "r_squared": [1.0, float("nan")],
            "slope_std_error": [0.0, float("nan")],
            "intercept_std_error": [0.0, float("nan")],
            "residual_std_error": [0.0, float("nan")],
        }
    )


def test_attach_residuals_uses_slope_and_intercept() -> None:
    residuals = attach_residuals(_measurements(), _regressions())

    assert list(residuals.columns) == [
        "experiment_id",
        "sample_id",
        "measurement_angle",
        "observed_rotation",
        "predicted_rotation",
        "residual",
    ]
    assert len(residuals) == 4
    first = residuals.iloc[0]
    assert first["predicted_rotation"] == pytest.approx(1.0)
    assert first["residual"] == pytest.approx(0.0)
    assert residuals["residual"].abs().max() == pytest.approx(0.0)


def test_attach_residuals_without_data_is_empty() -> None:
    residuals = attach_residuals(pd.DataFrame(), _regressions())
    assert residuals.empty
    assert "residual" in residuals.columns


def test_filter_measurements_none_means_no_filter() -> None:
    filtered = filter_measurements(_measurements())
    assert len(filtered) == 4


def test_filter_measurements_empty_selection_returns_nothing() -> None:
    filtered = filter_measurements(_measurements(), experiments=[], samples=[])
    assert filtered.empty


def test_filter_measurements_applies_all_criteria() -> None:
    filtered = filter_measurements(
        _measurements(),
        experiments=["EXP-001"],
        samples=["S-01"],
        angle_range=(5.0, 15.0),
    )
    assert len(filtered) == 1
    assert filtered.iloc[0]["measurement_angle"] == pytest.approx(10.0)


def test_filter_regressions_respects_selection() -> None:
    filtered = filter_regressions(_regressions(), experiments=["EXP-002"])
    assert filtered["experiment_id"].tolist() == ["EXP-002"]


def test_build_view_recomputes_derived_tables_for_filters() -> None:
    measurements = _measurements()
    regressions = _regressions()
    data = DashboardData(
        measurements=measurements,
        regressions=regressions,
        descriptive=pd.DataFrame(),
        residuals=pd.DataFrame(),
        comparison=pd.DataFrame(),
        quality=pd.DataFrame(),
        issues=pd.DataFrame(),
        imports=pd.DataFrame(),
        source_label="Test",
    )

    filtered = measurements[measurements["experiment_id"] == "EXP-001"]
    view = build_view(data, filtered, filter_regressions(regressions, ["EXP-001"]))

    assert len(view.descriptive) == 1
    assert view.descriptive.loc[0, "sample_id"] == "S-01"
    assert view.residuals["experiment_id"].unique().tolist() == ["EXP-001"]
    assert len(view.residuals) == 3
    assert view.comparison["experiment_id"].tolist() == ["EXP-001"]


def test_fitted_lines_match_regression_endpoints() -> None:
    lines = fitted_lines(_measurements(), _regressions(), points=5)

    first_group = lines[(lines["experiment_id"] == "EXP-001")].sort_values(
        "measurement_angle"
    )
    assert first_group["measurement_angle"].min() == pytest.approx(0.0)
    assert first_group["measurement_angle"].max() == pytest.approx(20.0)
    assert first_group["fitted_rotation"].min() == pytest.approx(1.0)
    assert first_group["fitted_rotation"].max() == pytest.approx(41.0)


def test_summarize_counts_and_mean_r_squared() -> None:
    quality = pd.DataFrame(
        {
            "source_file": ["a.csv", "ALL"],
            "rejected_rows": [2, 3],
        }
    )

    summary = summarize(
        DashboardData(
            measurements=_measurements(),
            regressions=_regressions(),
            descriptive=pd.DataFrame(),
            residuals=pd.DataFrame(),
            comparison=pd.DataFrame(),
            quality=quality,
            issues=pd.DataFrame(),
            imports=pd.DataFrame(),
            source_label="Test",
        )
    )

    assert summary["measurements"] == 4
    assert summary["experiments"] == 2
    assert summary["samples"] == 2
    assert summary["regressions"] == 2
    assert summary["mean_r_squared"] == pytest.approx(1.0)
    assert summary["rejected"] == 3


def test_quality_from_imports_uses_file_names_and_total_row() -> None:
    imports = pd.DataFrame(
        {
            "source_file": ["C:/data/one.csv", "C:/data/two.csv"],
            "imported_at": ["2026-01-01", "2026-01-02"],
            "n_rows": [10, 5],
            "n_valid": [9, 5],
            "n_invalid": [1, 0],
            "n_duplicates": [0, 0],
        }
    )

    quality = quality_from_imports(imports)

    assert quality["source_file"].tolist() == ["one.csv", "two.csv", "ALL"]
    total = quality[quality["source_file"] == "ALL"].iloc[0]
    assert total["total_rows"] == 15
    assert total["rejected_rows"] == 1


def test_load_local_reads_pipeline_artifacts(tmp_path: Path) -> None:
    processed = tmp_path / "processed_measurements.csv"
    _measurements().to_csv(processed, index=False)
    reports = tmp_path / "reports"
    reports.mkdir()
    _regressions().to_csv(reports / "regression_results.csv", index=False)
    pd.DataFrame(
        {
            "source_file": ["measurements.csv"],
            "total_rows": [4],
            "valid_rows": [4],
            "invalid_rows": [0],
            "duplicate_rows": [0],
            "rejected_rows": [0],
        }
    ).to_csv(reports / "data_quality_report.csv", index=False)

    data = load_local(processed_path=processed, reports_dir=reports)

    assert data.source_label == "Lokale Dateien"
    assert len(data.measurements) == 4
    assert len(data.regressions) == 2
    assert not data.residuals.empty
    assert data.quality.iloc[0]["total_rows"] == 4
    assert data.imports.empty


def test_load_local_computes_regressions_when_report_is_missing(tmp_path: Path) -> None:
    processed = tmp_path / "processed_measurements.csv"
    _measurements().to_csv(processed, index=False)

    data = load_local(processed_path=processed, reports_dir=tmp_path / "missing")

    assert len(data.regressions) == 1
    assert data.regressions.iloc[0]["experiment_id"] == "EXP-001"


def test_load_local_requires_processed_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_local(processed_path=tmp_path / "nope.csv", reports_dir=tmp_path)


def test_load_local_falls_back_to_bundled_demo(
    tmp_path: Path, monkeypatch
) -> None:
    demo_dir = tmp_path / "demo"
    demo_dir.mkdir()
    demo_processed = demo_dir / "processed_measurements.csv"
    _measurements().to_csv(demo_processed, index=False)
    demo_reports = demo_dir / "reports"
    demo_reports.mkdir()
    _regressions().to_csv(demo_reports / "regression_results.csv", index=False)

    monkeypatch.setattr(dashboard_data, "DATA_PROCESSED_DIR", tmp_path / "missing")
    monkeypatch.setattr(dashboard_data, "REPORTS_DIR", tmp_path / "missing-reports")
    monkeypatch.setattr(dashboard_data, "DEMO_PROCESSED_PATH", demo_processed)
    monkeypatch.setattr(dashboard_data, "DEMO_REPORTS_DIR", demo_reports)

    data = load_local()

    assert len(data.measurements) == 4
    assert data.warning is not None
    assert "Demo-Daten" in data.warning


def test_load_dashboard_data_falls_back_to_files(tmp_path: Path) -> None:
    processed = tmp_path / "processed_measurements.csv"
    _measurements().to_csv(processed, index=False)
    empty_database = tmp_path / "empty.db"
    init_db(get_engine(f"sqlite+pysqlite:///{empty_database}"))

    data = load_dashboard_data(
        source=SOURCE_AUTO,
        database_url=f"sqlite+pysqlite:///{empty_database}",
        processed_path=processed,
        reports_dir=tmp_path,
    )

    assert data.source_label == "Lokale Dateien"
    assert data.warning is not None
    assert len(data.measurements) == 4


def test_load_dashboard_data_files_source(tmp_path: Path) -> None:
    processed = tmp_path / "processed_measurements.csv"
    _measurements().to_csv(processed, index=False)

    data = load_dashboard_data(
        source=SOURCE_FILES, processed_path=processed, reports_dir=tmp_path
    )

    assert data.warning is None
    assert len(data.measurements) == 4


def test_load_from_empty_database_returns_empty_frames(tmp_path: Path) -> None:
    database = tmp_path / "empty.db"
    init_db(get_engine(f"sqlite+pysqlite:///{database}"))

    data = load_from_database(f"sqlite+pysqlite:///{database}")

    assert data.source_label == "PostgreSQL"
    assert data.measurements.empty
    assert data.regressions.empty
    assert data.quality.empty
    assert data.issues.empty


def test_load_from_database_includes_quality_issues(tmp_path: Path, make_raw) -> None:
    database = tmp_path / "quality.db"
    engine = get_engine(f"sqlite+pysqlite:///{database}")
    init_db(engine)
    raw = make_raw(
        [
            {
                "experiment_id": "E1",
                "sample_id": "S1",
                "measurement_angle": "0",
                "observed_rotation": "1",
                "measurement_timestamp": "2026-01-01T00:00:00Z",
            },
            {
                "experiment_id": "E1",
                "sample_id": "S1",
                "measurement_angle": "bad",
                "observed_rotation": "1",
                "measurement_timestamp": "2026-01-01T00:01:00Z",
            },
        ]
    )
    validated = validate_measurements(raw)
    persist_dataset(
        engine,
        validated,
        [SourceFile(path=Path("test.csv"), sha256="8" * 64, row_count=len(validated))],
    )
    engine.dispose()

    data = load_from_database(f"sqlite+pysqlite:///{database}")

    assert len(data.measurements) == 1
    assert data.issues["status"].tolist() == ["invalid"]
    assert data.issues.loc[0, "source_file"] == "test.csv"
