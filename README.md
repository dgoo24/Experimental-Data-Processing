# Experimental Data Processing and Analysis Tool

A small Python application for a university physics laboratory working with
optical polarization measurements. It replaces manual spreadsheet cleaning with
one reproducible command:

```text
CSV files -> validation/cleaning -> PostgreSQL -> statistics -> plots/reports
```

The project is intentionally small: a command-line interface, one PostgreSQL
container, a handful of Python modules and a pytest suite. There is no web
framework, task scheduler, message broker, or containerized Python service.

> **Synthetic example data:** the CSVs in `data/raw` and the generated outputs
> in `output/` are synthetic examples created for demonstration and testing.
> They are not real laboratory measurements. Replace them with real files before
> using the tool for research.

## Contents

- [Quick start](#quick-start)
- [Input CSV format](#input-csv-format)
- [Validation and cleaning](#validation-and-cleaning)
- [Statistical model and assumptions](#statistical-model-and-assumptions)
- [Database](#database)
- [Outputs](#outputs)
- [SQL queries](#sql-queries)
- [Testing](#testing)
- [Project structure](#project-structure)
- [Design decisions and limitations](#design-decisions-and-limitations)
- [Troubleshooting](#troubleshooting)

## Quick start

Requirements: Python 3.11+, Docker with Compose, and Git (optional but
recommended).

### Windows PowerShell

```powershell
cd experimental-data-tool

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

docker compose up -d db

python -m src.main process
```

### Linux / macOS

```bash
cd experimental-data-tool

python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

docker compose up -d db

python -m src.main process
```

`process` creates the tables if needed, reads every `*.csv` in `data/raw`,
validates and cleans the rows, stores raw and processed measurements, computes
regressions, and writes plots and reports.

Useful commands:

```bash
# Optional explicit table creation
python -m src.main init-db

# Process without PostgreSQL (validation and local reports only)
python -m src.main process --skip-db

# Show stored history and regression results
python -m src.main history
python -m src.main history --experiment EXP-001

# Run the tests (SQLite in-memory; no PostgreSQL needed)
python -m pytest

# Stop PostgreSQL; the named Docker volume keeps the data
docker compose down
```

The default database URL is:

```text
postgresql+psycopg://lab_user:lab_password@127.0.0.1:5434/experimental_data
```

Override it with `--database-url` or the `DATABASE_URL` environment variable.
`.env.example` documents the variable, but the application does **not** load
`.env` files automatically; export the value in your shell or set it in your
IDE.

## Input CSV format

Place one or more UTF-8 CSV files in `data/raw`. Every file must have a header
row and these five required columns (names are case-sensitive):

| Column | Type | Unit | Meaning |
| --- | --- | --- | --- |
| `experiment_id` | text | - | Experiment identifier, max 64 characters, e.g. `EXP-001` |
| `sample_id` | text | - | Sample identifier within the experiment, max 64 characters |
| `measurement_angle` | number | degrees | Analyzer/polarizer angle relative to the chosen zero reference |
| `observed_rotation` | number | degrees | Measured rotation of the polarization plane |
| `measurement_timestamp` | ISO-8601 text | - | Time of the measurement; normalized to UTC |

Example:

```csv
experiment_id,sample_id,measurement_angle,observed_rotation,measurement_timestamp
EXP-001,S-01,0,1.2,2026-05-12T08:00:00Z
EXP-001,S-01,10,9.4,2026-05-12T08:01:00Z
```

Format assumptions:

- One row is one measurement.
- Decimal separator is `.` (not `,`).
- Timestamps are ISO-8601. Values with an offset are converted to UTC; values
  without an offset are interpreted as UTC. The database stores timezone-naive
  UTC timestamps.
- Blank numeric or text fields are invalid; they are not treated as zero.
- Extra columns are accepted for the current run and ignored by the database.
  The original file remains the authoritative source.
- A measurement is a duplicate when experiment, sample, angle and timestamp all
  match. Repetitions at the same angle with different timestamps are allowed.
- Files are never modified or deleted. A file is read again only when its
  SHA-256 checksum changes; an unchanged file is skipped on re-import.

## Validation and cleaning

Validation happens before any statistical calculation. Every row receives one
of three statuses:

- `valid` - used for analysis;
- `invalid` - missing value, non-numeric/non-finite number, out-of-range value,
  unparseable timestamp, or over-long identifier;
- `duplicate` - same experiment/sample/angle/timestamp as an earlier row.

Default acceptance ranges (configurable from the command line):

| Quantity | Default range |
| --- | --- |
| `measurement_angle` | -360 to 360 deg |
| `observed_rotation` | -180 to 180 deg |

```bash
python -m src.main process --angle-min -90 --angle-max 90 \
  --rotation-min -45 --rotation-max 45
```

Invalid and duplicate rows are **not silently deleted**:

- they remain in the `raw_measurements` table with their status and reason;
- they are listed in `output/reports/quality_issues.csv`;
- per-file counts appear in `output/reports/data_quality_report.csv` and
  `output/reports/summary.md`;
- only `valid` rows enter `processed_measurements` and the analysis.

Rows with missing values are also inventoried in the original source CSV. The
`raw_measurements` table stores the original text, not just the parsed number.

## Statistical model and assumptions

For each `(experiment_id, sample_id)` group, the application fits an ordinary
least-squares line:

```text
observed_rotation = slope * measurement_angle + intercept
```

- Both variables are in degrees. The slope has units of degree/degree; the
  intercept is in degrees.
- The fit is unweighted because the CSV format has no per-point uncertainty.
- Standard errors for slope/intercept and the residual standard error are
  reported when at least three points are available. With only two points, the
  line is determined exactly and the standard errors are `NaN`/not stored.
- R-squared is computed as the square of the Pearson correlation. It describes
  goodness of fit and is not evidence of a physical model.
- Assumptions: approximately linear relationship over the measured range,
  independent errors and roughly constant error variance. Residual plots are
  provided so these assumptions can be checked visually.
- The experiment comparison is descriptive (mean slope/intercept per
  experiment). It is deliberately not a significance test.

All statistical code is in `src/analysis.py` and operates only on DataFrames. It
has no database dependency, which keeps it easy to test.

## Database

PostgreSQL stores six small tables:

| Table | Purpose |
| --- | --- |
| `experiments` | Experiment code and metadata |
| `samples` | Sample code, unique within an experiment |
| `imports` | One row per imported file, with checksum and row counts |
| `raw_measurements` | Original text values, validation status and reason |
| `processed_measurements` | Clean numeric rows used for analysis |
| `regression_results` | Latest slope/intercept/R-squared and standard errors |

Primary keys, foreign keys, unique constraints and basic check constraints are
defined in `src/database.py`; `sql/schema.sql` is a reference PostgreSQL DDL
file. The application creates tables with SQLAlchemy
(`Base.metadata.create_all`), which is sufficient for this single-schema project.
**Alembic was deliberately omitted**: there is no migration history yet. If the
schema evolves after real data has been collected, add Alembic then rather than
carrying migration machinery now.

Re-import behavior:

- same file checksum -> file-level import is skipped;
- changed file -> raw rows are recorded again, but an already stored
  experiment/sample/angle/timestamp point is not duplicated;
- regression results are upserted per experiment/sample, so re-running does not
  create duplicate rows.

The old scaffold table `measurements` (if present in an existing local volume)
is unused by this version. The new schema uses the tables listed above.

## Outputs

After `python -m src.main process`:

```text
data/processed/processed_measurements.csv   clean measurements used for analysis
output/plots/rotation_vs_angle.png          scatter plot + regression lines
output/plots/regression_residuals.png       residual diagnostics
output/plots/rotation_histogram.png         observed-rotation distribution
output/reports/data_quality_report.csv      counts per input file
output/reports/quality_issues.csv           every rejected row and reason
output/reports/descriptive_statistics.csv   per experiment/sample statistics
output/reports/regression_results.csv       slope, intercept, R-squared, SEs
output/reports/residuals.csv                observed/predicted/residual rows
output/reports/experiment_comparison.csv    descriptive comparison
output/reports/summary.md                   human-readable run summary
```

All plots are PNG files written with Matplotlib's non-interactive `Agg` backend.
If there are no valid rows, tables and the quality report are still produced;
plots are skipped.

## SQL queries

Ready-to-run PostgreSQL queries live in `sql/queries/`:

- `measurements_by_experiment.sql`
- `average_rotation_by_sample.sql`
- `sample_comparison.sql`
- `regression_results.sql`
- `data_quality_summary.sql`
- `experiment_comparison.sql`

The first query uses a psql variable. Example on PowerShell:

```powershell
Get-Content -Raw sql\queries\measurements_by_experiment.sql |
  docker exec -i experimental_data_db psql -U lab_user -d experimental_data `
    -v experiment_id=EXP-001 -f -
```

On Linux/macOS:

```bash
docker exec -i experimental_data_db psql -U lab_user -d experimental_data \
  -v experiment_id=EXP-001 -f - \
  < sql/queries/measurements_by_experiment.sql
```

## Testing

The automated suite uses pytest and an in-memory SQLite database. This keeps the
tests fast and portable while exercising the same SQLAlchemy models and queries.
The PostgreSQL-specific schema and the full workflow were also smoke-tested
against PostgreSQL 16 in Docker during development.

```bash
python -m pytest
```

Coverage includes:

- CSV parsing, required/duplicate headers, multiple files, checksums;
- every validation rule, duplicate detection, quality reports;
- cleaning and excluded-row behavior;
- exact synthetic regressions with known slope/intercept, residual standard
  errors, skipped short groups and experiment comparisons;
- database persistence, raw-row retention, idempotent imports, regression
  round-trips, import history;
- report/plot generation and the end-to-end CLI.

Synthetic test data uses known mathematical relationships, not claimed
experimental results.

## Project structure

```text
experimental-data-tool/
├── data/
│   ├── raw/                    # input CSVs (read-only to the app)
│   └── processed/              # cleaned measurement CSV
├── output/
│   ├── plots/                  # PNG figures
│   └── reports/                # CSV tables and summary.md
├── sql/
│   ├── schema.sql              # reference PostgreSQL schema
│   └── queries/                # analytical SQL
├── src/
│   ├── ingestion.py            # CSV discovery/reading, checksums
│   ├── validation.py           # row-level checks and quality report
│   ├── cleaning.py             # selection of typed valid rows
│   ├── analysis.py             # descriptive stats and OLS regression
│   ├── database.py             # SQLAlchemy models and persistence
│   ├── reports.py              # Matplotlib and CSV/Markdown output
│   ├── config.py               # paths and default database URL
│   └── main.py                 # command-line interface
├── tests/
├── docker-compose.yml          # PostgreSQL only
├── requirements.txt
├── pytest.ini
├── .env.example
├── .gitignore
└── README.md
```

## Design decisions and limitations

- **No FastAPI/React/Airflow/etc.** The required workflow is a batch CLI; a web
  UI or scheduler would add operational cost without helping a small lab.
- **One command, one database container.** The Python app runs in a virtual
  environment; only PostgreSQL is containerized.
- **No silent deletion.** Rejected rows are visible in both the database and the
  reports.
- **No invented physical meaning.** The default ranges are QA limits, not
  constants of nature. Change them for your apparatus.
- **No uncertainty propagation.** The CSV format has no uncertainty column, so
  the fit is unweighted OLS.
- **No significance tests between experiments.** The comparison is descriptive;
  adding formal tests would require a stated statistical design.
- **Schema changes require care.** `create_all` does not migrate existing
  tables. Introduce Alembic if the schema must evolve with retained real data.

## Troubleshooting

**`DATABASE ERROR: connection ... refused`**

Start the database and wait for its health check:

```bash
docker compose up -d db
docker compose ps
```

**Port 5434 is already in use**

Change the host port in `docker-compose.yml` and update `DATABASE_URL` or pass
`--database-url`.

**`No CSV files found`**

Put at least one `.csv` file in `data/raw` or pass `--input <directory>`.

**`missing required column(s)`**

Check the header against the five required names above. Header names are
case-sensitive.

**I want a clean database**

This deletes the Docker volume and all stored measurements:

```bash
docker compose down -v
docker compose up -d db
python -m src.main process
```

**Can I use this offline?**

Yes, for validation and local reports:

```bash
python -m src.main process --skip-db
```

The PostgreSQL step is skipped, so only local CSV/PNG/Markdown outputs are
produced.
