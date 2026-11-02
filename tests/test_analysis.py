from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.analysis import (
    AnalysisBundle,
    RegressionError,
    analyze_measurements,
    compare_experiments,
    descriptive_statistics,
    fit_linear_regression,
    regress_by_sample,
)


def test_exact_line_has_known_fit():
    fit = fit_linear_regression([0, 1, 2, 3], [1, 4, 7, 10])

    assert fit.slope == pytest.approx(3.0)
    assert fit.intercept == pytest.approx(1.0)
    assert fit.r_squared == pytest.approx(1.0)
    assert fit.residual_std_error == pytest.approx(0.0, abs=1e-12)
    assert fit.n_points == 4


def test_noisy_fit_matches_numpy_least_squares():
    x = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    y = np.array([2.1, 3.9, 6.2, 7.8, 10.1])

    fit = fit_linear_regression(x, y)
    slope, intercept = np.polyfit(x, y, 1)
    predicted = slope * x + intercept
    ss_res = float(np.sum((y - predicted) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))

    assert fit.slope == pytest.approx(slope)
    assert fit.intercept == pytest.approx(intercept)
    assert fit.r_squared == pytest.approx(1.0 - ss_res / ss_tot)
    expected_residual_se = np.sqrt(ss_res / (len(x) - 2))
    assert fit.residual_std_error == pytest.approx(expected_residual_se)


def test_two_points_have_no_standard_errors():
    fit = fit_linear_regression([0, 1], [1, 3])

    assert fit.slope == pytest.approx(2.0)
    assert fit.intercept == pytest.approx(1.0)
    assert np.isnan(fit.slope_std_error)
    assert np.isnan(fit.residual_std_error)


def test_constant_angle_raises():
    with pytest.raises(RegressionError, match="no variation"):
        fit_linear_regression([1, 1, 1], [1, 2, 3])


def test_per_sample_regressions_match_known_lines(processed_frame):
    regressions, residuals, skipped = regress_by_sample(processed_frame)

    assert skipped == []
    assert len(regressions) == 2
    assert len(residuals) == len(processed_frame)

    first = regressions.iloc[0]
    assert first["experiment_id"] == "EXP-001"
    assert first["sample_id"] == "S-01"
    assert first["slope"] == pytest.approx(3.0)
    assert first["intercept"] == pytest.approx(2.0)

    second = regressions.iloc[1]
    assert second["slope"] == pytest.approx(-0.5)
    assert second["intercept"] == pytest.approx(5.0)

    for _, group in residuals.groupby(["experiment_id", "sample_id"]):
        assert group["residual"].sum() == pytest.approx(0.0, abs=1e-10)


def test_short_group_is_skipped_not_fatal():
    measurements = pd.DataFrame(
        {
            "experiment_id": ["E1", "E1", "E2"],
            "sample_id": ["S1", "S1", "S2"],
            "measurement_angle": [0.0, 10.0, 0.0],
            "observed_rotation": [1.0, 2.0, 3.0],
            "measurement_timestamp": pd.to_datetime(
                ["2026-01-01T00:00:00", "2026-01-01T00:01:00", "2026-01-02T00:00:00"]
            ),
        }
    )

    regressions, residuals, skipped = regress_by_sample(measurements)

    assert len(regressions) == 1
    assert len(residuals) == 2
    assert len(skipped) == 1
    assert skipped[0]["experiment_id"] == "E2"
    assert skipped[0]["sample_id"] == "S2"
    assert "at least two" in skipped[0]["reason"]


def test_descriptive_statistics_are_reproducible(processed_frame):
    stats = descriptive_statistics(processed_frame)
    first = stats.iloc[0]
    angles = processed_frame.loc[
        (processed_frame["experiment_id"] == "EXP-001")
        & (processed_frame["sample_id"] == "S-01"),
        "measurement_angle",
    ]

    assert first["n_points"] == 6
    assert first["mean_angle_deg"] == pytest.approx(angles.mean())
    assert first["std_angle_deg"] == pytest.approx(angles.std(ddof=1))
    assert first["min_angle_deg"] == 0
    assert first["max_angle_deg"] == 50


def test_comparison_between_experiments(processed_frame):
    bundle = analyze_measurements(processed_frame)
    comparison = bundle.comparison

    assert comparison["experiment_id"].tolist() == ["EXP-001", "EXP-002"]
    assert comparison.loc[0, "mean_slope"] == pytest.approx(3.0)
    assert comparison.loc[1, "mean_slope"] == pytest.approx(-0.5)
    assert comparison["n_samples"].tolist() == [1, 1]


def test_empty_analysis_returns_empty_tables():
    empty = pd.DataFrame(
        columns=[
            "experiment_id",
            "sample_id",
            "measurement_angle",
            "observed_rotation",
            "measurement_timestamp",
        ]
    )
    bundle = analyze_measurements(empty)

    assert isinstance(bundle, AnalysisBundle)
    assert bundle.descriptive.empty
    assert bundle.regressions.empty
    assert bundle.residuals.empty
    assert bundle.comparison.empty
    assert bundle.skipped == []


def test_compare_empty_regressions():
    empty = pd.DataFrame(columns=["experiment_id", "sample_id", "n_points", "slope", "intercept", "r_squared"])
    assert compare_experiments(empty).empty
