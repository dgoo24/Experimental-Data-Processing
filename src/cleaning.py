"""Cleaning: select valid rows without discarding the source evidence.

The raw rows and their validation status live in the database and in the
quality report.  This module only builds the clean, typed measurement table used
for statistics and plotting.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .validation import STATUS_VALID, validate_measurements

PROCESSED_COLUMNS = [
    "experiment_id",
    "sample_id",
    "measurement_angle",
    "observed_rotation",
    "measurement_timestamp",
    "source_file",
    "source_row",
]


def select_valid_measurements(validated: pd.DataFrame) -> pd.DataFrame:
    """Return typed rows whose validation status is ``valid``.

    The returned frame is sorted by experiment, sample, timestamp and angle so
    that CSV output and reports are reproducible.
    """
    required = {
        "status",
        "experiment_id_value",
        "sample_id_value",
        "measurement_angle_value",
        "observed_rotation_value",
        "measurement_timestamp_value",
        "source_file",
        "source_row",
    }
    missing = sorted(required - set(validated.columns))
    if missing:
        raise ValueError(f"validated input is missing column(s): {', '.join(missing)}")

    selected = validated[validated["status"].eq(STATUS_VALID)].copy()
    processed = pd.DataFrame(
        {
            "experiment_id": selected["experiment_id_value"].astype(str),
            "sample_id": selected["sample_id_value"].astype(str),
            "measurement_angle": selected["measurement_angle_value"].astype(float),
            "observed_rotation": selected["observed_rotation_value"].astype(float),
            "measurement_timestamp": pd.to_datetime(
                selected["measurement_timestamp_value"]
            ),
            "source_file": selected["source_file"].astype(str),
            "source_row": selected["source_row"].astype(int),
        }
    )

    return (
        processed.sort_values(
            ["experiment_id", "sample_id", "measurement_timestamp", "measurement_angle"],
            kind="stable",
        )
        .reset_index(drop=True)[PROCESSED_COLUMNS]
    )


def clean_measurements(
    frame: pd.DataFrame,
    config=None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Convenience wrapper: validate a raw frame and return validated + clean."""
    validated = validate_measurements(frame, config=config)
    return validated, select_valid_measurements(validated)


def export_processed_measurements(processed: pd.DataFrame, path: Path) -> Path:
    """Write the clean measurement table as UTF-8 CSV and return its path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    processed.to_csv(path, index=False, encoding="utf-8")
    return path
