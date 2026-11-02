"""Validation and data-quality reporting.

Validation is deliberately row-based and easy to audit:

* required values must be present,
* identifiers must be short enough for the database,
* angles/rotations must be finite numbers inside configurable ranges,
* timestamps must be ISO-8601 parseable (normalized to UTC),
* repeated measurements are flagged by
  ``(experiment_id, sample_id, measurement_angle, measurement_timestamp)``.

Rows are never removed.  Each row receives a status of ``valid``, ``invalid`` or
``duplicate`` plus a human-readable explanation.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .ingestion import METADATA_COLUMNS, REQUIRED_COLUMNS

STATUS_VALID = "valid"
STATUS_INVALID = "invalid"
STATUS_DUPLICATE = "duplicate"

ISSUE_COLUMNS = [
    "missing_required",
    "non_numeric",
    "out_of_range",
    "invalid_timestamp",
    "invalid_id",
    "duplicate_measurement",
]

QUALITY_COLUMNS = [
    "source_file",
    "total_rows",
    "valid_rows",
    "invalid_rows",
    "duplicate_rows",
    "rejected_rows",
    "missing_required_rows",
    "non_numeric_rows",
    "out_of_range_rows",
    "invalid_timestamp_rows",
    "invalid_id_rows",
    "duplicate_measurement_rows",
]


@dataclass(frozen=True)
class ValidationConfig:
    """Configurable acceptance ranges for one measurement.

    Defaults are intentionally wide quality-control limits, not physical
    constants.  Units are degrees for both angle and rotation.
    """

    angle_min: float = -360.0
    angle_max: float = 360.0
    rotation_min: float = -180.0
    rotation_max: float = 180.0
    max_id_length: int = 64

    def __post_init__(self) -> None:
        if not np.isfinite([self.angle_min, self.angle_max]).all():
            raise ValueError("angle limits must be finite")
        if not np.isfinite([self.rotation_min, self.rotation_max]).all():
            raise ValueError("rotation limits must be finite")
        if self.angle_min >= self.angle_max:
            raise ValueError("angle_min must be smaller than angle_max")
        if self.rotation_min >= self.rotation_max:
            raise ValueError("rotation_min must be smaller than rotation_max")
        if self.max_id_length < 1:
            raise ValueError("max_id_length must be positive")


def _is_blank(series: pd.Series) -> pd.Series:
    return series.isna() | series.astype(str).str.strip().eq("")


def _is_blank_value(value: object) -> bool:
    return pd.isna(value) or str(value).strip() == ""


def _parse_utc(series: pd.Series) -> pd.Series:
    """Parse timestamps to timezone-naive UTC values.

    Input without an offset is treated as UTC.  Documenting one interpretation
    avoids silent local-time/UTC mixing in the database.
    """
    parsed = pd.to_datetime(series, errors="coerce", utc=True, format="mixed")
    return parsed.dt.tz_convert(None)


def _error_messages(frame: pd.DataFrame, config: ValidationConfig) -> pd.Series:
    messages: list[str] = []

    for index in frame.index:
        errors: list[str] = []

        missing = [
            column
            for column in REQUIRED_COLUMNS
            if _is_blank_value(frame.at[index, column])
        ]
        if missing:
            errors.append("missing required value(s): " + ", ".join(missing))

        if bool(frame.at[index, "non_numeric"]):
            errors.append("non-numeric or non-finite measurement value")

        angle = frame.at[index, "measurement_angle_value"]
        rotation = frame.at[index, "observed_rotation_value"]
        if bool(frame.at[index, "out_of_range"]):
            if np.isfinite(angle) and not (config.angle_min <= angle <= config.angle_max):
                errors.append(
                    "measurement_angle outside "
                    f"[{config.angle_min:g}, {config.angle_max:g}] deg"
                )
            if np.isfinite(rotation) and not (
                config.rotation_min <= rotation <= config.rotation_max
            ):
                errors.append(
                    "observed_rotation outside "
                    f"[{config.rotation_min:g}, {config.rotation_max:g}] deg"
                )

        if bool(frame.at[index, "invalid_timestamp"]):
            errors.append("measurement_timestamp is not a valid ISO-8601 timestamp")
        if bool(frame.at[index, "invalid_id"]):
            errors.append(
                "experiment_id or sample_id is longer than "
                f"{config.max_id_length} characters"
            )
        if bool(frame.at[index, "duplicate_measurement"]):
            errors.append(
                "duplicate measurement (same experiment, sample, angle and timestamp)"
            )

        messages.append("; ".join(errors))

    return pd.Series(messages, index=frame.index, dtype="object")


def validate_measurements(
    frame: pd.DataFrame,
    config: ValidationConfig | None = None,
) -> pd.DataFrame:
    """Return a copy of ``frame`` with parsed values and validation flags."""
    config = config or ValidationConfig()

    missing_columns = [
        column for column in REQUIRED_COLUMNS + METADATA_COLUMNS if column not in frame.columns
    ]
    if missing_columns:
        raise ValueError(f"validation input is missing column(s): {', '.join(missing_columns)}")

    result = frame.reset_index(drop=True).copy()
    text = result[REQUIRED_COLUMNS].astype(str)

    experiment_text = text["experiment_id"]
    sample_text = text["sample_id"]
    angle_text = text["measurement_angle"]
    rotation_text = text["observed_rotation"]
    timestamp_text = text["measurement_timestamp"]

    experiment_missing = _is_blank(experiment_text)
    sample_missing = _is_blank(sample_text)
    angle_missing = _is_blank(angle_text)
    rotation_missing = _is_blank(rotation_text)
    timestamp_missing = _is_blank(timestamp_text)

    result["missing_required"] = (
        experiment_missing | sample_missing | angle_missing | rotation_missing | timestamp_missing
    )

    angle = pd.to_numeric(angle_text, errors="coerce").astype(float)
    rotation = pd.to_numeric(rotation_text, errors="coerce").astype(float)

    result["non_numeric"] = (
        (~angle_missing & ~np.isfinite(angle))
        | (~rotation_missing & ~np.isfinite(rotation))
    )

    result["out_of_range"] = (
        np.isfinite(angle)
        & ((angle < config.angle_min) | (angle > config.angle_max))
    ) | (
        np.isfinite(rotation)
        & ((rotation < config.rotation_min) | (rotation > config.rotation_max))
    )

    timestamp = _parse_utc(timestamp_text.where(~timestamp_missing))
    result["invalid_timestamp"] = ~timestamp_missing & timestamp.isna()

    experiment_stripped = experiment_text.str.strip()
    sample_stripped = sample_text.str.strip()
    result["invalid_id"] = (
        (experiment_stripped.str.len() > config.max_id_length)
        | (sample_stripped.str.len() > config.max_id_length)
    )

    result["measurement_angle_value"] = angle
    result["observed_rotation_value"] = rotation
    result["measurement_timestamp_value"] = timestamp

    # Duplicate detection only uses rows whose key fields are usable.  Repeated
    # measurements at the same angle but with different timestamps are allowed.
    duplicate_eligible = (
        ~experiment_missing
        & ~sample_missing
        & ~angle_missing
        & ~timestamp_missing
        & ~result["non_numeric"]
        & ~result["invalid_timestamp"]
        & ~result["invalid_id"]
        & np.isfinite(angle)
    )
    duplicate_keys = pd.DataFrame(
        {
            "experiment_id": experiment_stripped,
            "sample_id": sample_stripped,
            "measurement_angle": angle,
            "measurement_timestamp": timestamp,
        }
    )
    result["duplicate_measurement"] = duplicate_keys.duplicated(keep="first") & duplicate_eligible

    has_issue = result[
        ["missing_required", "non_numeric", "out_of_range", "invalid_timestamp", "invalid_id"]
    ].any(axis=1)
    result["status"] = np.select(
        [has_issue, result["duplicate_measurement"]],
        [STATUS_INVALID, STATUS_DUPLICATE],
        default=STATUS_VALID,
    )

    result["validation_errors"] = _error_messages(result, config)
    result["experiment_id_value"] = experiment_stripped
    result["sample_id_value"] = sample_stripped
    return result


def _count(group: pd.DataFrame) -> dict[str, object]:
    return {
        "total_rows": int(len(group)),
        "valid_rows": int(group["status"].eq(STATUS_VALID).sum()),
        "invalid_rows": int(group["status"].eq(STATUS_INVALID).sum()),
        "duplicate_rows": int(group["status"].eq(STATUS_DUPLICATE).sum()),
        "rejected_rows": int(group["status"].ne(STATUS_VALID).sum()),
        "missing_required_rows": int(group["missing_required"].sum()),
        "non_numeric_rows": int(group["non_numeric"].sum()),
        "out_of_range_rows": int(group["out_of_range"].sum()),
        "invalid_timestamp_rows": int(group["invalid_timestamp"].sum()),
        "invalid_id_rows": int(group["invalid_id"].sum()),
        "duplicate_measurement_rows": int(group["duplicate_measurement"].sum()),
    }


def build_quality_report(validated: pd.DataFrame) -> pd.DataFrame:
    """Summarize quality per source file, plus an ``ALL`` total row."""
    if validated.empty:
        return pd.DataFrame(columns=QUALITY_COLUMNS)

    rows: list[dict[str, object]] = []
    for source_file, group in validated.groupby("source_file", sort=True):
        rows.append({"source_file": source_file, **_count(group)})

    if len(rows) > 1:
        rows.append({"source_file": "ALL", **_count(validated)})

    return pd.DataFrame(rows, columns=QUALITY_COLUMNS)


def quality_issues(validated: pd.DataFrame) -> pd.DataFrame:
    """Return every rejected row with its original values and explanation."""
    columns = [
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
    if validated.empty:
        return pd.DataFrame(columns=columns)

    rejected = validated[validated["status"].ne(STATUS_VALID)].copy()
    return rejected[columns].sort_values(["source_file", "source_row"]).reset_index(drop=True)
