from __future__ import annotations

import pandas as pd

from src.database import database_summary, fetch_regression_results, get_engine
from src.main import main

from .conftest import VALID_CSV


def _write_inputs(tmp_path):
    input_dir = tmp_path / "raw"
    input_dir.mkdir()
    (input_dir / "measurements.csv").write_text(VALID_CSV, encoding="utf-8")
    (input_dir / "issues.csv").write_text(
        "experiment_id,sample_id,measurement_angle,observed_rotation,measurement_timestamp\n"
        "EXP-001,S-01,999,1.0,2026-01-03T10:00:00Z\n",
        encoding="utf-8",
    )
    return input_dir


def test_process_end_to_end_with_sqlite(tmp_path):
    input_dir = _write_inputs(tmp_path)
    output_dir = tmp_path / "output"
    processed_dir = tmp_path / "processed"
    db_path = tmp_path / "lab.db"
    database_url = f"sqlite:///{db_path.as_posix()}"

    exit_code = main(
        [
            "process",
            "--input",
            str(input_dir),
            "--output",
            str(output_dir),
            "--processed-dir",
            str(processed_dir),
            "--database-url",
            database_url,
        ]
    )

    assert exit_code == 0
    assert (processed_dir / "processed_measurements.csv").exists()
    assert (output_dir / "reports" / "summary.md").exists()
    assert (output_dir / "reports" / "regression_results.csv").exists()
    assert (output_dir / "plots" / "rotation_vs_angle.png").exists()
    assert (output_dir / "reports" / "quality_issues.csv").exists()

    engine = get_engine(database_url)
    summary = database_summary(engine)
    assert summary["experiments"] == 2
    assert summary["raw_measurements"] == 11
    assert summary["processed_measurements"] == 10
    assert summary["regression_results"] == 2
    assert len(fetch_regression_results(engine)) == 2

    clean = pd.read_csv(processed_dir / "processed_measurements.csv")
    assert len(clean) == 10
    assert list(clean.columns[:5]) == [
        "experiment_id",
        "sample_id",
        "measurement_angle",
        "observed_rotation",
        "measurement_timestamp",
    ]


def test_repeated_process_is_idempotent(tmp_path):
    input_dir = _write_inputs(tmp_path)
    output_dir = tmp_path / "output"
    processed_dir = tmp_path / "processed"
    db_path = tmp_path / "lab.db"
    database_url = f"sqlite:///{db_path.as_posix()}"

    args = [
        "process",
        "--input",
        str(input_dir),
        "--output",
        str(output_dir),
        "--processed-dir",
        str(processed_dir),
        "--database-url",
        database_url,
    ]
    assert main(args) == 0
    assert main(args) == 0

    engine = get_engine(database_url)
    summary = database_summary(engine)
    assert summary["raw_measurements"] == 11
    assert summary["processed_measurements"] == 10
    assert summary["imports"] == 2
    assert summary["regression_results"] == 2


def test_process_with_skip_db(tmp_path):
    input_dir = _write_inputs(tmp_path)
    output_dir = tmp_path / "output"
    processed_dir = tmp_path / "processed"

    exit_code = main(
        [
            "process",
            "--input",
            str(input_dir),
            "--output",
            str(output_dir),
            "--processed-dir",
            str(processed_dir),
            "--skip-db",
        ]
    )

    assert exit_code == 0
    assert (output_dir / "reports" / "regression_results.csv").exists()
    assert (processed_dir / "processed_measurements.csv").exists()


def test_init_db_command(tmp_path):
    db_path = tmp_path / "empty.db"
    exit_code = main(
        ["init-db", "--database-url", f"sqlite:///{db_path.as_posix()}"]
    )

    assert exit_code == 0
    engine = get_engine(f"sqlite:///{db_path.as_posix()}")
    assert database_summary(engine)["experiments"] == 0
