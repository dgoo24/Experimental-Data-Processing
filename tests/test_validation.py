from __future__ import annotations

import pandas as pd

from src.validation import (
    STATUS_DUPLICATE,
    STATUS_INVALID,
    STATUS_VALID,
    ValidationConfig,
    build_quality_report,
    quality_issues,
    validate_measurements,
)


def _row(angle="0", rotation="1.5", timestamp="2026-01-01T10:00:00Z", experiment="E1", sample="S1"):
    return {
        "experiment_id": experiment,
        "sample_id": sample,
        "measurement_angle": angle,
        "observed_rotation": rotation,
        "measurement_timestamp": timestamp,
    }


def test_valid_rows_pass(make_raw):
    raw = make_raw([_row("0"), _row("10", "3.2", "2026-01-01T10:01:00Z")])
    validated = validate_measurements(raw)

    assert validated["status"].tolist() == [STATUS_VALID, STATUS_VALID]
    assert validated["validation_errors"].tolist() == ["", ""]
    assert validated["measurement_angle_value"].tolist() == [0.0, 10.0]


def test_each_validation_problem_is_reported(make_raw):
    rows = [
        _row("0", "1.0"),  # valid canonical row
        _row("10", "", "2026-01-01T10:01:00Z"),  # missing rotation
        _row("bad", "1.0", "2026-01-01T10:02:00Z"),  # non-numeric angle
        _row("999", "1.0", "2026-01-01T10:03:00Z"),  # angle out of range
        _row("30", "500", "2026-01-01T10:04:00Z"),  # rotation out of range
        _row("40", "1.0", "not-a-date"),  # invalid timestamp
        _row("50", "1.0", "2026-01-01T10:06:00Z", experiment="E" * 65),  # id too long
        _row("0", "1.0"),  # duplicate of canonical row
        _row("0", "9.0", "2026-01-01T11:00:00Z"),  # same angle, new timestamp
    ]
    validated = validate_measurements(make_raw(rows))

    assert validated.loc[0, "status"] == STATUS_VALID
    assert validated.loc[1, "status"] == STATUS_INVALID
    assert "missing required" in validated.loc[1, "validation_errors"]
    assert validated.loc[2, "status"] == STATUS_INVALID
    assert "non-numeric" in validated.loc[2, "validation_errors"]
    assert validated.loc[3, "status"] == STATUS_INVALID
    assert "measurement_angle outside" in validated.loc[3, "validation_errors"]
    assert validated.loc[4, "status"] == STATUS_INVALID
    assert "observed_rotation outside" in validated.loc[4, "validation_errors"]
    assert validated.loc[5, "status"] == STATUS_INVALID
    assert "ISO-8601" in validated.loc[5, "validation_errors"]
    assert validated.loc[6, "status"] == STATUS_INVALID
    assert "longer than 64" in validated.loc[6, "validation_errors"]
    assert validated.loc[7, "status"] == STATUS_DUPLICATE
    assert "duplicate" in validated.loc[7, "validation_errors"]
    assert validated.loc[8, "status"] == STATUS_VALID


def test_invalid_row_keeps_duplicate_flag_but_is_invalid(make_raw):
    validated = validate_measurements(
        make_raw(
            [
                _row("0", "1.0"),
                _row("0", ""),  # same key, but missing rotation
            ]
        )
    )

    assert validated.loc[1, "duplicate_measurement"]
    assert validated.loc[1, "missing_required"]
    assert validated.loc[1, "status"] == STATUS_INVALID
    assert "duplicate" in validated.loc[1, "validation_errors"]


def test_duplicate_detection_spans_source_files(make_raw):
    first = make_raw([_row("0", "1.0")], source_file="a.csv")
    second = make_raw([_row("0", "1.0")], source_file="b.csv")
    combined = pd.concat([first, second], ignore_index=True)

    validated = validate_measurements(combined)

    assert validated.loc[0, "status"] == STATUS_VALID
    assert validated.loc[1, "status"] == STATUS_DUPLICATE


def test_timestamp_offsets_are_normalized_to_naive_utc(make_raw):
    raw = make_raw([_row("0", "1.0", "2026-01-01T12:00:00+02:00")])
    validated = validate_measurements(raw)

    value = validated.loc[0, "measurement_timestamp_value"]
    assert value == pd.Timestamp("2026-01-01T10:00:00")
    assert value.tzinfo is None


def test_custom_ranges_are_used(make_raw):
    raw = make_raw([_row("0", "10"), _row("100", "10", "2026-01-01T10:01:00Z")])
    validated = validate_measurements(
        raw,
        config=ValidationConfig(
            angle_min=-50,
            angle_max=50,
            rotation_min=-20,
            rotation_max=20,
        ),
    )

    assert validated["status"].tolist() == [STATUS_VALID, STATUS_INVALID]


def test_quality_report_counts_and_total_row(make_raw):
    first = make_raw(
        [_row("0", "1.0"), _row("10", "bad", "2026-01-01T10:01:00Z")],
        source_file="a.csv",
    )
    second = make_raw([_row("20", "3.0", "2026-01-01T10:02:00Z")], source_file="b.csv")
    validated = validate_measurements(pd.concat([first, second], ignore_index=True))

    report = build_quality_report(validated)

    assert report["source_file"].tolist() == ["a.csv", "b.csv", "ALL"]
    total = report[report["source_file"] == "ALL"].iloc[0]
    assert total["total_rows"] == 3
    assert total["valid_rows"] == 2
    assert total["invalid_rows"] == 1
    assert total["rejected_rows"] == 1
    assert total["non_numeric_rows"] == 1


def test_quality_issues_keep_original_values(make_raw):
    validated = validate_measurements(make_raw([_row("bad", "1.0")]))
    issues = quality_issues(validated)

    assert len(issues) == 1
    assert issues.loc[0, "measurement_angle"] == "bad"
    assert issues.loc[0, "status"] == STATUS_INVALID
    assert "non-numeric" in issues.loc[0, "validation_errors"]


def test_invalid_config_is_rejected():
    import pytest

    with pytest.raises(ValueError, match="angle_min"):
        ValidationConfig(angle_min=10, angle_max=10)
