from __future__ import annotations

from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

import src.dashboard_data as dashboard_data


def _data() -> dashboard_data.DashboardData:
    measurements = pd.DataFrame(
        {
            "experiment_id": ["EXP-001", "EXP-001", "EXP-001", "EXP-002"],
            "sample_id": ["S-01", "S-01", "S-01", "S-02"],
            "measurement_angle": [0.0, 10.0, 20.0, 0.0],
            "observed_rotation": [1.0, 21.0, 41.0, 5.0],
            "measurement_timestamp": pd.to_datetime(
                [
                    "2026-01-01T10:00:00",
                    "2026-01-01T10:01:00",
                    "2026-01-01T10:02:00",
                    "2026-01-02T10:00:00",
                ]
            ),
        }
    )
    regressions = pd.DataFrame(
        {
            "experiment_id": ["EXP-001", "EXP-002"],
            "sample_id": ["S-01", "S-02"],
            "n_points": [3, 1],
            "slope": [2.0, 1.5],
            "intercept": [1.0, 5.0],
            "r_squared": [1.0, float("nan")],
            "slope_std_error": [0.0, float("nan")],
            "intercept_std_error": [0.0, float("nan")],
            "residual_std_error": [0.0, float("nan")],
        }
    )
    quality = pd.DataFrame(
        {
            "source_file": ["measurements.csv"],
            "total_rows": [4],
            "valid_rows": [4],
            "invalid_rows": [0],
            "duplicate_rows": [0],
            "rejected_rows": [0],
        }
    )

    return dashboard_data.DashboardData(
        measurements=measurements,
        regressions=regressions,
        descriptive=dashboard_data.descriptive_statistics(measurements),
        residuals=dashboard_data.attach_residuals(measurements, regressions),
        comparison=dashboard_data.compare_experiments(regressions),
        quality=quality,
        issues=pd.DataFrame(),
        imports=pd.DataFrame(),
        source_label="Test",
    )


def test_dashboard_renders_every_view(monkeypatch) -> None:
    monkeypatch.setattr(
        dashboard_data, "load_dashboard_data", lambda **kwargs: _data()
    )

    app_path = Path(__file__).resolve().parent.parent / "src" / "dashboard.py"
    app = AppTest.from_file(app_path, default_timeout=60)
    app.run()

    assert not app.exception
    assert [(metric.label, metric.value) for metric in app.metric] == [
        ("Messungen", "4"),
        ("Experimente", "2"),
        ("Proben", "2"),
        ("Regressionen", "2"),
        ("Mittleres R²", "1.0000"),
        ("Abgewiesene Zeilen", "0"),
    ]

    views = app.segmented_control[0]
    for view in views.options:
        views.set_value(view).run()
        assert not app.exception, view


def test_cloud_entry_point_keeps_rendering_after_rerun(monkeypatch) -> None:
    """Streamlit re-executes the entry point on every interaction.

    The entry point used by Streamlit Community Cloud must therefore render the
    dashboard on every rerun; a plain ``import`` only renders the first time and
    leaves a blank page afterwards.
    """
    monkeypatch.setattr(
        dashboard_data, "load_dashboard_data", lambda **kwargs: _data()
    )

    app_path = Path(__file__).resolve().parent.parent / "streamlit_app.py"
    app = AppTest.from_file(app_path, default_timeout=60)

    app.run()
    assert not app.exception
    assert len(app.metric) == 6

    app.run()
    assert not app.exception
    assert [(metric.label, metric.value) for metric in app.metric] == [
        ("Messungen", "4"),
        ("Experimente", "2"),
        ("Proben", "2"),
        ("Regressionen", "2"),
        ("Mittleres R²", "1.0000"),
        ("Abgewiesene Zeilen", "0"),
    ]
