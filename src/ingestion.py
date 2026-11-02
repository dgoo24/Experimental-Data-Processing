"""CSV ingestion for optical polarization measurements.

Input files are read as text so that malformed values are preserved for the
data-quality report.  The caller receives a DataFrame containing the original
text plus the source file name and source row number.  Nothing in ``data/raw``
is modified or deleted.
"""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = [
    "experiment_id",
    "sample_id",
    "measurement_angle",
    "observed_rotation",
    "measurement_timestamp",
]

METADATA_COLUMNS = ["source_file", "source_row"]


class CSVFormatError(ValueError):
    """Raised when an input file cannot be used as a measurements file."""


@dataclass(frozen=True)
class SourceFile:
    """An input file that was read during this run."""

    path: Path
    sha256: str
    row_count: int

    @property
    def name(self) -> str:
        return self.path.name


def sha256_file(path: Path) -> str:
    """Return the SHA-256 checksum of a file without changing it."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover_csv_files(input_dir: Path) -> list[Path]:
    """Return CSV files in a directory, sorted for deterministic processing."""
    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory does not exist: {input_dir}")
    if not input_dir.is_dir():
        raise NotADirectoryError(f"Input path is not a directory: {input_dir}")

    files = sorted(
        path for path in input_dir.iterdir() if path.is_file() and path.suffix.lower() == ".csv"
    )
    if not files:
        raise FileNotFoundError(f"No CSV files found in {input_dir}")
    return files


def _read_header(path: Path) -> list[str]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader, None)
    except UnicodeDecodeError as exc:
        raise CSVFormatError(f"{path.name}: file is not valid UTF-8 text") from exc

    if not header:
        raise CSVFormatError(f"{path.name}: file is empty")

    columns = [name.strip() for name in header]
    if any(not name for name in columns):
        raise CSVFormatError(f"{path.name}: header contains an empty column name")

    duplicates = sorted({name for name in columns if columns.count(name) > 1})
    if duplicates:
        raise CSVFormatError(
            f"{path.name}: duplicate column(s) in header: {', '.join(duplicates)}"
        )

    missing = [name for name in REQUIRED_COLUMNS if name not in columns]
    if missing:
        raise CSVFormatError(
            f"{path.name}: missing required column(s): {', '.join(missing)}. "
            f"Required columns are: {', '.join(REQUIRED_COLUMNS)}"
        )
    return columns


def read_measurements_csv(path: Path) -> pd.DataFrame:
    """Read one CSV file, preserving raw text and row provenance.

    Extra columns are allowed and kept in the returned DataFrame for this run.
    They are not stored in the relational database; the original CSV remains the
    authoritative copy of the source file.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file does not exist: {path}")

    columns = _read_header(path)
    try:
        frame = pd.read_csv(
            path,
            dtype=str,
            keep_default_na=False,
            na_filter=False,
            encoding="utf-8-sig",
        )
    except pd.errors.EmptyDataError as exc:
        raise CSVFormatError(f"{path.name}: file is empty") from exc
    except pd.errors.ParserError as exc:
        raise CSVFormatError(f"{path.name}: could not parse CSV: {exc}") from exc

    frame.columns = columns
    if frame.empty:
        raise CSVFormatError(f"{path.name}: header is present but there are no data rows")

    frame = frame.reset_index(drop=True)
    frame["source_file"] = path.name
    frame["source_row"] = frame.index + 2  # line 1 is the header
    return frame


def load_input_files(input_dir: Path) -> tuple[pd.DataFrame, list[SourceFile]]:
    """Read every CSV in ``input_dir`` and return one combined DataFrame.

    A malformed file stops the run with a clear error.  Valid rows are never
    dropped here; validation and quarantine happen in :mod:`src.validation`.
    """
    frames: list[pd.DataFrame] = []
    sources: list[SourceFile] = []

    for path in discover_csv_files(Path(input_dir)):
        frame = read_measurements_csv(path)
        frames.append(frame)
        sources.append(
            SourceFile(path=path, sha256=sha256_file(path), row_count=len(frame))
        )

    combined = pd.concat(frames, ignore_index=True, sort=False)
    return combined, sources
