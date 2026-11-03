"""Interactive dashboard for the polarization measurements.

Run it from the project root::

    streamlit run src/dashboard.py

The dashboard only reads data.  It never modifies the database or the CSV
files; use ``python -m src.main process`` for the actual pipeline.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import altair as alt
import pandas as pd
import streamlit as st

from src.config import DEFAULT_DATABASE_URL
from src.analysis import compare_experiments
from src.dashboard_data import (
    SOURCE_AUTO,
    SOURCE_DATABASE,
    SOURCE_FILES,
    DashboardData,
    build_view,
    equation,
    filter_measurements,
    filter_regressions,
    fitted_lines,
    load_dashboard_data,
    summarize,
)

SOURCE_LABELS = {
    "Automatisch": SOURCE_AUTO,
    "PostgreSQL": SOURCE_DATABASE,
    "Lokale Dateien": SOURCE_FILES,
}

VIEWS = ["Übersicht", "Regressionen", "Datenqualität", "Messwerte"]

PALETTE = [
    "#38bdf8",
    "#818cf8",
    "#34d399",
    "#fbbf24",
    "#f472b6",
    "#a78bfa",
    "#f87171",
    "#2dd4bf",
    "#60a5fa",
    "#c084fc",
]

st.set_page_config(
    page_title="Polarimetrie-Dashboard",
    page_icon=":material/science:",
    layout="wide",
)


@st.cache_data(ttl="2m", show_spinner=False)
def _load(source_key: str, database_url: str) -> DashboardData:
    return load_dashboard_data(source=source_key, database_url=database_url)


def _format_number(value: float | int, digits: int = 0) -> str:
    if isinstance(value, float) and pd.isna(value):
        return "–"
    text = f"{value:,.{digits}f}"
    return text.replace(",", "\u202f")


def _grouped(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["group"] = result["experiment_id"] + " / " + result["sample_id"]
    return result


def _color_scale() -> alt.Scale:
    return alt.Scale(range=PALETTE)


def _scatter_with_fit(measurements: pd.DataFrame, regressions: pd.DataFrame) -> alt.LayerChart:
    points = _grouped(measurements)
    lines = fitted_lines(measurements, regressions)

    color = alt.Color("group:N", title="Experiment / Probe", scale=_color_scale())
    x = alt.X("measurement_angle:Q", title="Messwinkel (Grad)")
    y = alt.Y("observed_rotation:Q", title="Beobachtete Drehung (Grad)")

    point_layer = (
        alt.Chart(points)
        .mark_circle(size=70, opacity=0.9)
        .encode(
            x=x,
            y=y,
            color=color,
            tooltip=[
                alt.Tooltip("experiment_id:N", title="Experiment"),
                alt.Tooltip("sample_id:N", title="Probe"),
                alt.Tooltip("measurement_angle:Q", title="Winkel (°)", format=".2f"),
                alt.Tooltip("observed_rotation:Q", title="Drehung (°)", format=".2f"),
            ],
        )
    )

    layers: list[alt.Chart] = [point_layer]
    if not lines.empty:
        lines = lines.rename(columns={"fitted_rotation": "observed_rotation"})
        layers.insert(
            0,
            alt.Chart(_grouped(lines))
            .mark_line(strokeWidth=2, opacity=0.85)
            .encode(x=x, y=y, color=color),
        )
    return alt.layer(*layers).interactive()


def _histogram(measurements: pd.DataFrame) -> alt.LayerChart:
    values = measurements["observed_rotation"]
    bars = (
        alt.Chart(measurements)
        .mark_bar(color="#38bdf8", opacity=0.85, cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
        .encode(
            x=alt.X(
                "observed_rotation:Q",
                bin=alt.Bin(maxbins=24),
                title="Beobachtete Drehung (Grad)",
            ),
            y=alt.Y("count()", title="Messungen"),
            tooltip=[alt.Tooltip("count()", title="Messungen")],
        )
    )
    mean_rule = (
        alt.Chart(pd.DataFrame({"mean": [float(values.mean())]}))
        .mark_rule(color="#f87171", strokeDash=[6, 4])
        .encode(x="mean:Q", tooltip=[alt.Tooltip("mean:Q", title="Mittelwert", format=".2f")])
    )
    return bars + mean_rule


def _comparison_chart(comparison: pd.DataFrame) -> alt.Chart:
    return (
        alt.Chart(comparison)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X("experiment_id:N", title=None, sort="-y"),
            y=alt.Y("mean_slope:Q", title="Mittlere Steigung"),
            color=alt.Color("experiment_id:N", legend=None, scale=_color_scale()),
            tooltip=[
                alt.Tooltip("experiment_id:N", title="Experiment"),
                alt.Tooltip("n_samples:Q", title="Proben"),
                alt.Tooltip("n_points:Q", title="Messpunkte"),
                alt.Tooltip("mean_slope:Q", title="Mittlere Steigung", format=".4f"),
                alt.Tooltip("mean_r_squared:Q", title="Mittleres R²", format=".5f"),
            ],
        )
    )


def _residual_chart(residuals: pd.DataFrame) -> alt.LayerChart:
    points = (
        alt.Chart(_grouped(residuals))
        .mark_circle(size=70, opacity=0.9)
        .encode(
            x=alt.X("measurement_angle:Q", title="Messwinkel (Grad)"),
            y=alt.Y("residual:Q", title="Residuum (Grad)"),
            color=alt.Color("group:N", title="Experiment / Probe", scale=_color_scale()),
            tooltip=[
                alt.Tooltip("experiment_id:N", title="Experiment"),
                alt.Tooltip("sample_id:N", title="Probe"),
                alt.Tooltip("measurement_angle:Q", title="Winkel (°)", format=".2f"),
                alt.Tooltip("residual:Q", title="Residuum (°)", format=".3f"),
            ],
        )
    )
    zero = (
        alt.Chart(pd.DataFrame({"zero": [0.0]}))
        .mark_rule(color="#94a3b8", strokeDash=[4, 4])
        .encode(y="zero:Q")
    )
    return points + zero


# ---------------------------------------------------------------------------
# Sidebar: data source and filters
# ---------------------------------------------------------------------------

with st.sidebar:
    st.subheader("Datenquelle", divider=False)
    source_label = st.segmented_control(
        "Datenquelle",
        options=list(SOURCE_LABELS),
        default="Automatisch",
        label_visibility="collapsed",
        width="stretch",
    )
    source_key = SOURCE_LABELS.get(source_label or "Automatisch", SOURCE_AUTO)

    with st.expander("Verbindung", icon=":material/database:"):
        database_url = st.text_input(
            "DATABASE_URL",
            value=DEFAULT_DATABASE_URL,
            help="Verbindungszeichenfolge für PostgreSQL (wird nur gelesen).",
        )
        if st.button("Daten neu laden", icon=":material/refresh:", width="stretch"):
            _load.clear()

    try:
        with st.spinner("Daten werden geladen …"):
            data = _load(source_key, database_url)
    except Exception as exc:  # noqa: BLE001 - keep the failure readable in the UI
        st.error(
            str(exc),
            title="Daten konnten nicht geladen werden",
            icon=":material/error:",
        )
        st.caption(
            "Prüfe, ob PostgreSQL läuft (`docker compose up -d db`) oder ob "
            "`python -m src.main process` bereits Dateien erzeugt hat."
        )
        st.stop()

    measurements = data.measurements
    experiment_options = (
        sorted(measurements["experiment_id"].unique()) if not measurements.empty else []
    )
    selected_experiments = st.multiselect(
        "Experiment",
        options=experiment_options,
        default=experiment_options,
        placeholder="Alle Experimente",
    )

    sample_source = (
        measurements[measurements["experiment_id"].isin(selected_experiments)]
        if selected_experiments
        else measurements
    )
    sample_options = sorted(sample_source["sample_id"].unique()) if not sample_source.empty else []
    selected_samples = st.multiselect(
        "Probe",
        options=sample_options,
        default=sample_options,
        placeholder="Alle Proben",
    )

    angle_range: tuple[float, float] | None = None
    if not sample_source.empty:
        low = float(sample_source["measurement_angle"].min())
        high = float(sample_source["measurement_angle"].max())
        if low < high:
            angle_range = st.slider(
                "Messwinkel (Grad)",
                min_value=low,
                max_value=high,
                value=(low, high),
                step=(high - low) / 100,
            )

    st.caption(
        "Die mitgelieferten CSVs unter `data/raw` sind synthetische "
        "Beispieldaten, keine echten Labormessungen."
    )

# ---------------------------------------------------------------------------
# Filtered view
# ---------------------------------------------------------------------------

if not selected_experiments:
    st.info(
        "Kein Experiment ausgewählt. Wähle links mindestens ein Experiment.",
        icon=":material/filter_alt:",
    )
    st.stop()

filtered_measurements = filter_measurements(
    measurements, selected_experiments, selected_samples, angle_range
)
filtered_regressions = filter_regressions(
    data.regressions, selected_experiments, selected_samples
)
view_data = build_view(data, filtered_measurements, filtered_regressions)
summary = summarize(view_data)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

title_col, badge_col = st.columns([3, 1], vertical_alignment="center")
with title_col:
    st.title("Polarimetrie-Dashboard")
    st.caption(
        "Optische Polarisationsmessungen — Validierung, lineare Regression und "
        "Datenqualität aus einer Quelle."
    )
with badge_col:
    st.badge(f"Quelle: {data.source_label}", color="blue", icon=":material/database:")
    st.badge("Synthetische Beispieldaten", color="orange", icon=":material/science:")

if data.warning:
    st.warning(data.warning, icon=":material/cloud_off:")

if filtered_measurements.empty:
    st.info(
        "Für diese Filter sind keine Messungen vorhanden.",
        icon=":material/search_off:",
    )
    st.stop()

with st.container(horizontal=True):
    st.metric("Messungen", _format_number(summary["measurements"]), border=True)
    st.metric("Experimente", _format_number(summary["experiments"]), border=True)
    st.metric("Proben", _format_number(summary["samples"]), border=True)
    st.metric("Regressionen", _format_number(summary["regressions"]), border=True)
    st.metric(
        "Mittleres R²",
        _format_number(summary["mean_r_squared"], 4),
        border=True,
    )
    st.metric("Abgewiesene Zeilen", _format_number(summary["rejected"]), border=True)

st.write("")

view = st.segmented_control(
    "Ansicht",
    options=VIEWS,
    default="Übersicht",
    label_visibility="collapsed",
    width="stretch",
)
view = view or "Übersicht"

# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

if view == "Übersicht":
    with st.container(border=True):
        st.subheader("Drehung über Messwinkel")
        st.altair_chart(
            _scatter_with_fit(filtered_measurements, filtered_regressions),
            alt="Streudiagramm der Messpunkte mit einer Regressionsgeraden je Experiment und Probe",
        )
        st.caption(
            "Modell: beobachtete Drehung = Steigung × Messwinkel + Achsenabschnitt. "
            "Beide Achsen in Grad."
        )

    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            st.subheader("Verteilung der Drehung")
            st.altair_chart(
                _histogram(filtered_measurements),
                alt="Histogramm der beobachteten Drehung mit Markierung des Mittelwerts",
            )
    with right:
        with st.container(border=True):
            st.subheader("Vergleich der Experimente")
            if filtered_regressions.empty:
                st.info("Noch keine Regression verfügbar.", icon=":material/functions:")
            else:
                st.altair_chart(
                    _comparison_chart(compare_experiments(filtered_regressions)),
                    alt="Balkendiagramm der mittleren Steigung je Experiment",
                )

elif view == "Regressionen":
    with st.container(border=True):
        st.subheader("Regressionsergebnisse")
        if filtered_regressions.empty:
            st.info(
                "Pro Experiment/Probe werden mindestens zwei Messpunkte mit "
                "unterschiedlichem Winkel benötigt.",
                icon=":material/functions:",
            )
        else:
            table = filtered_regressions.copy()
            table["Gleichung"] = table.apply(equation, axis=1)
            st.dataframe(
                table[
                    [
                        "experiment_id",
                        "sample_id",
                        "n_points",
                        "slope",
                        "intercept",
                        "r_squared",
                        "slope_std_error",
                        "residual_std_error",
                        "Gleichung",
                    ]
                ],
                hide_index=True,
                column_config={
                    "experiment_id": st.column_config.TextColumn("Experiment"),
                    "sample_id": st.column_config.TextColumn("Probe"),
                    "n_points": st.column_config.NumberColumn("Punkte", format="%d"),
                    "slope": st.column_config.NumberColumn("Steigung", format="%.4f"),
                    "intercept": st.column_config.NumberColumn(
                        "Achsenabschnitt (°)", format="%.4f"
                    ),
                    "r_squared": st.column_config.NumberColumn("R²", format="%.5f"),
                    "slope_std_error": st.column_config.NumberColumn(
                        "SE Steigung", format="%.4f"
                    ),
                    "residual_std_error": st.column_config.NumberColumn(
                        "SE Residuen", format="%.4f"
                    ),
                },
                alt="Tabelle der linearen Regressionen je Experiment und Probe",
            )
            st.caption(
                "Standardfehler werden erst ab drei Messpunkten berechnet. "
                "R² ist ein Anpassungsmaß, kein Beweis für ein physikalisches Modell."
            )

    with st.container(border=True):
        st.subheader("Residuen")
        if view_data.residuals.empty:
            st.info("Keine Residuen verfügbar.", icon=":material/timeline:")
        else:
            st.altair_chart(
                _residual_chart(view_data.residuals),
                alt="Residuen der Regression gegen den Messwinkel",
            )
            st.caption("Residuum = beobachtete Drehung − vorhergesagte Drehung (Grad).")

elif view == "Datenqualität":
    with st.container(border=True):
        st.subheader("Qualität je Quelldatei")
        if data.quality.empty:
            st.info("Keine Qualitätsdaten vorhanden.", icon=":material/fact_check:")
        else:
            st.dataframe(
                data.quality,
                hide_index=True,
                column_config={
                    "source_file": st.column_config.TextColumn("Quelldatei"),
                    "total_rows": st.column_config.NumberColumn("Zeilen", format="%d"),
                    "valid_rows": st.column_config.NumberColumn("Gültig", format="%d"),
                    "invalid_rows": st.column_config.NumberColumn("Ungültig", format="%d"),
                    "duplicate_rows": st.column_config.NumberColumn("Duplikate", format="%d"),
                    "rejected_rows": st.column_config.NumberColumn("Abgewiesen", format="%d"),
                },
                alt="Datenqualität je Quelldatei",
            )

    with st.container(border=True):
        st.subheader("Abgewiesene Zeilen")
        if data.issues.empty:
            st.success(
                "Keine abgewiesenen Zeilen. Alle eingelesenen Messungen sind gültig.",
                icon=":material/check_circle:",
            )
        else:
            st.dataframe(
                data.issues,
                hide_index=True,
                column_config={
                    "source_file": st.column_config.TextColumn(
                        "Quelldatei", width="medium"
                    ),
                    "source_row": st.column_config.NumberColumn("Zeile", format="%d"),
                    "status": st.column_config.TextColumn("Status"),
                    "experiment_id": st.column_config.TextColumn("Experiment"),
                    "sample_id": st.column_config.TextColumn("Probe"),
                    "measurement_angle": st.column_config.TextColumn("Winkel (roh)"),
                    "observed_rotation": st.column_config.TextColumn("Drehung (roh)"),
                    "measurement_timestamp": st.column_config.TextColumn(
                        "Zeitstempel (roh)"
                    ),
                    "validation_errors": st.column_config.TextColumn(
                        "Begründung", width="large"
                    ),
                },
                alt="Liste der abgewiesenen Zeilen mit Begründung",
            )
            st.caption(
                "Abgewiesene Zeilen bleiben in der Quelldatei und in `raw_measurements` "
                "erhalten; sie werden nur aus der Analyse ausgeschlossen."
            )

    with st.container(border=True):
        st.subheader("Importverlauf")
        if data.imports.empty:
            st.info(
                "Der Importverlauf ist nur mit PostgreSQL verfügbar.",
                icon=":material/history:",
            )
        else:
            st.dataframe(
                data.imports,
                hide_index=True,
                column_config={
                    "source_file": st.column_config.TextColumn("Datei", width="large"),
                    "imported_at": st.column_config.DatetimeColumn(
                        "Importiert", format="DD.MM.YYYY HH:mm"
                    ),
                    "n_rows": st.column_config.NumberColumn("Zeilen", format="%d"),
                    "n_valid": st.column_config.NumberColumn("Gültig", format="%d"),
                    "n_invalid": st.column_config.NumberColumn("Ungültig", format="%d"),
                    "n_duplicates": st.column_config.NumberColumn("Duplikate", format="%d"),
                },
                alt="Importverlauf der eingelesenen CSV-Dateien",
            )

elif view == "Messwerte":
    st.dataframe(
        filtered_measurements,
        hide_index=True,
        column_config={
            "experiment_id": st.column_config.TextColumn("Experiment"),
            "sample_id": st.column_config.TextColumn("Probe"),
            "measurement_angle": st.column_config.NumberColumn(
                "Messwinkel (°)", format="%.2f"
            ),
            "observed_rotation": st.column_config.NumberColumn(
                "Drehung (°)", format="%.2f"
            ),
            "measurement_timestamp": st.column_config.DatetimeColumn(
                "Zeitstempel (UTC)", format="DD.MM.YYYY HH:mm:ss"
            ),
        },
        alt="Gefilterte Tabelle der gültigen Messwerte",
    )
    st.download_button(
        "Gefilterte Messwerte als CSV",
        data=filtered_measurements.to_csv(index=False).encode("utf-8"),
        file_name="filtered_measurements.csv",
        mime="text/csv",
        icon=":material/download:",
    )

    with st.container(border=True):
        st.subheader("Deskriptive Statistik")
        st.dataframe(
            view_data.descriptive,
            hide_index=True,
            column_config={
                "experiment_id": st.column_config.TextColumn("Experiment"),
                "sample_id": st.column_config.TextColumn("Probe"),
                "n_points": st.column_config.NumberColumn("Punkte", format="%d"),
                "mean_angle_deg": st.column_config.NumberColumn(
                    "Ø Winkel (°)", format="%.2f"
                ),
                "std_angle_deg": st.column_config.NumberColumn(
                    "s Winkel (°)", format="%.2f"
                ),
                "min_angle_deg": st.column_config.NumberColumn(
                    "Min. Winkel (°)", format="%.2f"
                ),
                "max_angle_deg": st.column_config.NumberColumn(
                    "Max. Winkel (°)", format="%.2f"
                ),
                "mean_rotation_deg": st.column_config.NumberColumn(
                    "Ø Drehung (°)", format="%.2f"
                ),
                "std_rotation_deg": st.column_config.NumberColumn(
                    "s Drehung (°)", format="%.2f"
                ),
                "min_rotation_deg": st.column_config.NumberColumn(
                    "Min. Drehung (°)", format="%.2f"
                ),
                "max_rotation_deg": st.column_config.NumberColumn(
                    "Max. Drehung (°)", format="%.2f"
                ),
            },
            alt="Deskriptive Statistik je Experiment und Probe",
        )

st.caption(
    "Nur lesender Zugriff. Neue Daten werden mit "
    "`python -m src.main process` verarbeitet und gespeichert."
)
