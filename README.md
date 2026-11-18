# Shortlist — job recommendations + monthly market dashboard (Tasks 5 & 6)

```
app/            data.py (clean) · engine.py (recommender) · trends.py (dashboard metrics)
                updater.py (auto + manual refresh) · server.py (Flask API) · static/index.html (UI)
data/raw/       put your base CSV here (same columns as the notebook: title, published_date, link,
                hourly_low, hourly_high, budget, country — edit COLS in app/data.py if different)
data/incoming/  drop each new month's CSV here  ·  data/state/  update log (auto-created)
docs/API.md     API reference  ·  notebooks/  analysis notebook (Tasks 1-4)
```
## Run
```bash
pip install -r requirements.txt && python -m app.server      # http://localhost:5000  (API docs: /docs)
docker compose up --build                                    # same, containerised
```
## Dashboard updates: automatic AND manual
| Mode | How it works |
|---|---|
| **Automatic** (default) | A background thread checks every `CHECK_SECS` (1 h). It rebuilds the data, model and trends when **new/changed files appear in `data/incoming/`** or **a new calendar month starts**. If `SOURCE_URL` is set, the monthly rebuild first downloads that CSV. Turn off with `AUTO_REFRESH=0`. |
| **Manual** | "Refresh now" button (Market pulse tab) · `POST /api/update/refresh` · `python -m app.updater` (also fine for cron/CI). |
Every rebuild is logged (trigger, rows, new rows, seconds) and shown in the Update centre. The dashboard picks month/week/day buckets from your data span automatically.

## Ideas to extend
- Real user accounts + saved profiles/searches, email or Slack alerts for new matches
- Resume upload → extract skills automatically (PDF/DOCX parsing)
- Embedding model (sentence-transformers) for semantic matching; add job descriptions as features
- Click/apply logging → learn-to-rank, A/B tests, precision@k dashboard
- Forecast and country-rate pages from Tasks 3–4 inside the dashboard; anomaly alerts ("postings -30% this month")
- Postgres/pgvector + scheduled jobs (Airflow/cron/GitHub Actions) when data outgrows memory
