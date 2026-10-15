"""
Command line entry point.

    python -m collector run                  # collect from every configured source
    python -m collector run --source jobs    # just one source
    python -m collector report               # write reports/latest.md
    python -m collector status               # show the last runs
"""
import argparse
import logging
import sys

from collector.config import settings
from collector.db import connect
from collector.report import build_report
from collector.runner import run


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="collector")
    sub = parser.add_subparsers(dest="command", required=True)
    p_run = sub.add_parser("run", help="Collect data from the APIs")
    p_run.add_argument("--source", action="append", help="jobs, weather or reddit (repeatable)")
    sub.add_parser("report", help="Write reports/latest.md")
    sub.add_parser("status", help="Show recent runs")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

    if args.command == "run":
        results = run(settings, only=args.source)
        # Exit code 1 if anything failed, so cron / GitHub Actions can alert you
        return 1 if "failed" in results.values() else 0
    if args.command == "report":
        print(f"Report written to {build_report(settings)}")
        return 0
    if args.command == "status":
        with connect(settings.db_path) as conn:
            for r in conn.execute("SELECT * FROM run_log ORDER BY run_id DESC LIMIT 15"):
                print(f"{r['started_at'][:16]}  {r['source']:<8} {r['status']:<8} "
                      f"{r['rows_loaded'] or 0:>5} rows  {r['message'] or ''}")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
