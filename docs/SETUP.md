# Setup

## 1. Get the keys

**Adzuna (required for job data, free):**
1. Sign up at https://developer.adzuna.com/signup
2. Your dashboard shows an **Application ID** and **Application Key**.

**Reddit (optional):**
1. While logged in, go to https://www.reddit.com/prefs/apps and create an app of type **script**.
2. Reddit may require you to request API access first and can take a few weeks to approve. The collector works without it; the Reddit source just shows as `skipped`.

## 2. Run it on your computer

Requires Python 3.10+.

```bash
pip install -r requirements.txt
cp .env.example .env        # Windows: copy .env.example .env
```

Open `.env` and paste your keys. Then:

```bash
python -m collector run
python -m collector status
python -m collector report
```

The database is `data/collector.db`. Open it with any SQLite viewer (DB Browser for SQLite, or the SQLite extension in VS Code) to explore with your own SQL.

## 3. Run it automatically every day

Pick one.

### Option A: GitHub Actions (recommended; runs even when your laptop is off)

1. On GitHub, open the repo → **Settings → Secrets and variables → Actions → New repository secret**.
2. Add `ADZUNA_APP_ID` and `ADZUNA_APP_KEY` (and the Reddit ones if you have them).
3. Go to the **Actions** tab, enable workflows if asked, open **Daily collection** and click **Run workflow** once to test.
4. After that it runs every day by itself. Each run's report appears on the run's summary page, and the database is saved as an artifact called `collector-db` that you can download.

How the database survives between runs: each run downloads the previous run's `collector-db` artifact, adds the new data, and uploads it again. Artifacts are kept for 90 days, so as long as it runs daily the history keeps growing.

Note: GitHub pauses scheduled workflows in repos with no activity for 60 days. A commit, or clicking **Run workflow**, turns it back on.

### Option B: cron (Mac/Linux)

```bash
crontab -e
```

Add this line (runs at 8:15 every morning; change the path):

```
15 8 * * * cd /path/to/api-data-collector && /usr/bin/python3 -m collector run >> data/cron.log 2>&1
```

### Option C: Windows Task Scheduler

1. Open **Task Scheduler** → **Create Basic Task** → name it "API collector" → **Daily**, 8:15 AM.
2. Action: **Start a program**.
   - Program: the full path to `python.exe` (run `where python` in a terminal to find it)
   - Arguments: `-m collector run`
   - Start in: the full path to this repo folder
3. Finish, then right-click the task → **Run** to test.

With B or C, the computer must be on at that time.
