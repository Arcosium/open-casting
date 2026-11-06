"""One-shot trigger for a Render Cron service; no scheduler is installed locally."""
import argparse
import os

from render import Render


def trigger(client, workflow, task, value=None):
    if task == "maintenance":
        names = ("rotate_daily_missions", "close_due_missions", "purge_expired_applications")
        return [client.workflows.start_task(f"{workflow}/{name}", []) for name in names]
    return [client.workflows.start_task(f"{workflow}/{task}", [] if value is None else [value])]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("task", choices=["maintenance", "rotate_daily_missions", "close_due_missions", "purge_expired_applications", "build_sponsor_report"])
    parser.add_argument("value", nargs="?")
    args = parser.parse_args()
    if args.task == "build_sponsor_report" and not args.value:
        parser.error("build_sponsor_report requires mission_id")
    if args.task in ("close_due_missions", "purge_expired_applications") and args.value is not None:
        try:
            args.value = float(args.value)
        except ValueError:
            parser.error("timestamp must be a number")
    trigger(Render(), os.environ["RENDER_WORKFLOW_SLUG"], args.task, args.value)
    print("Workflow runs submitted.")
