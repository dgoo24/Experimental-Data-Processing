-- Reference schema for the PostgreSQL database.
--
-- The application creates the same tables with SQLAlchemy
-- (Base.metadata.create_all) when `python -m src.main init-db` or
-- `python -m src.main process` runs. This file is provided for inspection and
-- for manual database setup. It is not used automatically, so schema changes
-- must be made in src/database.py as well.

CREATE TABLE IF NOT EXISTS experiments (
    id              SERIAL PRIMARY KEY,
    experiment_id   VARCHAR(64) NOT NULL UNIQUE,
    title           VARCHAR(255),
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS samples (
    id              SERIAL PRIMARY KEY,
    experiment_id   INTEGER NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
    sample_id       VARCHAR(64) NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_samples_experiment_sample UNIQUE (experiment_id, sample_id)
);

CREATE TABLE IF NOT EXISTS imports (
    id              SERIAL PRIMARY KEY,
    source_file     VARCHAR(512) NOT NULL,
    file_sha256     VARCHAR(64) NOT NULL UNIQUE,
    imported_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    n_rows          INTEGER NOT NULL,
    n_valid         INTEGER NOT NULL,
    n_invalid       INTEGER NOT NULL,
    n_duplicates    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS raw_measurements (
    id                      SERIAL PRIMARY KEY,
    import_id               INTEGER NOT NULL REFERENCES imports(id) ON DELETE CASCADE,
    source_row              INTEGER NOT NULL,
    experiment_id           TEXT NOT NULL DEFAULT '',
    sample_id               TEXT NOT NULL DEFAULT '',
    measurement_angle       TEXT NOT NULL DEFAULT '',
    observed_rotation       TEXT NOT NULL DEFAULT '',
    measurement_timestamp   TEXT NOT NULL DEFAULT '',
    status                  VARCHAR(16) NOT NULL,
    validation_errors       TEXT NOT NULL DEFAULT '',
    created_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_raw_measurements_status
        CHECK (status IN ('valid', 'invalid', 'duplicate'))
);

CREATE TABLE IF NOT EXISTS processed_measurements (
    id                      SERIAL PRIMARY KEY,
    raw_measurement_id      INTEGER NOT NULL UNIQUE
                                REFERENCES raw_measurements(id) ON DELETE CASCADE,
    experiment_id           INTEGER NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
    sample_id               INTEGER NOT NULL REFERENCES samples(id) ON DELETE CASCADE,
    measurement_angle       DOUBLE PRECISION NOT NULL,
    observed_rotation       DOUBLE PRECISION NOT NULL,
    measurement_timestamp   TIMESTAMP NOT NULL,
    created_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_processed_measurement_point
        UNIQUE (experiment_id, sample_id, measurement_angle, measurement_timestamp)
);

CREATE TABLE IF NOT EXISTS regression_results (
    id                      SERIAL PRIMARY KEY,
    experiment_id           INTEGER NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
    sample_id               INTEGER NOT NULL REFERENCES samples(id) ON DELETE CASCADE,
    n_points                INTEGER NOT NULL,
    slope                   DOUBLE PRECISION NOT NULL,
    intercept               DOUBLE PRECISION NOT NULL,
    r_squared               DOUBLE PRECISION,
    slope_std_error         DOUBLE PRECISION,
    intercept_std_error     DOUBLE PRECISION,
    residual_std_error      DOUBLE PRECISION,
    computed_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_regression_experiment_sample UNIQUE (experiment_id, sample_id),
    CONSTRAINT ck_regression_n_points CHECK (n_points >= 2),
    CONSTRAINT ck_regression_r_squared
        CHECK (r_squared IS NULL OR (r_squared >= 0.0 AND r_squared <= 1.0))
);

CREATE INDEX IF NOT EXISTS ix_experiments_experiment_id
    ON experiments (experiment_id);
CREATE INDEX IF NOT EXISTS ix_samples_experiment_id
    ON samples (experiment_id);
CREATE INDEX IF NOT EXISTS ix_imports_file_sha256
    ON imports (file_sha256);
CREATE INDEX IF NOT EXISTS ix_raw_measurements_import_id
    ON raw_measurements (import_id);
CREATE INDEX IF NOT EXISTS ix_raw_measurements_status
    ON raw_measurements (status);
CREATE INDEX IF NOT EXISTS ix_processed_measurements_experiment_id
    ON processed_measurements (experiment_id);
CREATE INDEX IF NOT EXISTS ix_processed_measurements_sample_id
    ON processed_measurements (sample_id);
CREATE INDEX IF NOT EXISTS ix_regression_results_experiment_id
    ON regression_results (experiment_id);
CREATE INDEX IF NOT EXISTS ix_regression_results_sample_id
    ON regression_results (sample_id);
