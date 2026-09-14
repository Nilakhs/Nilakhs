"""
Generate streak.svg: total contributions (rolling year), current streak,
longest streak (rolling year) -- all from one GraphQL contributionsCollection
query so the numbers are internally consistent with each other.

Deterministic window: per the project's data rules, the rolling-year window
is pinned to whole UTC days: (today - 364 days) 00:00:00Z through today
23:59:59Z. This makes repeated runs on the same UTC day produce identical
output regardless of local vs. Actions execution time.
"""
from __future__ import annotations
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import env, GENERATED, write_if_changed, FONT_FAMILY, FG, FG_DIM, ACCENT, embedded_font_style  # noqa: E402
from gh_api import graphql, rolling_year_window  # noqa: E402

QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            contributionCount
          }
        }
      }
    }
  }
}
"""


def compute_streaks(days: list[dict]):
    """days: list of {date: 'YYYY-MM-DD', contributionCount: int}, chronological."""
    today = date.today()
    longest = 0
    running = 0
    current = 0
    # Walk chronologically for longest streak.
    for d in days:
        if d["contributionCount"] > 0:
            running += 1
            longest = max(longest, running)
        else:
            running = 0
    # Current streak: walk backward from the most recent day. If today has
    # 0 contributions (common if the run happens before the user's push),
    # that alone doesn't break a streak that ended yesterday -- we just
    # don't count today, and start counting from the most recent day with
    # activity, provided that day is today or yesterday.
    by_date = {d["date"]: d["contributionCount"] for d in days}
    cursor = today
    # If today has no contributions yet, step back one day before counting,
    # but only one day of grace.
    if by_date.get(cursor.isoformat(), 0) == 0:
        cursor = cursor - timedelta(days=1)
    streak = 0
    while True:
        key = cursor.isoformat()
        if key not in by_date:
            break
        if by_date[key] > 0:
            streak += 1
            cursor -= timedelta(days=1)
        else:
            break
    return streak, longest


def build_svg(total: int, current: int, longest: int) -> str:
    width, height = 420, 140
    cards = [
        ("Total (365d)", f"{total:,}"),
        ("Current streak", f"{current} {'day' if current == 1 else 'days'}"),
        ("Longest streak", f"{longest} {'day' if longest == 1 else 'days'}"),
    ]
    col_w = width / len(cards)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="{FONT_FAMILY}" role="img" aria-label="Contribution streak stats">',
        embedded_font_style(),
        f'<rect width="{width}" height="{height}" rx="10" fill="none" stroke="{FG_DIM}" stroke-opacity="0.35"/>',
    ]
    for i, (label, value) in enumerate(cards):
        cx = col_w * i + col_w / 2
        if i > 0:
            parts.append(
                f'<line x1="{col_w * i:.1f}" y1="20" x2="{col_w * i:.1f}" y2="{height - 20}" '
                f'stroke="{FG_DIM}" stroke-opacity="0.25"/>'
            )
        parts.append(
            f'<text x="{cx:.1f}" y="62" font-size="26" font-weight="600" fill="{ACCENT}" '
            f'text-anchor="middle">{value}</text>'
        )
        parts.append(
            f'<text x="{cx:.1f}" y="92" font-size="12" fill="{FG_DIM}" '
            f'text-anchor="middle">{label}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts)


def main():
    login = env("GITHUB_LOGIN")
    token = env("GITHUB_TOKEN")
    start, end = rolling_year_window()

    data = graphql(token, QUERY, {
        "login": login,
        "from": start.isoformat().replace("+00:00", "Z"),
        "to": end.isoformat().replace("+00:00", "Z"),
    })

    cal = data["user"]["contributionsCollection"]["contributionCalendar"]
    total = cal["totalContributions"]
    days = [d for week in cal["weeks"] for d in week["contributionDays"]]

    current, longest = compute_streaks(days)
    svg = build_svg(total, current, longest)
    changed = write_if_changed(GENERATED / "streak.svg", svg)
    print(f"{'wrote' if changed else 'unchanged'}: generated/streak.svg "
          f"(total={total}, current={current}, longest={longest})")


if __name__ == "__main__":
    main()
