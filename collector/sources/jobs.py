"""
Data job postings from the Adzuna API (free key: https://developer.adzuna.com).

Besides storing each posting, it tags the skills each posting mentions and flags
visa sponsorship language, so you can track what the market asks for over time.
"""
import re

from collector.db import now_utc, upsert
from collector.sources.base import Source

BASE_URL = "https://api.adzuna.com/v1/api/jobs/us/search/{page}"

# Skill name -> regex. Word boundaries stop "R" matching inside "React", etc.
SKILLS = {
    "SQL": r"\bsql\b",
    "Python": r"\bpython\b",
    "R": r"\bR\b",
    "Excel": r"\bexcel\b",
    "Power BI": r"\bpower ?bi\b",
    "Tableau": r"\btableau\b",
    "Looker": r"\blooker\b",
    "Snowflake": r"\bsnowflake\b",
    "Databricks": r"\bdatabricks\b",
    "BigQuery": r"\bbig ?query\b",
    "dbt": r"\bdbt\b",
    "Airflow": r"\bairflow\b",
    "Spark": r"\b(py)?spark\b",
    "Kafka": r"\bkafka\b",
    "AWS": r"\baws\b|amazon web services",
    "Azure": r"\bazure\b",
    "GCP": r"\bgcp\b|google cloud",
    "Docker": r"\bdocker\b",
    "Machine learning": r"machine learning|\bml\b",
    "ETL": r"\betl\b|\belt\b",
    "Statistics": r"\bstatistic",
}
SKILL_PATTERNS = {name: re.compile(p, re.IGNORECASE if name != "R" else 0) for name, p in SKILLS.items()}

SPONSOR_POSITIVE = re.compile(r"\b(visa|sponsor(ship)?|h-?1b)\b", re.IGNORECASE)
SPONSOR_NEGATIVE = re.compile(
    r"(no|not|unable to|cannot|can't|will not|won't|does not|do not)\s+(\w+\s+){0,3}sponsor"
    r"|without (the need for )?(visa )?sponsorship"
    r"|must be (a )?(us|u\.s\.) citizen",
    re.IGNORECASE,
)
TAG = re.compile(r"<[^>]+>")


def extract_skills(text: str) -> list[str]:
    return sorted(name for name, pattern in SKILL_PATTERNS.items() if pattern.search(text))


class JobPostings(Source):
    name = "jobs"

    def is_configured(self):
        if self.settings.adzuna_app_id and self.settings.adzuna_app_key:
            return True, ""
        return False, "ADZUNA_APP_ID / ADZUNA_APP_KEY not set"

    def extract(self):
        s = self.settings
        responses = []
        for term in s.job_searches:
            for page in range(1, s.job_pages_per_search + 1):
                resp = self.session.get(
                    BASE_URL.format(page=page),
                    params={
                        "app_id": s.adzuna_app_id,
                        "app_key": s.adzuna_app_key,
                        "what_phrase": term,
                        "results_per_page": s.job_results_per_page,
                        "max_days_old": s.job_max_days_old,
                        "sort_by": "date",
                        "content-type": "application/json",
                    },
                    timeout=s.request_timeout,
                )
                resp.raise_for_status()
                results = resp.json().get("results", [])
                responses.append({"search_term": term, "results": results})
                if len(results) < s.job_results_per_page:
                    break               # last page: don't spend an API call on an empty one
        return responses

    def transform(self, raw):
        seen_at = now_utc()
        postings, skills = {}, []
        for batch in raw:
            for job in batch["results"]:
                job_id = str(job["id"])
                if job_id in postings:          # same job can match two searches
                    continue
                description = TAG.sub(" ", job.get("description") or "")
                title = TAG.sub(" ", job.get("title") or "").strip()
                text = f"{title} {description}"
                area = (job.get("location") or {}).get("area") or []
                says_no = bool(SPONSOR_NEGATIVE.search(text))
                postings[job_id] = {
                    "job_id": job_id,
                    "search_term": batch["search_term"],
                    "title": title,
                    "company": (job.get("company") or {}).get("display_name"),
                    "location": (job.get("location") or {}).get("display_name"),
                    "state": area[1] if len(area) > 1 else None,
                    "salary_min": job.get("salary_min"),
                    "salary_max": job.get("salary_max"),
                    "salary_is_predicted": int(str(job.get("salary_is_predicted", "0")) == "1"),
                    "contract_time": job.get("contract_time"),
                    "contract_type": job.get("contract_type"),
                    "category": (job.get("category") or {}).get("label"),
                    "description": description.strip(),
                    "mentions_sponsorship": int(bool(SPONSOR_POSITIVE.search(text)) and not says_no),
                    "says_no_sponsorship": int(says_no),
                    "url": job.get("redirect_url"),
                    "posted_at": job.get("created"),
                    "first_seen_at": seen_at,
                    "last_seen_at": seen_at,
                }
                skills += [{"job_id": job_id, "skill": sk} for sk in extract_skills(text)]
        return {"job_postings": list(postings.values()), "job_skills": skills}

    def load(self, conn, tables):
        n = upsert(conn, "job_postings", tables["job_postings"], key=("job_id",),
                   keep_on_update=("first_seen_at", "search_term"))
        upsert(conn, "job_skills", tables["job_skills"], key=("job_id", "skill"))
        return n
