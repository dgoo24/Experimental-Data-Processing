"""Small SQLAlchemy persistence layer.

The schema has six tables:

``experiments``, ``samples``, ``imports``, ``raw_measurements``,
``processed_measurements`` and ``regression_results``.

Raw rows are retained with their validation status.  Processed rows contain only
clean, typed measurements.  ``Base.metadata.create_all`` is used instead of
Alembic because this project has a single, small schema and no migration history
yet; see the README for the trade-off.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
    func,
    select,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.pool import StaticPool

from .config import DB_CONNECT_TIMEOUT, DEFAULT_DATABASE_URL
from .ingestion import SourceFile
from .validation import STATUS_DUPLICATE, STATUS_INVALID, STATUS_VALID


class DatabaseOperationError(RuntimeError):
    """Raised when a database operation cannot be completed."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Experiment(Base):
    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    experiment_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)


class Sample(Base):
    __tablename__ = "samples"
    __table_args__ = (
        UniqueConstraint("experiment_id", "sample_id", name="uq_samples_experiment_sample"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    experiment_id: Mapped[int] = mapped_column(
        ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sample_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)


class ImportRecord(Base):
    __tablename__ = "imports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_file: Mapped[str] = mapped_column(String(512), nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    n_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    n_valid: Mapped[int] = mapped_column(Integer, nullable=False)
    n_invalid: Mapped[int] = mapped_column(Integer, nullable=False)
    n_duplicates: Mapped[int] = mapped_column(Integer, nullable=False)


class RawMeasurement(Base):
    __tablename__ = "raw_measurements"
    __table_args__ = (
        CheckConstraint(
            "status IN ('valid', 'invalid', 'duplicate')",
            name="ck_raw_measurements_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    import_id: Mapped[int] = mapped_column(
        ForeignKey("imports.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_row: Mapped[int] = mapped_column(Integer, nullable=False)
    experiment_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sample_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    measurement_angle: Mapped[str] = mapped_column(Text, nullable=False, default="")
    observed_rotation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    measurement_timestamp: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    validation_errors: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)


class ProcessedMeasurement(Base):
    __tablename__ = "processed_measurements"
    __table_args__ = (
        UniqueConstraint(
            "experiment_id",
            "sample_id",
            "measurement_angle",
            "measurement_timestamp",
            name="uq_processed_measurement_point",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    raw_measurement_id: Mapped[int] = mapped_column(
        ForeignKey("raw_measurements.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    experiment_id: Mapped[int] = mapped_column(
        ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sample_id: Mapped[int] = mapped_column(
        ForeignKey("samples.id", ondelete="CASCADE"), nullable=False, index=True
    )
    measurement_angle: Mapped[float] = mapped_column(Float, nullable=False)
    observed_rotation: Mapped[float] = mapped_column(Float, nullable=False)
    measurement_timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)


class RegressionResult(Base):
    __tablename__ = "regression_results"
    __table_args__ = (
        UniqueConstraint("experiment_id", "sample_id", name="uq_regression_experiment_sample"),
        CheckConstraint("n_points >= 2", name="ck_regression_n_points"),
        CheckConstraint(
            "r_squared IS NULL OR (r_squared >= 0.0 AND r_squared <= 1.0)",
            name="ck_regression_r_squared",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    experiment_id: Mapped[int] = mapped_column(
        ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sample_id: Mapped[int] = mapped_column(
        ForeignKey("samples.id", ondelete="CASCADE"), nullable=False, index=True
    )
    n_points: Mapped[int] = mapped_column(Integer, nullable=False)
    slope: Mapped[float] = mapped_column(Float, nullable=False)
    intercept: Mapped[float] = mapped_column(Float, nullable=False)
    r_squared: Mapped[float | None] = mapped_column(Float, nullable=True)
    slope_std_error: Mapped[float | None] = mapped_column(Float, nullable=True)
    intercept_std_error: Mapped[float | None] = mapped_column(Float, nullable=True)
    residual_std_error: Mapped[float | None] = mapped_column(Float, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)


@dataclass
class ImportOutcome:
    source_file: str
    status: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    duplicate_rows: int
    stored_processed: int
    already_stored: int


@dataclass
class RegressionStoreResult:
    stored: int
    skipped: list[dict[str, object]]


def get_engine(
    database_url: str | None = None,
    echo: bool = False,
    connect_timeout: int | None = None,
) -> Engine:
    """Create an engine for PostgreSQL (default) or SQLite (tests/offline use).

    PostgreSQL connections use a short connect timeout (``DB_CONNECT_TIMEOUT``,
    default 3 s) so an unreachable server fails fast instead of blocking the
    caller - and with it the Streamlit script - for minutes.
    """
    url = database_url or DEFAULT_DATABASE_URL
    options: dict[str, object] = {"echo": echo}

    if url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url:
            options["poolclass"] = StaticPool
    else:
        options["connect_args"] = {"connect_timeout": connect_timeout or DB_CONNECT_TIMEOUT}

    engine = create_engine(url, **options)

    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def check_connection(engine: Engine) -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def _get_or_create_experiment(session: Session, experiment_code: str) -> Experiment:
    code = experiment_code.strip()
    if not code:
        raise DatabaseOperationError("experiment_id cannot be empty")
    experiment = session.scalar(select(Experiment).where(Experiment.experiment_id == code))
    if experiment is None:
        experiment = Experiment(experiment_id=code)
        session.add(experiment)
        session.flush()
    return experiment


def _get_or_create_sample(session: Session, experiment: Experiment, sample_code: str) -> Sample:
    code = sample_code.strip()
    if not code:
        raise DatabaseOperationError("sample_id cannot be empty")
    sample = session.scalar(
        select(Sample).where(
            Sample.experiment_id == experiment.id,
            Sample.sample_id == code,
        )
    )
    if sample is None:
        sample = Sample(experiment_id=experiment.id, sample_id=code)
        session.add(sample)
        session.flush()
    return sample


def _normalize_timestamp(value: object) -> datetime | None:
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp):
        return None
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert("UTC").tz_localize(None)
    return timestamp.to_pydatetime()


def _measurement_key(
    experiment_code: str,
    sample_code: str,
    angle: float,
    timestamp: datetime,
) -> tuple[str, str, float, datetime]:
    return (
        str(experiment_code).strip(),
        str(sample_code).strip(),
        round(float(angle), 9),
        _normalize_timestamp(timestamp),
    )


def _existing_measurement_keys(session: Session) -> set[tuple[str, str, float, datetime]]:
    rows = session.execute(
        select(
            Experiment.experiment_id,
            Sample.sample_id,
            ProcessedMeasurement.measurement_angle,
            ProcessedMeasurement.measurement_timestamp,
        )
        .join(Sample, Sample.experiment_id == Experiment.id)
        .join(ProcessedMeasurement, ProcessedMeasurement.sample_id == Sample.id)
    ).all()
    return {
        _measurement_key(experiment_code, sample_code, angle, timestamp)
        for experiment_code, sample_code, angle, timestamp in rows
    }


def persist_dataset(
    engine: Engine,
    validated: pd.DataFrame,
    sources: list[SourceFile],
) -> list[ImportOutcome]:
    """Store raw rows and clean processed rows, one transaction per source file.

    Importing an unchanged file again is skipped based on its SHA-256 checksum.
    A changed file is read again, but measurement points already in the database
    are not duplicated.
    """
    outcomes: list[ImportOutcome] = []

    required = {
        "source_file",
        "source_row",
        "status",
        "experiment_id",
        "sample_id",
        "measurement_angle",
        "observed_rotation",
        "measurement_timestamp",
        "experiment_id_value",
        "sample_id_value",
        "measurement_angle_value",
        "observed_rotation_value",
        "measurement_timestamp_value",
        "validation_errors",
    }
    missing = sorted(required - set(validated.columns))
    if missing:
        raise DatabaseOperationError(
            f"validated data is missing column(s): {', '.join(missing)}"
        )

    for source in sources:
        subset = validated[validated["source_file"] == source.name]
        valid_count = int(subset["status"].eq(STATUS_VALID).sum())
        invalid_count = int(subset["status"].eq(STATUS_INVALID).sum())
        duplicate_count = int(subset["status"].eq(STATUS_DUPLICATE).sum())

        try:
            with Session(engine) as session:
                existing_import = session.scalar(
                    select(ImportRecord).where(
                        ImportRecord.file_sha256 == source.sha256
                    )
                )
                if existing_import is not None:
                    outcomes.append(
                        ImportOutcome(
                            source_file=source.name,
                            status="skipped_existing_file",
                            total_rows=len(subset),
                            valid_rows=valid_count,
                            invalid_rows=invalid_count,
                            duplicate_rows=duplicate_count,
                            stored_processed=0,
                            already_stored=0,
                        )
                    )
                    continue

                import_record = ImportRecord(
                    source_file=str(source.path),
                    file_sha256=source.sha256,
                    n_rows=len(subset),
                    n_valid=valid_count,
                    n_invalid=invalid_count,
                    n_duplicates=duplicate_count,
                )
                session.add(import_record)
                session.flush()

                raw_rows: list[tuple[RawMeasurement, object]] = []
                for row in subset.itertuples(index=False):
                    raw = RawMeasurement(
                        import_id=import_record.id,
                        source_row=int(row.source_row),
                        experiment_id=str(row.experiment_id),
                        sample_id=str(row.sample_id),
                        measurement_angle=str(row.measurement_angle),
                        observed_rotation=str(row.observed_rotation),
                        measurement_timestamp=str(row.measurement_timestamp),
                        status=str(row.status),
                        validation_errors=str(row.validation_errors),
                    )
                    session.add(raw)
                    raw_rows.append((raw, row))
                session.flush()

                existing_keys = _existing_measurement_keys(session)
                stored = 0
                already_stored = 0

                for raw, row in raw_rows:
                    if row.status != STATUS_VALID:
                        continue

                    timestamp = _normalize_timestamp(row.measurement_timestamp_value)
                    if timestamp is None:
                        continue

                    experiment_code = str(row.experiment_id_value)
                    sample_code = str(row.sample_id_value)
                    angle = float(row.measurement_angle_value)
                    key = _measurement_key(experiment_code, sample_code, angle, timestamp)
                    if key in existing_keys:
                        already_stored += 1
                        continue

                    experiment = _get_or_create_experiment(session, experiment_code)
                    sample = _get_or_create_sample(session, experiment, sample_code)
                    session.add(
                        ProcessedMeasurement(
                            raw_measurement_id=raw.id,
                            experiment_id=experiment.id,
                            sample_id=sample.id,
                            measurement_angle=angle,
                            observed_rotation=float(row.observed_rotation_value),
                            measurement_timestamp=timestamp,
                        )
                    )
                    existing_keys.add(key)
                    stored += 1

                session.commit()
                outcomes.append(
                    ImportOutcome(
                        source_file=source.name,
                        status="imported",
                        total_rows=len(subset),
                        valid_rows=valid_count,
                        invalid_rows=invalid_count,
                        duplicate_rows=duplicate_count,
                        stored_processed=stored,
                        already_stored=already_stored,
                    )
                )
        except Exception as exc:
            raise DatabaseOperationError(
                f"failed to store {source.name}: {exc}"
            ) from exc

    return outcomes


def _finite_or_none(value: object) -> float | None:
    number = float(value)
    return number if pd.notna(number) and abs(number) != float("inf") else None


def store_regression_results(engine: Engine, regressions: pd.DataFrame) -> RegressionStoreResult:
    """Insert or update one regression result per experiment/sample."""
    if regressions.empty:
        return RegressionStoreResult(stored=0, skipped=[])

    stored = 0
    skipped: list[dict[str, object]] = []

    with Session(engine) as session:
        for row in regressions.itertuples(index=False):
            experiment = session.scalar(
                select(Experiment).where(Experiment.experiment_id == str(row.experiment_id))
            )
            sample = None
            if experiment is not None:
                sample = session.scalar(
                    select(Sample).where(
                        Sample.experiment_id == experiment.id,
                        Sample.sample_id == str(row.sample_id),
                    )
                )

            if experiment is None or sample is None:
                skipped.append(
                    {
                        "experiment_id": row.experiment_id,
                        "sample_id": row.sample_id,
                        "reason": "experiment/sample not found in database",
                    }
                )
                continue

            result = session.scalar(
                select(RegressionResult).where(
                    RegressionResult.experiment_id == experiment.id,
                    RegressionResult.sample_id == sample.id,
                )
            )
            if result is None:
                result = RegressionResult(
                    experiment_id=experiment.id,
                    sample_id=sample.id,
                    n_points=int(row.n_points),
                    slope=float(row.slope),
                    intercept=float(row.intercept),
                    r_squared=_finite_or_none(row.r_squared),
                    slope_std_error=_finite_or_none(row.slope_std_error),
                    intercept_std_error=_finite_or_none(row.intercept_std_error),
                    residual_std_error=_finite_or_none(row.residual_std_error),
                )
                session.add(result)
            else:
                result.n_points = int(row.n_points)
                result.slope = float(row.slope)
                result.intercept = float(row.intercept)
                result.r_squared = _finite_or_none(row.r_squared)
                result.slope_std_error = _finite_or_none(row.slope_std_error)
                result.intercept_std_error = _finite_or_none(row.intercept_std_error)
                result.residual_std_error = _finite_or_none(row.residual_std_error)
                result.computed_at = _utcnow()
            stored += 1

        session.commit()

    return RegressionStoreResult(stored=stored, skipped=skipped)


def fetch_measurements(
    engine: Engine,
    experiment_code: str | None = None,
) -> pd.DataFrame:
    """Return stored clean measurements as a DataFrame."""
    statement = (
        select(
            Experiment.experiment_id,
            Sample.sample_id,
            ProcessedMeasurement.measurement_angle,
            ProcessedMeasurement.observed_rotation,
            ProcessedMeasurement.measurement_timestamp,
        )
        .join(Sample, Sample.experiment_id == Experiment.id)
        .join(ProcessedMeasurement, ProcessedMeasurement.sample_id == Sample.id)
        .order_by(
            Experiment.experiment_id,
            Sample.sample_id,
            ProcessedMeasurement.measurement_timestamp,
            ProcessedMeasurement.measurement_angle,
        )
    )
    if experiment_code:
        statement = statement.where(Experiment.experiment_id == experiment_code)

    with engine.connect() as connection:
        rows = connection.execute(statement).all()

    return pd.DataFrame(
        rows,
        columns=[
            "experiment_id",
            "sample_id",
            "measurement_angle",
            "observed_rotation",
            "measurement_timestamp",
        ],
    )


def fetch_regression_results(
    engine: Engine,
    experiment_code: str | None = None,
) -> pd.DataFrame:
    """Return stored regression results as a DataFrame."""
    statement = (
        select(
            Experiment.experiment_id,
            Sample.sample_id,
            RegressionResult.n_points,
            RegressionResult.slope,
            RegressionResult.intercept,
            RegressionResult.r_squared,
            RegressionResult.slope_std_error,
            RegressionResult.intercept_std_error,
            RegressionResult.residual_std_error,
            RegressionResult.computed_at,
        )
        .join(Sample, Sample.experiment_id == Experiment.id)
        .join(RegressionResult, RegressionResult.sample_id == Sample.id)
        .order_by(Experiment.experiment_id, Sample.sample_id)
    )
    if experiment_code:
        statement = statement.where(Experiment.experiment_id == experiment_code)

    with engine.connect() as connection:
        rows = connection.execute(statement).all()

    return pd.DataFrame(
        rows,
        columns=[
            "experiment_id",
            "sample_id",
            "n_points",
            "slope",
            "intercept",
            "r_squared",
            "slope_std_error",
            "intercept_std_error",
            "residual_std_error",
            "computed_at",
        ],
    )


def fetch_import_history(engine: Engine) -> pd.DataFrame:
    """Return import history, newest first."""
    statement = select(
        ImportRecord.source_file,
        ImportRecord.file_sha256,
        ImportRecord.imported_at,
        ImportRecord.n_rows,
        ImportRecord.n_valid,
        ImportRecord.n_invalid,
        ImportRecord.n_duplicates,
    ).order_by(ImportRecord.imported_at.desc(), ImportRecord.id.desc())

    with engine.connect() as connection:
        rows = connection.execute(statement).all()

    return pd.DataFrame(
        rows,
        columns=[
            "source_file",
            "file_sha256",
            "imported_at",
            "n_rows",
            "n_valid",
            "n_invalid",
            "n_duplicates",
        ],
    )


def fetch_quality_issues(engine: Engine) -> pd.DataFrame:
    """Return retained raw rows that are invalid or duplicates."""
    statement = (
        select(
            ImportRecord.source_file,
            RawMeasurement.source_row,
            RawMeasurement.status,
            RawMeasurement.experiment_id,
            RawMeasurement.sample_id,
            RawMeasurement.measurement_angle,
            RawMeasurement.observed_rotation,
            RawMeasurement.measurement_timestamp,
            RawMeasurement.validation_errors,
        )
        .join(ImportRecord, ImportRecord.id == RawMeasurement.import_id)
        .where(RawMeasurement.status != STATUS_VALID)
        .order_by(ImportRecord.id, RawMeasurement.source_row)
    )

    with engine.connect() as connection:
        rows = connection.execute(statement).all()

    return pd.DataFrame(
        rows,
        columns=[
            "source_file",
            "source_row",
            "status",
            "experiment_id",
            "sample_id",
            "measurement_angle",
            "observed_rotation",
            "measurement_timestamp",
            "validation_errors",
        ],
    )


def database_summary(engine: Engine) -> dict[str, int]:
    """Return row counts for the main tables."""
    with Session(engine) as session:
        return {
            "experiments": int(session.scalar(select(func.count()).select_from(Experiment)) or 0),
            "samples": int(session.scalar(select(func.count()).select_from(Sample)) or 0),
            "imports": int(session.scalar(select(func.count()).select_from(ImportRecord)) or 0),
            "raw_measurements": int(
                session.scalar(select(func.count()).select_from(RawMeasurement)) or 0
            ),
            "processed_measurements": int(
                session.scalar(select(func.count()).select_from(ProcessedMeasurement)) or 0
            ),
            "regression_results": int(
                session.scalar(select(func.count()).select_from(RegressionResult)) or 0
            ),
        }
