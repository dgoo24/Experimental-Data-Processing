"""Project-wide defaults.

The application intentionally keeps configuration simple: paths and the database
URL have sensible defaults and can be overridden from the command line or the
``DATABASE_URL`` environment variable.
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_RAW_DIR = PROJECT_ROOT / "data" / "raw"
DATA_PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
DEMO_DATA_DIR = PROJECT_ROOT / "data" / "demo"
DEMO_PROCESSED_PATH = DEMO_DATA_DIR / "processed_measurements.csv"
DEMO_REPORTS_DIR = DEMO_DATA_DIR / "reports"
OUTPUT_DIR = PROJECT_ROOT / "output"
PLOTS_DIR = OUTPUT_DIR / "plots"
REPORTS_DIR = OUTPUT_DIR / "reports"

DEFAULT_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://lab_user:lab_password@127.0.0.1:5434/experimental_data",
)

# Seconds to wait for a TCP/connection handshake with PostgreSQL.  Without a
# limit a closed or filtered port blocks the dashboard for minutes (Streamlit
# Community Cloud has no database at all), so keep the fallback to the local
# files fast.  libpq treats values below 2 as 2 seconds.
DB_CONNECT_TIMEOUT = int(os.environ.get("DB_CONNECT_TIMEOUT", "3"))
