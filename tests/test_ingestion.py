from __future__ import annotations

import pandas as pd
import pytest

from src.ingestion import (
    REQUIRED_COLUMNS,
    CSVFormatError,
    discover_csv_files,
    load_input_files,
    read_measurements_csv,
    sha256_file,
)

from .conftest import VALID_CSV


def test_read_valid_csv_preserves_text_and_provenance(valid_csv_file):
    frame = read_measurements_csv(valid_csv_file)

    assert list(frame.columns[:5]) == REQUIRED_COLUMNS
    assert len(frame) == 10
    assert frame.loc[0, "experiment_id"] == "EXP-001"
    assert frame.loc[0, "measurement_angle"] == "0"
    assert frame.loc[0, "source_file"] == "measurements.csv"
    assert frame.loc[0, "source_row"] == 2
    assert frame.loc[9, "source_row"] == 11


def test_missing_required_column_is_rejected(write_csv):
    path = write_csv(
        "experiment_id,sample_id,measurement_angle,measurement_timestamp\n"
        "EXP-1,S-1,0,2026-01-01T00:00:00Z\n"
    )

    with pytest.raises(CSVFormatError, match="missing required column"):
        read_measurements_csv(path)


def test_duplicate_header_is_rejected(write_csv):
    path = write_csv(
        "experiment_id,sample_id,measurement_angle,observed_rotation,"
        "measurement_timestamp,observed_rotation\n"
    )

    with pytest.raises(CSVFormatError, match="duplicate column"):
        read_measurements_csv(path)


def test_header_without_rows_is_rejected(write_csv):
    path = write_csv(
        "experiment_id,sample_id,measurement_angle,observed_rotation,measurement_timestamp\n"
    )

    with pytest.raises(CSVFormatError, match="no data rows"):
        read_measurements_csv(path)


def test_extra_columns_are_kept_for_the_run(write_csv):
    path = write_csv(
        "experiment_id,sample_id,measurement_angle,observed_rotation,"
        "measurement_timestamp,operator\n"
        "EXP-1,S-1,0,1.5,2026-01-01T00:00:00Z,AB\n"
    )

    frame = read_measurements_csv(path)

    assert frame.loc[0, "operator"] == "AB"


def test_discover_and_load_multiple_files(write_csv):
    write_csv(
        "experiment_id,sample_id,measurement_angle,observed_rotation,measurement_timestamp\n"
        "EXP-2,S-2,0,1,2026-01-02T00:00:00Z\n",
        name="b.csv",
    )
    write_csv(
        "experiment_id,sample_id,measurement_angle,observed_rotation,measurement_timestamp\n"
        "EXP-1,S-1,0,1,2026-01-01T00:00:00Z\n",
        name="a.csv",
    )
    write_csv("not a measurement file", name="notes.txt")

    files = discover_csv_files(write_csv(VALID_CSV, name="c.csv").parent)
    assert [path.name for path in files] == ["a.csv", "b.csv", "c.csv"]

    combined, sources = load_input_files(files[0].parent)
    assert len(combined) == 12
    assert [source.name for source in sources] == ["a.csv", "b.csv", "c.csv"]
    assert all(source.sha256 for source in sources)


def test_checksum_changes_when_content_changes(write_csv):
    path = write_csv(VALID_CSV)
    first = sha256_file(path)
    path.write_text(VALID_CSV + "\n", encoding="utf-8")
    second = sha256_file(path)
    assert first != second


def test_input_directory_must_exist(tmp_path):
    with pytest.raises(FileNotFoundError, match="does not exist"):
        discover_csv_files(tmp_path / "missing")


def test_source_row_is_an_integer_column(valid_csv_file):
    frame = read_measurements_csv(valid_csv_file)
    assert pd.api.types.is_integer_dtype(frame["source_row"])
