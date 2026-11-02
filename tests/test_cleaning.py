from __future__ import annotations

import pandas as pd

from src.cleaning import (
    PROCESSED_COLUMNS,
    clean_measurements,
    export_processed_measurements,
    select_valid_measurements,
)


def test_select_valid_measurements_returns_typed_sorted_rows(validated_frame):
    processed = select_valid_measurements(validated_frame)

    assert list(processed.columns) == PROCESSED_COLUMNS
    assert len(processed) == 10
    assert processed["experiment_id"].tolist()[0] == "EXP-001"
    assert processed["sample_id"].tolist()[0] == "S-01"
    assert pd.api.types.is_float_dtype(processed["measurement_angle"])
    assert pd.api.types.is_float_dtype(processed["observed_rotation"])
    assert pd.api.types.is_datetime64_any_dtype(processed["measurement_timestamp"])


def test_invalid_and_duplicate_rows_are_excluded(make_raw):
    rows = [
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
        {
            "experiment_id": "E1",
            "sample_id": "S1",
            "measurement_angle": "0",
            "observed_rotation": "2",
            "measurement_timestamp": "2026-01-01T00:00:00Z",
        },
    ]
    validated, processed = clean_measurements(make_raw(rows))

    assert len(validated) == 3
    assert len(processed) == 1
    assert processed.loc[0, "observed_rotation"] == 1.0


def test_empty_result_has_expected_columns(make_raw):
    validated, processed = clean_measurements(
        make_raw(
            [
                {
                    "experiment_id": "E1",
                    "sample_id": "S1",
                    "measurement_angle": "bad",
                    "observed_rotation": "1",
                    "measurement_timestamp": "2026-01-01T00:00:00Z",
                }
            ]
        )
    )

    assert len(processed) == 0
    assert list(processed.columns) == PROCESSED_COLUMNS


def test_export_processed_measurements(tmp_path, processed_frame):
    path = export_processed_measurements(processed_frame, tmp_path / "clean.csv")

    assert path.exists()
    loaded = pd.read_csv(path)
    assert len(loaded) == len(processed_frame)
    assert list(loaded.columns) == PROCESSED_COLUMNS
