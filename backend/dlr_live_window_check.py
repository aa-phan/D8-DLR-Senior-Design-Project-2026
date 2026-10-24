"""Window check for hourly live slots (skeleton for the RED commit; behaviour follows in GREEN)."""


def billed_minutes(run):
    return 0


def evaluate_window(runs, run_rows, rating_rows, start, hours=24):
    return {"slots": [], "minutes": {"count": 0, "median": None, "max": None, "projected_30d": None}, "passed": False}


def format_report(result):
    return ""


def fetch_runs(start, hours):
    return []


def fetch_rows(start, hours, conn=None):
    return [], []


def main(argv=None):
    return 1
