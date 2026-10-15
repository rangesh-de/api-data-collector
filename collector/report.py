"""
Turns the collected data into a short Markdown report (reports/latest.md).

The questions are about the job market for data roles: which skills are asked for,
what pays, where the jobs are, and how often postings mention visa sponsorship.
"""
from pathlib import Path

from collector.config import ROOT, Settings
from collector.db import connect

QUERIES = {
    "Collection health (last 14 runs)": """
        SELECT source, status, rows_loaded, substr(started_at, 1, 16) AS started, message
        FROM run_log ORDER BY run_id DESC LIMIT 14
    """,
    "Postings collected per role": """
        SELECT search_term AS role, COUNT(*) AS postings,
               MIN(substr(first_seen_at, 1, 10)) AS since
        FROM job_postings GROUP BY search_term ORDER BY postings DESC
    """,
    "Most requested skills (share of postings)": """
        SELECT s.skill, COUNT(*) AS postings,
               ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM job_postings), 1) AS pct_of_postings
        FROM job_skills s GROUP BY s.skill ORDER BY postings DESC LIMIT 15
    """,
    "Top skills by role (% of that role's postings)": """
        WITH role_totals AS (SELECT search_term, COUNT(*) AS total FROM job_postings GROUP BY search_term),
        ranked AS (
            SELECT p.search_term, s.skill, COUNT(*) AS n,
                   ROW_NUMBER() OVER (PARTITION BY p.search_term ORDER BY COUNT(*) DESC) AS rnk
            FROM job_postings p JOIN job_skills s USING (job_id)
            GROUP BY p.search_term, s.skill
        )
        SELECT r.search_term AS role, r.skill, ROUND(100.0 * r.n / t.total, 1) AS pct
        FROM ranked r JOIN role_totals t USING (search_term)
        WHERE r.rnk <= 5 ORDER BY role, r.rnk
    """,
    "Advertised salary by role (employer-stated only, not Adzuna estimates)": """
        SELECT search_term AS role, COUNT(*) AS postings_with_salary,
               ROUND(AVG((salary_min + salary_max) / 2)) AS avg_midpoint_usd,
               ROUND(MIN(salary_min)) AS lowest_min, ROUND(MAX(salary_max)) AS highest_max
        FROM job_postings
        WHERE salary_is_predicted = 0 AND salary_min IS NOT NULL AND salary_max IS NOT NULL
          AND salary_min >= 20000                       -- drops hourly rates entered as yearly
        GROUP BY search_term ORDER BY avg_midpoint_usd DESC
    """,
    "Top hiring states": """
        SELECT state, COUNT(*) AS postings,
               ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct
        FROM job_postings WHERE state IS NOT NULL
        GROUP BY state ORDER BY postings DESC LIMIT 10
    """,
    "Visa sponsorship language in postings": """
        SELECT search_term AS role, COUNT(*) AS postings,
               SUM(mentions_sponsorship) AS mentions_sponsorship,
               SUM(says_no_sponsorship) AS says_no_sponsorship,
               ROUND(100.0 * SUM(says_no_sponsorship) / COUNT(*), 1) AS pct_says_no
        FROM job_postings GROUP BY search_term ORDER BY postings DESC
    """,
    "Weather: last 7 observed days": """
        SELECT city, date, temp_max_c, temp_min_c, precipitation_mm
        FROM weather_daily WHERE is_forecast = 0
        ORDER BY date DESC, city LIMIT 21
    """,
    "Reddit: most discussed new posts (last 7 days)": """
        SELECT subreddit, title, score, num_comments
        FROM reddit_posts WHERE created_at >= datetime('now', '-7 days')
        ORDER BY num_comments DESC LIMIT 10
    """,
}


def to_markdown(rows, columns) -> str:
    if not rows:
        return "_No data yet._"
    clean = lambda v: "" if v is None else str(v).replace("|", "/").replace("\n", " ")
    lines = ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    lines += ["| " + " | ".join(clean(v) for v in row) + " |" for row in rows]
    return "\n".join(lines)


def build_report(settings: Settings, out: Path = ROOT / "reports" / "latest.md") -> Path:
    parts = ["# Data job market report\n",
             "Job data from [Adzuna](https://www.adzuna.com). Weather from [Open-Meteo](https://open-meteo.com).\n",
             "Skill and sponsorship tags come from keyword matching on posting snippets, so treat them as "
             "directional, not exact.\n"]
    with connect(settings.db_path) as conn:
        for title, sql in QUERIES.items():
            cur = conn.execute(sql)
            columns = [d[0] for d in cur.description]
            parts += [f"## {title}\n", to_markdown(cur.fetchall(), columns), ""]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(parts), encoding="utf-8")
    return out
