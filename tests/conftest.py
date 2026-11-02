from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.cleaning import select_valid_measurements
from src.database import get_engine, init_db
from src.ingestion import read_measurements_csv
from src.validation import validate_measurements

VALID_CSV = """experiment_id,sample_id,measurement_angle,observed_rotation,measurement_timestamp
EXP-001,S-01,0,2,2026-01-01T10:00:00Z
EXP-001,S-01,10,32,2026-01-01T10:01:00Z
EXP-001,S-01,20,62,2026-01-01T10:02:00Z
EXP-001,S-01,30,92,2026-01-01T10:03:00Z
EXP-001,S-01,40,122,2026-01-01T10:04:00Z
EXP-001,S-01,50,152,2026-01-01T10:05:00Z
EXP-002,S-02,0,5,2026-01-02T10:00:00Z
EXP-002,S-02,10,0,2026-01-02T10:01:00Z
EXP-002,S-02,20,-5,2026-01-02T10:02:00Z
EXP-002,S-02,30,-10,2026-01-02T10:03:00Z
"""


@pytest.fixture
def write_csv(tmp_path: Path):
    def _write(content: str, name: str = "measurements.csv") -> Path:
        path = tmp_path / name
        path.write_text(content, encoding="utf-8")
        return path

    return _write


@pytest.fixture
def make_raw():
    def _make(rows: list[dict[str, object]], source_file: str = "test.csv") -> pd.DataFrame:
        frame = pd.DataFrame(rows)
        frame["source_file"] = source_file
        frame["source_row"] = range(2, len(frame) + 2)
        return frame

    return _make


@pytest.fixture
def valid_csv_file(tmp_path: Path) -> Path:
    path = tmp_path / "measurements.csv"
    path.write_text(VALID_CSV, encoding="utf-8")
    return path


@pytest.fixture
def raw_frame(valid_csv_file: Path) -> pd.DataFrame:
    return read_measurements_csv(valid_csv_file)


@pytest.fixture
def validated_frame(raw_frame: pd.DataFrame) -> pd.DataFrame:
    return validate_measurements(raw_frame)


@pytest.fixture
def processed_frame(validated_frame: pd.DataFrame) -> pd.DataFrame:
    return select_valid_measurements(validated_frame)


@pytest.fixture
def sqlite_engine():
    engine = get_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    yield engine
    engine.dispose()
