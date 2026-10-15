# Walkthrough

How each part works, in the order data flows, plus what to say in an interview.

## 1. Config (`collector/config.py`)

- Every setting lives in one `Settings` object: search terms, cities, page limits, database path.
- Secrets come from environment variables, read from a `.env` file locally or GitHub Secrets in Actions. **Keys are never in code.**
- **Interview line:** "Configuration and secrets are separated from logic, so the same code runs locally and in CI."

## 2. HTTP session (`collector/http.py`)

- One `requests.Session` shared by all sources, which reuses connections.
- `Retry` with `backoff_factor=2` retries on timeouts and on 429 (rate limited) / 5xx (server error), waiting longer each time. It respects the API's `Retry-After` header.
- 4xx errors like 401 (bad key) are **not** retried: repeating a bad request won't fix it.

## 3. Sources (`collector/sources/`)

Each one has the same three methods:

- **extract**: call the API, return raw JSON untouched. Keeping raw separate from cleaning makes bugs easy to find: you can see whether the API or your code was wrong.
- **transform**: turn JSON into flat rows for the tables.
- **load**: upsert into SQLite.

`base.py` defines this as an abstract class. This is the **template pattern**: the runner treats every source the same way.

**Jobs (Adzuna):**
- Loops over 4 search terms × up to 2 pages, and stops early when a page isn't full, which saves API calls.
- The same job can match two searches, so it's deduplicated by ID.
- Strips HTML tags from titles and descriptions.
- `extract_skills` uses regex with word boundaries. `\bR\b` is case-sensitive, so "React" doesn't count as R, and "excellence" doesn't count as Excel. The tests check exactly these cases.
- Sponsorship has two flags. "Unable to sponsor" sets `says_no_sponsorship` and does **not** count as a positive mention, even though it contains "sponsor". Negation handling is the subtle part worth mentioning.

**Weather (Open-Meteo):**
- Asks for 2 past days plus today. Today is a forecast; past days are observed.
- Tomorrow's run overwrites today's forecast with the real value, through the upsert on `(city, date)`. The data corrects itself with no extra code.

**Reddit (optional):**
- OAuth 2 client-credentials flow: exchange the app ID and secret for a temporary token, then call the API with `Authorization: bearer <token>`.
- Usernames are deliberately not stored (data minimization).

## 4. Database (`collector/db.py`)

- **Upsert** = `INSERT ... ON CONFLICT (key) DO UPDATE`. Running twice gives the same result as running once: the run is **idempotent**. That's the property that makes scheduled jobs safe to retry.
- `keep_on_update` protects `first_seen_at`, so you can measure how long a posting stayed open (`last_seen_at - first_seen_at`).
- SQLite is a single file with no server. For multiple users or bigger data, the same design moves to PostgreSQL with almost no changes.

## 5. Runner (`collector/runner.py`)

- Runs each source inside its own `try/except`, so one failure can't stop the others.
- Writes a `run_log` row **before** starting each source and updates it after. If the process crashes mid-run, a row stuck at `running` shows exactly where.
- `redact()` scrubs API keys from error messages. Request URLs often contain keys, and those messages end up in logs, which are public on GitHub. A test checks this.
- Exits with code 1 if any source failed, so GitHub Actions marks the run red and emails you.

## 6. Report (`collector/report.py`)

- Plain SQL over the collected tables: skill share overall and by role (`ROW_NUMBER() OVER (PARTITION BY ...)` for top 5 per role), salary by role, top states, sponsorship rates.
- The salary query uses only employer-stated salaries (`salary_is_predicted = 0`), since Adzuna estimates the rest. It also drops values under $20,000, which are usually hourly rates entered in the wrong field.

## 7. Scheduling (`.github/workflows/collect.yml`)

- Cron runs it daily on GitHub's servers. `workflow_dispatch` adds a manual button.
- The database is passed between runs as an artifact: download the previous one, add data, upload again.
- `concurrency` stops two runs overlapping and corrupting the database.
- `tests.yml` runs the test suite on every push (continuous integration).

## Questions an interviewer might ask

- *What happens if the API is down?* Retries with backoff first. If it still fails, that source is logged as failed, the others load normally, and the workflow goes red so I get notified. The next day's run continues as usual.
- *What if it runs twice?* Nothing breaks. Upserts make it idempotent.
- *How do you test code that calls external APIs?* Mock the HTTP layer with sample payloads, so tests are fast, free, and don't depend on the network.
- *How would you scale it?* Move storage to PostgreSQL or a warehouse, orchestrate with Airflow for dependencies and backfills, and land raw JSON in cloud storage before transforming.
- *What are the data quality limits?* Adzuna gives description snippets, so skill counts are a lower bound. I documented that instead of overstating the results.
