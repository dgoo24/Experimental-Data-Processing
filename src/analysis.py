"""Statistical analysis of optical polarization measurements.

Model
-----
For each ``(experiment_id, sample_id)`` group the application fits an ordinary
least-squares line

    observed_rotation = slope * measurement_angle + intercept

where both variables are in degrees.  The slope therefore has units of
degree/degree (dimensionless) and the intercept is in degrees.

Assumptions and limits
----------------------
* The relationship is approximately linear over the measured angle range.
* Errors are independent and have approximately constant variance; the CSV has
  no per-point uncertainty column, so the fit is unweighted OLS.
* R-squared is a goodness-of-fit statistic, not proof of a physical model.
* Standard errors are reported when there are at least three points.  With two
  points the line is determined exactly and no residual degrees of freedom
  remain, so standard errors are reported as NaN.
* Duplicate and invalid rows are excluded before this module is called.

The functions here only operate on DataFrames and have no database dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.stats import linregress

DESCRIPTIVE_COLUMNS = [
    "experiment_id",
    "sample_id",
    "n_points",
    "mean_angle_deg",
    "std_angle_deg",
    "min_angle_deg",
    "max_angle_deg",
    "mean_rotation_deg",
    "std_rotation_deg",
    "min_rotation_deg",
    "max_rotation_deg",
]

REGRESSION_COLUMNS = [
    "experiment_id",
    "sample_id",
    "n_points",
    "slope",
    "intercept",
    "r_squared",
    "slope_std_error",
    "intercept_std_error",
    "residual_std_error",
]

RESIDUAL_COLUMNS = [
    "experiment_id",
    "sample_id",
    "measurement_angle",
    "observed_rotation",
    "predicted_rotation",
    "residual",
]

COMPARISON_COLUMNS = [
    "experiment_id",
    "n_samples",
    "n_points",
    "mean_slope",
    "std_slope",
    "mean_intercept",
    "mean_r_squared",
]


class RegressionError(ValueError):
    """Raised when a group cannot be fitted with a linear regression."""


@dataclass(frozen=True)
class RegressionFit:
    slope: float
    intercept: float
    r_squared: float
    slope_std_error: float
    intercept_std_error: float
    residual_std_error: float
    n_points: int


@dataclass
class AnalysisBundle:
    descriptive: pd.DataFrame
    regressions: pd.DataFrame
    residuals: pd.DataFrame
    comparison: pd.DataFrame
    skipped: list[dict[str, object]] = field(default_factory=list)


def _empty_frame(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def descriptive_statistics(measurements: pd.DataFrame) -> pd.DataFrame:
    """Return count, mean, sample standard deviation and extrema per group."""
    if measurements.empty:
        return _empty_frame(DESCRIPTIVE_COLUMNS)

    grouped = (
        measurements.groupby(["experiment_id", "sample_id"], sort=True)
        .agg(
            n_points=("measurement_angle", "size"),
            mean_angle_deg=("measurement_angle", "mean"),
            std_angle_deg=("measurement_angle", "std"),
            min_angle_deg=("measurement_angle", "min"),
            max_angle_deg=("measurement_angle", "max"),
            mean_rotation_deg=("observed_rotation", "mean"),
            std_rotation_deg=("observed_rotation", "std"),
            min_rotation_deg=("observed_rotation", "min"),
            max_rotation_deg=("observed_rotation", "max"),
        )
        .reset_index()
    )
    return grouped[DESCRIPTIVE_COLUMNS]


def fit_linear_regression(x: np.ndarray | pd.Series, y: np.ndarray | pd.Series) -> RegressionFit:
    """Fit ``y = slope*x + intercept`` and return OLS diagnostics."""
    x_values = np.asarray(x, dtype=float)
    y_values = np.asarray(y, dtype=float)

    if x_values.shape != y_values.shape:
        raise RegressionError("x and y must have the same length")
    finite = np.isfinite(x_values) & np.isfinite(y_values)
    x_values = x_values[finite]
    y_values = y_values[finite]

    if len(x_values) < 2:
        raise RegressionError("at least two finite points are required")
    if np.ptp(x_values) == 0:
        raise RegressionError("measurement_angle has no variation")

    fit = linregress(x_values, y_values)
    predicted = fit.slope * x_values + fit.intercept
    residuals = y_values - predicted
    n_points = int(len(x_values))

    if n_points > 2:
        residual_std_error = float(np.sqrt(np.sum(residuals**2) / (n_points - 2)))
        slope_std_error = float(fit.stderr)
        intercept_std_error = float(fit.intercept_stderr)
    else:
        residual_std_error = float("nan")
        slope_std_error = float("nan")
        intercept_std_error = float("nan")

    return RegressionFit(
        slope=float(fit.slope),
        intercept=float(fit.intercept),
        r_squared=float(fit.rvalue**2) if np.isfinite(fit.rvalue) else float("nan"),
        slope_std_error=slope_std_error,
        intercept_std_error=intercept_std_error,
        residual_std_error=residual_std_error,
        n_points=n_points,
    )


def regress_by_sample(
    measurements: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, list[dict[str, object]]]:
    """Fit one regression per experiment/sample group.

    Returns ``(regression_results, residual_rows, skipped_groups)``.  Groups
    with fewer than two points, or with no angle variation, are skipped and
    reported instead of aborting the whole run.
    """
    results: list[dict[str, object]] = []
    residual_rows: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []

    if measurements.empty:
        return (
            _empty_frame(REGRESSION_COLUMNS),
            _empty_frame(RESIDUAL_COLUMNS),
            skipped,
        )

    for (experiment_id, sample_id), group in measurements.groupby(
        ["experiment_id", "sample_id"], sort=True
    ):
        try:
            fit = fit_linear_regression(group["measurement_angle"], group["observed_rotation"])
        except RegressionError as exc:
            skipped.append(
                {
                    "experiment_id": experiment_id,
                    "sample_id": sample_id,
                    "reason": str(exc),
                }
            )
            continue

        results.append(
            {
                "experiment_id": experiment_id,
                "sample_id": sample_id,
                "n_points": fit.n_points,
                "slope": fit.slope,
                "intercept": fit.intercept,
                "r_squared": fit.r_squared,
                "slope_std_error": fit.slope_std_error,
                "intercept_std_error": fit.intercept_std_error,
                "residual_std_error": fit.residual_std_error,
            }
        )

        for row in group.itertuples(index=False):
            predicted = fit.slope * float(row.measurement_angle) + fit.intercept
            residual_rows.append(
                {
                    "experiment_id": experiment_id,
                    "sample_id": sample_id,
                    "measurement_angle": float(row.measurement_angle),
                    "observed_rotation": float(row.observed_rotation),
                    "predicted_rotation": predicted,
                    "residual": float(row.observed_rotation) - predicted,
                }
            )

    regressions = pd.DataFrame(results, columns=REGRESSION_COLUMNS)
    residuals = pd.DataFrame(residual_rows, columns=RESIDUAL_COLUMNS)
    return regressions, residuals, skipped


def compare_experiments(regressions: pd.DataFrame) -> pd.DataFrame:
    """Summarize fitted slopes/intercepts per experiment.

    This is a descriptive comparison only.  It does not claim statistical
    significance between experiments.
    """
    if regressions.empty:
        return _empty_frame(COMPARISON_COLUMNS)

    comparison = (
        regressions.groupby("experiment_id", sort=True)
        .agg(
            n_samples=("sample_id", "nunique"),
            n_points=("n_points", "sum"),
            mean_slope=("slope", "mean"),
            std_slope=("slope", "std"),
            mean_intercept=("intercept", "mean"),
            mean_r_squared=("r_squared", "mean"),
        )
        .reset_index()
    )
    return comparison[COMPARISON_COLUMNS]


def analyze_measurements(measurements: pd.DataFrame) -> AnalysisBundle:
    """Run all descriptive and regression analysis on cleaned measurements."""
    descriptive = descriptive_statistics(measurements)
    regressions, residuals, skipped = regress_by_sample(measurements)
    comparison = compare_experiments(regressions)
    return AnalysisBundle(
        descriptive=descriptive,
        regressions=regressions,
        residuals=residuals,
        comparison=comparison,
        skipped=skipped,
    )
