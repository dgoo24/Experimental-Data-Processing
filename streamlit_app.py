"""Entry point for Streamlit Community Cloud.

The dashboard itself lives in :mod:`src.dashboard` and can also be started
locally with ``streamlit run src/dashboard.py``.

Streamlit re-executes *this file* on every rerun (every widget interaction), but
an ``import src.dashboard`` would only run once: the module stays in
``sys.modules`` and the page would go blank after the first interaction.  So the
dashboard script is executed with :mod:`runpy` on every rerun instead.
"""

from __future__ import annotations

import runpy
from pathlib import Path

APP_PATH = Path(__file__).resolve().parent / "src" / "dashboard.py"

runpy.run_path(str(APP_PATH), run_name="__main__")
