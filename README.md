<div align="center">

<img src="docs/images/banner.svg" alt="Experimental Data Processing – Banner" width="100%">

<br>

<img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white" alt="Python 3.11+">
<img src="https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white" alt="PostgreSQL 16">
<img src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white" alt="Docker Compose">
<img src="https://img.shields.io/badge/Tests-47%20bestanden-success" alt="47 Tests bestanden">
<img src="https://img.shields.io/badge/Status-einsatzbereit-success" alt="Status einsatzbereit">

<h3>Kleine, reproduzierbare Datenpipeline für optische Polarisationsmessungen</h3>

<p>
Vom Mess-CSV über Validierung und PostgreSQL bis zu Regression, Plots und Bericht –
mit einem einzigen Befehl.
</p>

<p>
<a href="#schnellstart">Schnellstart</a> ·
<a href="#csv-format">CSV-Format</a> ·
<a href="#statistik">Statistik</a> ·
<a href="#datenbank">Datenbank</a> ·
<a href="#ausgaben">Ausgaben</a>
</p>

</div>

---

> **Kurz gesagt:** Das Programm liest alle CSV-Dateien aus `data/raw`, prüft und
> bereinigt die Messwerte, speichert Roh- und Prozessdaten in PostgreSQL, führt
> pro Experiment/Probe eine lineare Regression durch und erzeugt PNG-Plots,
> CSV-Tabellen sowie einen lesbaren Markdown-Bericht.

> [!IMPORTANT]
> Die mitgelieferten CSV-Dateien in `data/raw` und die Screenshots in diesem
> README stammen aus **synthetischen Beispieldaten**. Sie sind keine echten
> Labormessungen. Vor dem Einsatz mit Forschungsdaten müssen sie ersetzt werden.

## Überblick

Dieses Projekt ist bewusst als **kleines internes Werkzeug** geschnitten – nicht
als Plattform. Es gibt keinen Scheduler, keine Microservices und keine zusätzliche
Infrastruktur. Ein Forschungsteam kann Messdateien in einen Ordner legen, einen
Befehl ausführen und erhält nachvollziehbare Ergebnisse. Ein optionales,
**rein lesendes Dashboard** macht dieselben Ergebnisse zusätzlich im Browser
erkundbar.

| Eigenschaft | Umsetzung |
| --- | --- |
| Eingabe | Eine oder mehrere CSV-Dateien in `data/raw` |
| Validierung | Fehlende Werte, Zahlenfehler, Wertebereiche, Zeitstempel, Duplikate |
| Speicherung | PostgreSQL mit Roh-, Prozess- und Regressionsdaten |
| Analyse | Deskriptive Statistik und OLS-Regression mit SciPy/NumPy |
| Ausgabe | PNG-Plots, CSV-Tabellen, `summary.md` |
| Schnittstelle | Kommandozeile (CLI) und optionales Streamlit-Dashboard |
| Tests | 67 pytest-Tests, inklusive synthetischer Regressionen mit bekannten Ergebnissen |
| Betrieb | Python lokal, PostgreSQL ausschließlich per Docker Compose |

## Workflow

```mermaid
flowchart LR
    A[CSV-Dateien<br/>data/raw] --> B[Ingestion]
    B --> C[Validierung]
    C -->|gültig| D[Cleaning]
    C -->|ungültig / Duplikat| Q[Quality Report<br/>Quarantäne]
    D --> E[(PostgreSQL)]
    D --> F[Statistik<br/>OLS-Regression]
    E --> G[Historie / SQL]
    F --> H[PNG-Plots<br/>CSV-Tabellen<br/>summary.md]
    E --> I[Streamlit-Dashboard<br/>nur lesend]
    H --> I

    style A fill:#0c4a6e,stroke:#38bdf8,color:#e0f2fe
    style C fill:#1e293b,stroke:#64748b,color:#e2e8f0
    style Q fill:#451a03,stroke:#f59e0b,color:#fef3c7
    style E fill:#172554,stroke:#4169e1,color:#dbeafe
    style H fill:#14532d,stroke:#22c55e,color:#dcfce7
    style I fill:#3b0764,stroke:#a78bfa,color:#f3e8ff
```

## Funktionen

- **Mehrere Dateien und Experimente** in einem Lauf.
- **Keine stillen Datenverluste:** ungültige Zeilen bleiben in der Datenbank und
  im Quality Report erhalten.
- **Idempotente Importe:** unveränderte Dateien werden über ihren SHA-256-Wert
  erkannt; bereits gespeicherte Messpunkte werden nicht doppelt angelegt.
- **Nachvollziehbare Rohdaten:** die ursprünglichen Textwerte werden getrennt von
  den bereinigten Zahlen gespeichert.
- **Eine Regression pro Experiment/Probe** mit Steigung, Achsenabschnitt,
  R², Standardfehlern und Residuen.
- **Deskriptiver Experimentvergleich** ohne voreilige Signifikanzaussagen.
- **Automatische Berichte** als PNG, CSV und Markdown.
- **Historie und SQL-Zugriff** auf alle gespeicherten Ergebnisse.
- **Optionales Dashboard:** interaktive Filter, Regressionsgeraden, Residuen,
  Datenqualität und CSV-Download – wahlweise aus PostgreSQL oder aus den
  lokalen Berichtsdateien.

## Screenshots

<p align="center">
  <img src="docs/images/rotation_vs_angle.png" alt="Beobachtete Rotation gegen Messwinkel mit Regressionsgeraden" width="49%">
  <img src="docs/images/regression_residuals.png" alt="Residuenplot der linearen Regression" width="49%">
</p>

<p align="center">
  <img src="docs/images/rotation_histogram.png" alt="Histogramm der beobachteten Rotation" width="62%">
</p>

<p align="center">
  <em>Synthetische Beispieldaten: drei Experiment/Probe-Gruppen mit je zehn Messpunkten.</em>
</p>

## Schnellstart

### Voraussetzungen

- Python **3.11 oder neuer**
- Docker mit Docker Compose
- Git (optional, aber empfohlen)

### Windows (PowerShell)

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

### Was passiert bei `process`?

1. Alle `*.csv`-Dateien aus `data/raw` werden gelesen.
2. Jede Zeile wird validiert und als `valid`, `invalid` oder `duplicate` markiert.
3. Rohdaten und bereinigte Messwerte werden in PostgreSQL gespeichert.
4. Pro Experiment/Probe wird eine OLS-Regression berechnet.
5. Plots, Tabellen und `summary.md` werden geschrieben.

Die Datenbanktabellen werden bei Bedarf automatisch angelegt. Ein separates
`init-db` ist optional:

```bash
python -m src.main init-db
```

### Nützliche Befehle

```bash
# Nur lokal validieren und Berichte erzeugen, ohne PostgreSQL
python -m src.main process --skip-db

# Anderes Eingabeverzeichnis verwenden
python -m src.main process --input "C:\Messdaten\Polarisation"

# Gespeicherte Historie anzeigen
python -m src.main history
python -m src.main history --experiment EXP-001

# Dashboard starten (http://localhost:8501)
python -m src.main dashboard

# Tests ausführen
python -m pytest

# PostgreSQL stoppen; das Docker-Volume bleibt erhalten
docker compose down
```

## Dashboard

Das Dashboard ist optional und **nur lesend**. Es verändert weder Datenbank noch
Dateien; neue Ergebnisse entstehen weiterhin über `python -m src.main process`.

```bash
python -m src.main dashboard
```

Alternativ lässt es sich direkt starten:

```bash
streamlit run src/dashboard.py
```

Danach ist die Oberfläche unter <http://localhost:8501> erreichbar. Das Design
kommt aus `.streamlit/config.toml` und übernimmt die Farben des Projektbanners.

| Ansicht | Inhalt |
| --- | --- |
| Übersicht | Streudiagramm mit Regressionsgeraden, Histogramm, Experimentvergleich |
| Regressionen | Tabelle mit Gleichung, Steigung, R² und Standardfehlern, Residuenplot |
| Datenqualität | Qualität je Quelldatei, abgewiesene Zeilen mit Begründung, Importverlauf |
| Messwerte | gefilterte Tabelle, deskriptive Statistik und CSV-Download |

Die Seitenleiste filtert nach Experiment, Probe und Messwinkel. Als Datenquelle
stehen `Automatisch`, `PostgreSQL` und `Lokale Dateien` zur Wahl:

- **Automatisch** versucht zuerst PostgreSQL und fällt bei fehlender Verbindung
  auf `data/processed` und `output/reports` zurück.
- **PostgreSQL** zeigt die gespeicherten Roh-, Prozess- und Regressionsdaten
  inklusive Importverlauf und abgewiesener Zeilen.
- **Lokale Dateien** liest die Artefakte des letzten `process`-Laufs und
  funktioniert auch ohne laufenden Docker-Container.

Für eine frische Installation – etwa auf Streamlit Community Cloud – liegen
unter `data/demo` kleine, synthetische Beispielartefakte. Fehlen
`data/processed` und `output/reports`, greift das Dashboard automatisch darauf
zurück und zeigt einen entsprechenden Hinweis an. Der Einstiegspunkt für
Streamlit Community Cloud ist `streamlit_app.py`; die eigentliche App bleibt
`src/dashboard.py`.

Die mitgelieferten CSVs sind synthetische Beispieldaten; das Dashboard weist
darauf sichtbar hin.

## CSV-Format

Jede Datei muss UTF-8-kodiert sein, eine Kopfzeile besitzen und die folgenden
fünf Spalten enthalten. Die Spaltennamen sind **kleingeschrieben und
case-sensitiv**.

| Spalte | Typ | Einheit | Bedeutung |
| --- | --- | --- | --- |
| `experiment_id` | Text | – | Experimentkennung, maximal 64 Zeichen, z. B. `EXP-001` |
| `sample_id` | Text | – | Probenkennung innerhalb des Experiments, maximal 64 Zeichen |
| `measurement_angle` | Zahl | Grad | Winkel des Analysators/Polarisators relativ zur Nullreferenz |
| `observed_rotation` | Zahl | Grad | Gemessene Drehung der Polarisationsebene |
| `measurement_timestamp` | ISO-8601 | – | Messzeitpunkt; wird nach UTC normalisiert |

Beispiel:

```csv
experiment_id,sample_id,measurement_angle,observed_rotation,measurement_timestamp
EXP-001,S-01,0,1.2,2026-05-12T08:00:00Z
EXP-001,S-01,10,9.4,2026-05-12T08:01:00Z
EXP-001,S-01,20,17.1,2026-05-12T08:02:00Z
```

### Formatannahmen

- Eine Zeile entspricht einer Messung.
- Dezimaltrennzeichen ist der Punkt (`.`), nicht das Komma.
- Zeitstempel sind ISO-8601. Werte mit Offset werden nach UTC umgerechnet;
  Werte ohne Offset werden als UTC interpretiert.
- Leere Zahlen- oder Textfelder sind ungültig und werden nicht als Null behandelt.
- Zusätzliche Spalten sind erlaubt, werden aber nicht in die Datenbank übernommen.
  Die Originaldatei bleibt die maßgebliche Quelle.
- Ein Duplikat liegt vor, wenn `experiment_id`, `sample_id`,
  `measurement_angle` und `measurement_timestamp` exakt übereinstimmen.
  Wiederholungen am selben Winkel mit anderem Zeitstempel sind erlaubt.
- Dateien werden niemals verändert oder gelöscht.

## Validierung und Cleaning

Jede Zeile erhält genau einen Status:

| Status | Bedeutung |
| --- | --- |
| `valid` | Wird für Analyse und Regression verwendet |
| `invalid` | Fehlender Wert, keine endliche Zahl, außerhalb des Bereichs, ungültiger Zeitstempel oder zu lange Kennung |
| `duplicate` | Gleicher Messpunkt wie eine frühere Zeile |

Wenn eine Zeile sowohl dupliziert als auch anderweitig ungültig ist, wird sie als
`invalid` geführt; das Duplikat-Merkmal bleibt im Quality Report sichtbar.

### Standardbereiche

| Größe | Standardbereich |
| --- | --- |
| `measurement_angle` | −360 bis 360 Grad |
| `observed_rotation` | −180 bis 180 Grad |

Die Bereiche sind Qualitätsgrenzen, keine physikalischen Konstanten. Sie können
pro Lauf angepasst werden:

```bash
python -m src.main process \
  --angle-min -90 --angle-max 90 \
  --rotation-min -45 --rotation-max 45
```

Ungültige und duplizierte Zeilen werden **nicht stillschweigend gelöscht**:

- Sie bleiben in `raw_measurements` mit Status und Begründung erhalten.
- Sie stehen in `output/reports/quality_issues.csv`.
- Die Zählungen pro Datei stehen in `data_quality_report.csv` und `summary.md`.
- Nur `valid`-Zeilen gelangen in `processed_measurements` und in die Statistik.

## Statistik

Für jede Kombination aus Experiment und Probe wird eine gewöhnliche
Kleinste-Quadrate-Regression (OLS) berechnet:

```text
observed_rotation = slope · measurement_angle + intercept
```

- Beide Größen sind in Grad. Die Steigung hat die Einheit Grad/Grad, der
  Achsenabschnitt die Einheit Grad.
- Die Regression ist ungewichtet, weil das CSV-Format keine Unsicherheit pro
  Messpunkt enthält.
- Standardfehler für Steigung und Achsenabschnitt sowie der Residualstandardfehler
  werden ab drei Messpunkten berichtet. Bei genau zwei Punkten ist die Gerade
  exakt bestimmt; Standardfehler werden dann als `NaN`/`NULL` geführt.
- R² ist ein Gütemaß der Anpassung und kein Beweis für ein physikalisches Modell.
- Annahmen: annähernd linearer Zusammenhang im Messbereich, unabhängige Fehler
  und näherungsweise konstante Fehlervarianz. Die Residuenplots dienen der
  visuellen Prüfung.
- Der Experimentvergleich ist **deskriptiv** (mittlere Steigung, mittlerer
  Achsenabschnitt). Es werden keine Signifikanztests zwischen Experimenten
  behauptet.

### Beispielergebnisse (synthetisch)

| Experiment | Probe | n | Steigung | Achsenabschnitt | R² |
| --- | --- | ---: | ---: | ---: | ---: |
| EXP-001 | S-01 | 10 | 0.821455 | 0.834545 | 0.999762 |
| EXP-001 | S-02 | 10 | 0.550121 | −0.965455 | 0.999918 |
| EXP-002 | S-03 | 10 | 1.021939 | 0.392727 | 0.999932 |

Diese Werte stammen aus den mitgelieferten Beispieldaten und dienen nur der
Demonstration der Pipeline.

## Datenbank

PostgreSQL speichert sechs kleine Tabellen mit Primärschlüsseln, Fremdschlüsseln,
Unique- und Check-Constraints.

```mermaid
erDiagram
    experiments ||--o{ samples : enthält
    experiments ||--o{ processed_measurements : gruppiert
    samples ||--o{ processed_measurements : liefert
    imports ||--o{ raw_measurements : enthält
    raw_measurements ||--o| processed_measurements : bereinigt_zu
    experiments ||--o{ regression_results : besitzt
    samples ||--o{ regression_results : erzeugt

    experiments {
        int id PK
        string experiment_id UK
        string title
        timestamp created_at
    }
    samples {
        int id PK
        int experiment_id FK
        string sample_id
        timestamp created_at
    }
    imports {
        int id PK
        string source_file
        string file_sha256 UK
        timestamp imported_at
        int n_rows
        int n_valid
        int n_invalid
        int n_duplicates
    }
    raw_measurements {
        int id PK
        int import_id FK
        int source_row
        text experiment_id
        text sample_id
        text measurement_angle
        text observed_rotation
        text measurement_timestamp
        string status
        text validation_errors
    }
    processed_measurements {
        int id PK
        int raw_measurement_id FK
        int experiment_id FK
        int sample_id FK
        float measurement_angle
        float observed_rotation
        timestamp measurement_timestamp
    }
    regression_results {
        int id PK
        int experiment_id FK
        int sample_id FK
        int n_points
        float slope
        float intercept
        float r_squared
        float slope_std_error
        float intercept_std_error
        float residual_std_error
        timestamp computed_at
    }
```

### Wiederholte Importe

- **Gleicher Datei-Checksum:** Der Dateiimport wird übersprungen.
- **Veränderte Datei:** Rohzeilen werden erneut protokolliert, bereits gespeicherte
  Messpunkte aber nicht doppelt angelegt.
- **Erneute Regression:** Ergebnisse werden pro Experiment/Probe aktualisiert,
  nicht dupliziert.

### Warum kein Alembic?

Das Projekt startet mit einem kleinen, stabilen Schema. `Base.metadata.create_all`
reicht dafür aus. Alembic wäre zusätzliche Komplexität ohne aktuellen Nutzen.
Sobald echte Daten vorliegen und das Schema migriert werden muss, ist Alembic der
richtige nächste Schritt.

## Ausgaben

```text
data/processed/processed_measurements.csv   bereinigte Messwerte
output/plots/rotation_vs_angle.png          Streudiagramm + Regressionsgeraden
output/plots/regression_residuals.png       Residuen der Regression
output/plots/rotation_histogram.png         Verteilung der Rotation
output/reports/data_quality_report.csv      Qualitätszählungen pro Datei
output/reports/quality_issues.csv           abgelehnte Zeilen mit Begründung
output/reports/descriptive_statistics.csv   Statistik pro Experiment/Probe
output/reports/regression_results.csv       Steigung, Achsenabschnitt, R², SE
output/reports/residuals.csv                beobachtet / vorhergesagt / Residuum
output/reports/experiment_comparison.csv    deskriptiver Experimentvergleich
output/reports/summary.md                   lesbarer Gesamtbericht
```

Die Plots werden mit dem nicht-interaktiven `Agg`-Backend von Matplotlib erzeugt.
Wenn keine gültigen Zeilen vorhanden sind, werden Tabellen und Quality Report
trotzdem geschrieben; Plots werden übersprungen.

## CLI-Referenz

| Befehl | Zweck |
| --- | --- |
| `python -m src.main init-db` | Datenbanktabellen anlegen |
| `python -m src.main process` | Vollständige Pipeline ausführen |
| `python -m src.main process --skip-db` | Nur validieren und lokale Berichte erzeugen |
| `python -m src.main process --input <dir>` | Anderes Eingabeverzeichnis verwenden |
| `python -m src.main process --output <dir>` | Anderes Ausgabeverzeichnis verwenden |
| `python -m src.main history` | Gespeicherte Messungen und Regressionen anzeigen |
| `python -m src.main history --experiment EXP-001` | Historie auf ein Experiment begrenzen |
| `python -m src.main dashboard` | Dieses Dashboard auf Port 8501 starten |
| `python -m src.main dashboard --port 8502` | Dashboard auf einem anderen Port starten |
| `python -m src.main process --angle-min ...` | Qualitätsgrenzen anpassen |

Die Standard-Datenbank-URL lautet:

```text
postgresql+psycopg://lab_user:lab_password@127.0.0.1:5434/experimental_data
```

Sie kann über `--database-url` oder die Umgebungsvariable `DATABASE_URL`
überschrieben werden.

## SQL-Abfragen

Die Dateien in `sql/queries/` sind direkt für PostgreSQL gedacht:

| Datei | Inhalt |
| --- | --- |
| `measurements_by_experiment.sql` | Messungen eines Experiments |
| `average_rotation_by_sample.sql` | Mittelwerte und Streuung pro Probe |
| `sample_comparison.sql` | Vergleich der Proben anhand der Regression |
| `regression_results.sql` | Gespeicherte Regressionsergebnisse |
| `data_quality_summary.sql` | Qualitätsübersicht pro Import |
| `experiment_comparison.sql` | Deskriptiver Vergleich der Experimente |

Beispiel unter PowerShell:

```powershell
Get-Content -Raw sql\queries\measurements_by_experiment.sql |
  docker exec -i experimental_data_db psql -U lab_user -d experimental_data `
    -v experiment_id=EXP-001 -f -
```

Unter Linux/macOS:

```bash
docker exec -i experimental_data_db psql -U lab_user -d experimental_data \
  -v experiment_id=EXP-001 -f - \
  < sql/queries/measurements_by_experiment.sql
```

`sql/schema.sql` ist eine lesbare PostgreSQL-Referenz. Die Anwendung erzeugt die
Tabellen selbst über SQLAlchemy.

## Tests

```bash
python -m pytest
```

Aktueller Stand:

```text
67 passed
```

Die Tests decken ab:

- CSV-Parsing, Pflichtspalten, doppelte Kopfzeilen, mehrere Dateien und Checksums,
- sämtliche Validierungsregeln, Duplikaterkennung und Quality Reports,
- Cleaning und Ausschluss ungültiger Zeilen,
- exakte synthetische Regressionen mit bekannten Steigungen, Achsenabschnitten
  und Standardfehlern,
- Datenbankpersistenz, Rohdatenhaltung, idempotente Importe und Regression-Roundtrips,
- Plot-/Report-Erzeugung und den vollständigen CLI-Durchlauf,
- Dashboard-Datenzugriff, Filter, Residuen, Datenquellen-Fallback,
  Demo-Daten sowie abgewiesene Zeilen aus PostgreSQL,
- alle vier Dashboard-Ansichten über den Streamlit-`AppTest`-Runner.

Die automatisierten Datenbanktests verwenden eine SQLite-In-Memory-Datenbank, damit
sie schnell und portabel sind. Derselbe SQLAlchemy-Code und der vollständige
Workflow wurden zusätzlich gegen PostgreSQL 16 in Docker geprüft.

## Projektstruktur

```text
experimental-data-tool/
├── data/
│   ├── raw/                    # Eingabe-CSVs (werden nie verändert)
│   ├── processed/              # bereinigte Messwerte
│   └── demo/                   # synthetische Demo-Artefakte für die Cloud
├── docs/
│   └── images/                 # Banner und Screenshots für dieses README
├── output/
│   ├── plots/                  # PNG-Abbildungen
│   └── reports/                # CSV-Tabellen und summary.md
├── sql/
│   ├── schema.sql              # PostgreSQL-Referenzschema
│   └── queries/                # analytische SQL-Abfragen
├── src/
│   ├── ingestion.py            # CSV-Erkennung, Lesen, Checksums
│   ├── validation.py           # Zeilenprüfung und Quality Report
│   ├── cleaning.py             # Auswahl typisierter gültiger Zeilen
│   ├── analysis.py             # Deskriptive Statistik und OLS
│   ├── database.py             # SQLAlchemy-Modelle und Persistenz
│   ├── reports.py              # Matplotlib, CSV und Markdown
│   ├── dashboard.py            # Streamlit-Oberfläche (nur lesend)
│   ├── dashboard_data.py       # Datenzugriff und Filter ohne Streamlit-Abhängigkeit
│   ├── config.py               # Pfade und Standard-Datenbank-URL
│   └── main.py                 # Kommandozeilen-Schnittstelle
├── tests/
├── .streamlit/
│   └── config.toml             # Dark Theme und Browser-Einstellungen
├── streamlit_app.py            # Einstiegspunkt für Streamlit Community Cloud
├── docker-compose.yml          # ausschließlich PostgreSQL
├── requirements.txt
├── pytest.ini
├── .env.example
├── .gitignore
└── README.md
```

## Entwurfsentscheidungen

- **Batch zuerst, Dashboard optional.** Der reproduzierbare Kern bleibt ein
  CLI-Lauf. Das Streamlit-Dashboard ist eine rein lesende Zusatzansicht ohne
  eigenen Zustand, ohne Schreibzugriff und ohne zusätzliche Infrastruktur; es
  kann jederzeit weggelassen werden.
- **Nur PostgreSQL läuft in Docker.** Die Python-Anwendung bleibt lokal in einer
  virtuellen Umgebung.
- **Keine stillen Löschungen.** Abgelehnte Zeilen sind in Datenbank und Bericht
  sichtbar.
- **Keine erfundene physikalische Bedeutung.** Die Standardbereiche sind
  Qualitätsgrenzen, keine Naturkonstanten.
- **Keine Unsicherheitsfortpflanzung.** Ohne Unsicherheitsspalte im CSV ist eine
  ungewichtete OLS die ehrliche Wahl.
- **Keine Signifikanztests zwischen Experimenten.** Der Vergleich bleibt
  deskriptiv, solange kein statistisches Design festgelegt ist.
- **Schemaänderungen brauchen Sorgfalt.** `create_all` migriert keine bestehenden
  Tabellen. Bei echten Daten mit Schemaänderungen sollte Alembic ergänzt werden.

## Fehlerbehebung

<details>
<summary><strong>Datenbankverbindung wird abgelehnt</strong></summary>

```bash
docker compose up -d db
docker compose ps
```

Warten, bis der Healthcheck erfolgreich ist, dann erneut ausführen.
</details>

<details>
<summary><strong>Port 5434 ist bereits belegt</strong></summary>

Host-Port in `docker-compose.yml` ändern und `DATABASE_URL` bzw.
`--database-url` anpassen.
</details>

<details>
<summary><strong>Keine CSV-Dateien gefunden</strong></summary>

Mindestens eine `.csv`-Datei in `data/raw` legen oder
`--input <verzeichnis>` verwenden.
</details>

<details>
<summary><strong>Pflichtspalte fehlt</strong></summary>

Kopfzeile mit den fünf erforderlichen Spalten prüfen. Die Namen sind
case-sensitiv.
</details>

<details>
<summary><strong>Dashboard zeigt keine Daten</strong></summary>

Entweder zuerst `python -m src.main process` ausführen oder im Dashboard unter
`Datenquelle` die Option `Lokale Dateien` wählen. Mit `Automatisch` erscheint bei
nicht erreichbarer Datenbank ein Hinweis und das Dashboard nutzt die lokalen
Dateien als Rückfallebene.
</details>

<details>
<summary><strong>Port 8501 ist bereits belegt</strong></summary>

```bash
python -m src.main dashboard --port 8502
```
</details>

<details>
<summary><strong>Datenbank komplett zurücksetzen</strong></summary>

Achtung, dies löscht das Docker-Volume und alle gespeicherten Messungen:

```bash
docker compose down -v
docker compose up -d db
python -m src.main process
```
</details>

---

<div align="center">

**Experimental Data Processing**

Entwickelt für ein kleines universitäres Forschungsteam.
Kein Enterprise-Stack – nur Python, PostgreSQL und reproduzierbare Ergebnisse.

<sub>Repository: <a href="https://github.com/dgoo24/Experimental-Data-Processing">dgoo24/Experimental-Data-Processing</a></sub>

</div>
