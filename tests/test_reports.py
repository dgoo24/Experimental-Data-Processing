from __future__ import annotations

import pandas as pd

from src.analysis import analyze_measurements
from src.cleaning import select_valid_measurements
from src.reports import generate_reports
from src.validation import validate_measurements


def test_generate_reports_creates_plots_tables_and_summary(
    tmp_path, validated_frame
):
    processed = select_valid_measurements(validated_frame)
    bundle = analyze_measurements(processed)

    artifacts = generate_reports(
        processed=processed,
        validated=validated_frame,
        bundle=bundle,
        output_dir=tmp_path,
    )

    expected = {
        "rotation_vs_angle",
        "regression_residuals",
        "rotation_histogram",
        "data_quality_report",
        "quality_issues",
        "descriptive_statistics",
        "regression_results",
        "residuals",
        "experiment_comparison",
        "summary",
    }
    assert expected.issubset(artifacts)
    for name in ["rotation_vs_angle", "regression_residuals", "rotation_histogram"]:
        assert artifacts[name].exists()
        assert artifacts[name].stat().st_size > 1000

    regression_table = pd.read_csv(artifacts["regression_results"])
    assert len(regression_table) == 2
    assert "slope" in regression_table.columns

    summary = artifacts["summary"].read_text(encoding="utf-8")
    assert "Experimental data processing summary" in summary
    assert "Linear regressions" in summary
    assert "EXP-001" in summary


def test_generate_reports_with_no_valid_rows(tmp_path, make_raw):
    raw = make_raw(
        [
            {
                "experiment_id": "E1",
                "sample_id": "S1",
                "measurement_angle": "bad",
                "observed_rotation": "1",
                "measurement_timestamp": "2026-01-01T00:00:00Z",
            }
        ]
    )
    validated = validate_measurements(raw)
    processed = select_valid_measurements(validated)
    bundle = analyze_measurements(processed)

    artifacts = generate_reports(processed, validated, bundle, tmp_path)

    assert "rotation_vs_angle" not in artifacts
    assert "regression_residuals" not in artifacts
    assert "rotation_histogram" not in artifacts
    assert artifacts["data_quality_report"].exists()
    assert artifacts["summary"].exists()
    assert artifacts["quality_issues"].exists()

    issues = pd.read_csv(artifacts["quality_issues"])
    assert len(issues) == 1
