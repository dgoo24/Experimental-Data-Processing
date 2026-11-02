from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.analysis import analyze_measurements
from src.cleaning import select_valid_measurements
from src.database import (
    Experiment,
    ImportRecord,
    ProcessedMeasurement,
    RawMeasurement,
    RegressionResult,
    Sample,
    check_connection,
    database_summary,
    fetch_import_history,
    fetch_measurements,
    fetch_regression_results,
    persist_dataset,
    store_regression_results,
)
from src.ingestion import SourceFile
from src.validation import validate_measurements


def _source(name: str, digest: str, rows: int) -> SourceFile:
    return SourceFile(path=Path(name), sha256=digest, row_count=rows)


def test_persist_dataset_creates_relational_rows(sqlite_engine, validated_frame):
    sources = [_source("measurements.csv", "a" * 64, len(validated_frame))]
    outcomes = persist_dataset(sqlite_engine, validated_frame, sources)

    assert len(outcomes) == 1
    assert outcomes[0].status == "imported"
    assert outcomes[0].stored_processed == 10
    summary = database_summary(sqlite_engine)
    assert summary == {
        "experiments": 2,
        "samples": 2,
        "imports": 1,
        "raw_measurements": 10,
        "processed_measurements": 10,
        "regression_results": 0,
    }

    measurements = fetch_measurements(sqlite_engine, experiment_code="EXP-001")
    assert len(measurements) == 6
    assert measurements["sample_id"].unique().tolist() == ["S-01"]


def test_invalid_rows_are_retained_in_raw_table(sqlite_engine, make_raw):
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
    sources = [_source("test.csv", "b" * 64, len(validated))]

    outcomes = persist_dataset(sqlite_engine, validated, sources)

    assert outcomes[0].stored_processed == 1
    with Session(sqlite_engine) as session:
        raw_statuses = session.scalars(
            select(RawMeasurement.status).order_by(RawMeasurement.source_row)
        ).all()
        assert raw_statuses == ["valid", "invalid"]
        assert session.scalar(select(ProcessedMeasurement).limit(1)) is not None


def test_same_file_hash_is_skipped(sqlite_engine, validated_frame):
    sources = [_source("measurements.csv", "c" * 64, len(validated_frame))]

    first = persist_dataset(sqlite_engine, validated_frame, sources)
    second = persist_dataset(sqlite_engine, validated_frame, sources)

    assert first[0].status == "imported"
    assert second[0].status == "skipped_existing_file"
    assert database_summary(sqlite_engine)["raw_measurements"] == 10
    assert database_summary(sqlite_engine)["processed_measurements"] == 10


def test_changed_file_does_not_duplicate_measurement_points(sqlite_engine, validated_frame):
    first_sources = [_source("measurements.csv", "d" * 64, len(validated_frame))]
    persist_dataset(sqlite_engine, validated_frame, first_sources)

    reopened = validated_frame.copy()
    reopened["source_file"] = "measurements_copy.csv"
    second_sources = [_source("measurements_copy.csv", "e" * 64, len(reopened))]

    outcomes = persist_dataset(sqlite_engine, reopened, second_sources)

    assert outcomes[0].stored_processed == 0
    assert outcomes[0].already_stored == 10
    summary = database_summary(sqlite_engine)
    assert summary["raw_measurements"] == 20
    assert summary["processed_measurements"] == 10
    assert summary["experiments"] == 2


def test_regression_results_round_trip(sqlite_engine, validated_frame):
    processed = select_valid_measurements(validated_frame)
    bundle = analyze_measurements(processed)
    sources = [_source("measurements.csv", "f" * 64, len(validated_frame))]
    persist_dataset(sqlite_engine, validated_frame, sources)

    result = store_regression_results(sqlite_engine, bundle.regressions)
    assert result.stored == 2
    assert result.skipped == []

    stored = fetch_regression_results(sqlite_engine)
    assert len(stored) == 2
    first = stored[stored["experiment_id"] == "EXP-001"].iloc[0]
    assert first["slope"] == pytest.approx(3.0)
    assert first["intercept"] == pytest.approx(2.0)
    assert first["r_squared"] == pytest.approx(1.0)

    # Re-running updates instead of adding duplicate result rows.
    store_regression_results(sqlite_engine, bundle.regressions)
    assert database_summary(sqlite_engine)["regression_results"] == 2


def test_import_history_and_experiment_filter(sqlite_engine, validated_frame):
    sources = [_source("measurements.csv", "1" * 64, len(validated_frame))]
    persist_dataset(sqlite_engine, validated_frame, sources)

    history = fetch_import_history(sqlite_engine)
    assert len(history) == 1
    assert history.loc[0, "n_rows"] == 10
    assert history.loc[0, "n_valid"] == 10

    filtered = fetch_measurements(sqlite_engine, experiment_code="EXP-002")
    assert filtered["experiment_id"].unique().tolist() == ["EXP-002"]


def test_store_regression_skips_missing_experiment(sqlite_engine):
    regressions = pd.DataFrame(
        [
            {
                "experiment_id": "DOES-NOT-EXIST",
                "sample_id": "S-01",
                "n_points": 4,
                "slope": 1.0,
                "intercept": 0.0,
                "r_squared": 1.0,
                "slope_std_error": 0.0,
                "intercept_std_error": 0.0,
                "residual_std_error": 0.0,
            }
        ]
    )

    result = store_regression_results(sqlite_engine, regressions)

    assert result.stored == 0
    assert len(result.skipped) == 1


def test_connection_and_schema(sqlite_engine):
    check_connection(sqlite_engine)
    summary = database_summary(sqlite_engine)
    assert summary["experiments"] == 0
    with Session(sqlite_engine) as session:
        assert session.scalar(select(Experiment).limit(1)) is None
        assert session.scalar(select(Sample).limit(1)) is None
        assert session.scalar(select(ImportRecord).limit(1)) is None
        assert session.scalar(select(RegressionResult).limit(1)) is None
