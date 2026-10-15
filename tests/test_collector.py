"""
Tests run fully offline: the `responses` library intercepts HTTP calls and returns
sample payloads shaped like the real APIs, so no keys or network are needed.
"""
import re
import sqlite3
from dataclasses import replace

import pytest
import responses

from collector.config import Settings
from collector.report import build_report
from collector.runner import run
from collector.sources.jobs import extract_skills

ADZUNA = re.compile(r"https://api\.adzuna\.com/v1/api/jobs/us/search/\d+")
METEO = "https://api.open-meteo.com/v1/forecast"
REDDIT_TOKEN = "https://www.reddit.com/api/v1/access_token"
REDDIT_NEW = re.compile(r"https://oauth\.reddit\.com/r/\w+/new")


def job(i, title="Data Analyst", desc="Strong SQL and Python. Power BI a plus.", predicted="0"):
    return {
        "id": str(i), "title": f"<strong>{title}</strong>", "description": desc,
        "company": {"display_name": f"Company {i}"},
        "location": {"display_name": "Des Moines, Polk County", "area": ["US", "Iowa", "Polk County", "Des Moines"]},
        "salary_min": 70000, "salary_max": 90000, "salary_is_predicted": predicted,
        "contract_time": "full_time", "category": {"label": "IT Jobs"},
        "created": "2026-10-14T10:00:00Z", "redirect_url": f"https://adzuna.example/{i}",
    }


def meteo_payload():
    return {"daily": {
        "time": ["2026-10-13", "2026-10-14", "2026-10-15"],
        "temperature_2m_max": [15.1, 17.3, 19.0], "temperature_2m_min": [3.2, 5.0, 8.1],
        "precipitation_sum": [0.0, 2.4, 0.0], "wind_speed_10m_max": [18.0, 25.2, 12.1],
        "weather_code": [1, 61, 2],
    }}


def reddit_payload(sub):
    return {"data": {"children": [{"data": {
        "id": f"{sub}1", "subreddit": sub, "title": "How do I get my first data engineering job?",
        "link_flair_text": "Career", "score": 42, "num_comments": 17,
        "created_utc": 1760500000, "permalink": f"/r/{sub}/comments/x/",
    }}]}}


@pytest.fixture
def settings(tmp_path):
    return replace(
        Settings(), db_path=tmp_path / "test.db",
        adzuna_app_id="ID123", adzuna_app_key="SECRETKEY",
        reddit_client_id=None, reddit_client_secret=None,
        job_searches=("data analyst", "data engineer"), job_pages_per_search=2, job_results_per_page=2,
    )


def mock_all(rsps):
    rsps.add(responses.GET, ADZUNA, json={"results": [job(1), job(2)]})          # page 1 full -> fetch page 2
    rsps.add(responses.GET, ADZUNA, json={"results": [job(3, "Senior Data Analyst",
             "Tableau required. Unable to sponsor visas at this time.")]})
    rsps.add(responses.GET, ADZUNA, json={"results": [job(2), job(4, "Data Engineer",
             "Airflow, dbt, Snowflake and AWS. Visa sponsorship available.", predicted="1")]})
    rsps.add(responses.GET, ADZUNA, json={"results": []})
    rsps.add(responses.GET, METEO, json=meteo_payload())


def rows(db, sql):
    with sqlite3.connect(db) as conn:
        return conn.execute(sql).fetchall()


@responses.activate
def test_full_run_loads_jobs_and_weather_and_skips_reddit(settings):
    mock_all(responses)
    assert run(settings) == {"jobs": "success", "weather": "success", "reddit": "skipped"}

    assert rows(settings.db_path, "SELECT COUNT(*) FROM job_postings")[0][0] == 4     # job 2 deduped
    assert rows(settings.db_path, "SELECT COUNT(*) FROM weather_daily")[0][0] == 9     # 3 cities x 3 days
    title, state = rows(settings.db_path, "SELECT title, state FROM job_postings WHERE job_id='1'")[0]
    assert (title, state) == ("Data Analyst", "Iowa")                                 # HTML stripped


@responses.activate
def test_running_twice_creates_no_duplicates_and_keeps_first_seen(settings):
    mock_all(responses); run(settings)
    first = rows(settings.db_path, "SELECT first_seen_at FROM job_postings WHERE job_id='1'")[0][0]
    responses.reset(); mock_all(responses); run(settings)

    assert rows(settings.db_path, "SELECT COUNT(*) FROM job_postings")[0][0] == 4
    assert rows(settings.db_path, "SELECT COUNT(*) FROM weather_daily")[0][0] == 9
    assert rows(settings.db_path, "SELECT first_seen_at FROM job_postings WHERE job_id='1'")[0][0] == first


@responses.activate
def test_skills_and_sponsorship_flags(settings):
    mock_all(responses); run(settings)
    skills = {r[0] for r in rows(settings.db_path, "SELECT skill FROM job_skills WHERE job_id='4'")}
    assert {"Airflow", "dbt", "Snowflake", "AWS"} <= skills

    flags = dict((r[0], (r[1], r[2])) for r in rows(
        settings.db_path, "SELECT job_id, mentions_sponsorship, says_no_sponsorship FROM job_postings"))
    assert flags["4"] == (1, 0)          # "sponsorship available"
    assert flags["3"] == (0, 1)          # "unable to sponsor"
    assert flags["1"] == (0, 0)


def test_skill_matching_avoids_false_positives():
    assert extract_skills("Experience with React and Redux") == []          # no "R"
    assert "R" in extract_skills("Proficient in R and SQL")
    assert "Power BI" in extract_skills("PowerBI dashboards")
    assert extract_skills("We value excellence") == []                      # no "Excel"


@responses.activate
def test_today_is_marked_forecast_and_past_days_observed(settings):
    mock_all(responses); run(settings, only=["weather"])
    flags = dict(rows(settings.db_path, "SELECT date, is_forecast FROM weather_daily WHERE city='Ames'"))
    assert flags == {"2026-10-13": 0, "2026-10-14": 0, "2026-10-15": 1}


@responses.activate
def test_one_failing_source_does_not_stop_others_and_secrets_are_redacted(settings):
    responses.add(responses.GET, ADZUNA, status=401, json={"error": "bad key"})
    responses.add(responses.GET, METEO, json=meteo_payload())
    assert run(settings) == {"jobs": "failed", "weather": "success", "reddit": "skipped"}

    message = rows(settings.db_path, "SELECT message FROM run_log WHERE source='jobs'")[0][0]
    assert "401" in message
    assert "SECRETKEY" not in message and "ID123" not in message


@responses.activate
def test_reddit_runs_when_credentials_are_set(settings):
    s = replace(settings, reddit_client_id="cid", reddit_client_secret="csecret")
    responses.add(responses.POST, REDDIT_TOKEN, json={"access_token": "tok", "expires_in": 3600})
    for sub in s.subreddits:
        responses.add(responses.GET, f"https://oauth.reddit.com/r/{sub}/new", json=reddit_payload(sub))
    assert run(s, only=["reddit"]) == {"reddit": "success"}
    assert rows(s.db_path, "SELECT COUNT(*) FROM reddit_posts")[0][0] == len(s.subreddits)
    assert responses.calls[1].request.headers["Authorization"] == "bearer tok"


@responses.activate
def test_report_builds(settings, tmp_path):
    mock_all(responses); run(settings)
    out = build_report(settings, tmp_path / "report.md")
    text = out.read_text()
    assert "Most requested skills" in text and "| SQL |" in text
