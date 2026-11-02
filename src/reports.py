"""Matplotlib plots and CSV/Markdown reports."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .analysis import AnalysisBundle
from .validation import build_quality_report, quality_issues


def _prepare(path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _group_label(experiment_id: str, sample_id: str) -> str:
    return f"{experiment_id} / {sample_id}"


def plot_rotation_vs_angle(
    processed: pd.DataFrame,
    bundle: AnalysisBundle,
    path: Path,
) -> Path | None:
    """Scatter measurements with one fitted line per experiment/sample."""
    if processed.empty:
        return None

    path = _prepare(path)
    figure, axis = plt.subplots(figsize=(8.0, 5.0))
    color_map = plt.get_cmap("tab10")
    groups = list(processed.groupby(["experiment_id", "sample_id"], sort=True))

    fits = {
        (str(row.experiment_id), str(row.sample_id)): row
        for row in bundle.regressions.itertuples(index=False)
    }

    for index, ((experiment_id, sample_id), group) in enumerate(groups):
        color = color_map(index % 10)
        label = _group_label(experiment_id, sample_id)
        axis.scatter(
            group["measurement_angle"],
            group["observed_rotation"],
            s=28,
            color=color,
            label=label,
            zorder=3,
        )

        fit = fits.get((str(experiment_id), str(sample_id)))
        if fit is not None:
            x_line = np.linspace(
                float(group["measurement_angle"].min()),
                float(group["measurement_angle"].max()),
                100,
            )
            y_line = fit.slope * x_line + fit.intercept
            axis.plot(x_line, y_line, color=color, linewidth=1.8, zorder=2)

    axis.set_xlabel("Measurement angle (deg)")
    axis.set_ylabel("Observed rotation (deg)")
    axis.set_title("Observed rotation vs measurement angle")
    axis.grid(True, alpha=0.3)
    if len(groups) <= 15:
        axis.legend(fontsize=8, frameon=False)
    figure.tight_layout()
    figure.savefig(path, dpi=150)
    plt.close(figure)
    return path


def plot_residuals(residuals: pd.DataFrame, path: Path) -> Path | None:
    """Residuals against measurement angle, with a zero reference line."""
    if residuals.empty:
        return None

    path = _prepare(path)
    figure, axis = plt.subplots(figsize=(8.0, 5.0))
    color_map = plt.get_cmap("tab10")
    groups = list(residuals.groupby(["experiment_id", "sample_id"], sort=True))

    for index, ((experiment_id, sample_id), group) in enumerate(groups):
        axis.scatter(
            group["measurement_angle"],
            group["residual"],
            s=28,
            color=color_map(index % 10),
            label=_group_label(experiment_id, sample_id),
            zorder=3,
        )

    axis.axhline(0.0, color="black", linewidth=1.0, linestyle="--")
    axis.set_xlabel("Measurement angle (deg)")
    axis.set_ylabel("Residual (deg)")
    axis.set_title("Regression residuals")
    axis.grid(True, alpha=0.3)
    if len(groups) <= 15:
        axis.legend(fontsize=8, frameon=False)
    figure.tight_layout()
    figure.savefig(path, dpi=150)
    plt.close(figure)
    return path


def plot_rotation_histogram(processed: pd.DataFrame, path: Path) -> Path | None:
    """Histogram of all valid observed-rotation values."""
    if processed.empty:
        return None

    path = _prepare(path)
    values = processed["observed_rotation"].dropna().to_numpy(dtype=float)
    if len(values) == 0:
        return None

    bins = int(min(20, max(5, np.sqrt(len(values)))))
    figure, axis = plt.subplots(figsize=(8.0, 5.0))
    axis.hist(values, bins=bins, color="#4472c4", edgecolor="white", alpha=0.9)
    axis.axvline(float(np.mean(values)), color="#c00000", linestyle="--", label="Mean")
    axis.set_xlabel("Observed rotation (deg)")
    axis.set_ylabel("Number of measurements")
    axis.set_title("Distribution of observed rotation")
    axis.grid(True, axis="y", alpha=0.3)
    axis.legend(frameon=False)
    figure.tight_layout()
    figure.savefig(path, dpi=150)
    plt.close(figure)
    return path


def _format_cell(value: object) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, (float, np.floating)):
        number = float(value)
        if not np.isfinite(number):
            return "n/a"
        return f"{number:.6g}"
    text = str(value)
    return text.replace("|", "\\|")


def _markdown_table(frame: pd.DataFrame, max_rows: int = 50) -> str:
    if frame.empty:
        return "_No rows._"

    shown = frame.head(max_rows)
    header = "| " + " | ".join(str(column) for column in shown.columns) + " |"
    separator = "| " + " | ".join("---" for _ in shown.columns) + " |"
    rows = [
        "| " + " | ".join(_format_cell(value) for value in row) + " |"
        for row in shown.itertuples(index=False, name=None)
    ]
    result = "\n".join([header, separator, *rows])
    if len(frame) > max_rows:
        result += f"\n\n_Showing the first {max_rows} of {len(frame)} rows._"
    return result


def _import_table(import_outcomes: Iterable[object] | None) -> pd.DataFrame:
    if not import_outcomes:
        return pd.DataFrame()
    rows = [asdict(outcome) if hasattr(outcome, "__dataclass_fields__") else vars(outcome) for outcome in import_outcomes]
    return pd.DataFrame(rows)


def write_summary_markdown(
    processed: pd.DataFrame,
    validated: pd.DataFrame,
    bundle: AnalysisBundle,
    import_outcomes: Iterable[object] | None,
    path: Path,
) -> Path:
    """Write a compact human-readable run summary."""
    path = _prepare(path)
    quality = build_quality_report(validated)

    validation_config = validated.attrs.get("validation_config", {})

    lines = [
        "# Experimental data processing summary",
        "",
        "Generated automatically by `experimental-data-tool`.",
        "",
        "## Run overview",
        "",
        f"- Input rows: {len(validated)}",
        f"- Valid measurements used for analysis: {len(processed)}",
        f"- Rejected rows (invalid or duplicate): {int(validated['status'].ne('valid').sum())}",
        f"- Analysis groups (experiment/sample): {len(bundle.descriptive)}",
        f"- Regressions computed: {len(bundle.regressions)}",
    ]

    if validation_config:
        lines += [
            f"- Accepted measurement angle: "
            f"{validation_config['angle_min']:g} to {validation_config['angle_max']:g} deg",
            f"- Accepted observed rotation: "
            f"{validation_config['rotation_min']:g} to {validation_config['rotation_max']:g} deg",
        ]

    lines += [
        "",
        "## Data quality",
        "",
        _markdown_table(quality),
        "",
        "Rejected rows are listed in `quality_issues.csv`; they remain in the",
        "original input and, when the database step runs, in `raw_measurements`",
        "with their validation status.",
        "",
    ]

    import_table = _import_table(import_outcomes)
    if not import_table.empty:
        lines += ["## Database imports", "", _markdown_table(import_table), ""]

    lines += ["## Descriptive statistics", "", _markdown_table(bundle.descriptive), ""]

    lines += ["## Linear regressions", ""]
    if bundle.regressions.empty:
        lines.append("_No regression could be computed._")
    else:
        display = bundle.regressions.copy()
        display["equation"] = display.apply(
            lambda row: (
                f"y = {row['slope']:.6g} x "
                f"{'+' if row['intercept'] >= 0 else '-'} {abs(row['intercept']):.6g}"
            ),
            axis=1,
        )
        lines.append(_markdown_table(display))
    lines.append("")

    lines += ["## Comparison between experiments", "", _markdown_table(bundle.comparison), ""]

    if bundle.skipped:
        lines += ["## Skipped groups", ""]
        lines.append(_markdown_table(pd.DataFrame(bundle.skipped)))
        lines.append("")

    lines += [
        "## Interpretation notes",
        "",
        "- The fitted model is `observed_rotation = slope * measurement_angle + intercept`.",
        "- Both variables are in degrees, so the slope is in degree/degree.",
        "- R-squared is a goodness-of-fit statistic, not proof of a physical model.",
        "- Standard errors are omitted when fewer than three points are available.",
        "",
    ]

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def generate_reports(
    processed: pd.DataFrame,
    validated: pd.DataFrame,
    bundle: AnalysisBundle,
    output_dir: Path,
    import_outcomes: Iterable[object] | None = None,
) -> dict[str, Path]:
    """Write all CSV tables, PNG plots and the Markdown summary."""
    output_dir = Path(output_dir)
    plots_dir = output_dir / "plots"
    reports_dir = output_dir / "reports"
    plots_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    artifacts: dict[str, Path] = {}

    quality = build_quality_report(validated)
    issues = quality_issues(validated)
    tables = {
        "data_quality_report": (quality, reports_dir / "data_quality_report.csv"),
        "quality_issues": (issues, reports_dir / "quality_issues.csv"),
        "descriptive_statistics": (
            bundle.descriptive,
            reports_dir / "descriptive_statistics.csv",
        ),
        "regression_results": (bundle.regressions, reports_dir / "regression_results.csv"),
        "residuals": (bundle.residuals, reports_dir / "residuals.csv"),
        "experiment_comparison": (
            bundle.comparison,
            reports_dir / "experiment_comparison.csv",
        ),
    }

    for name, (frame, path) in tables.items():
        frame.to_csv(path, index=False, encoding="utf-8")
        artifacts[name] = path

    plot_paths = {
        "rotation_vs_angle": plot_rotation_vs_angle(
            processed, bundle, plots_dir / "rotation_vs_angle.png"
        ),
        "regression_residuals": plot_residuals(
            bundle.residuals, plots_dir / "regression_residuals.png"
        ),
        "rotation_histogram": plot_rotation_histogram(
            processed, plots_dir / "rotation_histogram.png"
        ),
    }
    for name, path in plot_paths.items():
        if path is not None:
            artifacts[name] = path

    summary_path = write_summary_markdown(
        processed,
        validated,
        bundle,
        import_outcomes,
        reports_dir / "summary.md",
    )
    artifacts["summary"] = summary_path
    return artifacts
