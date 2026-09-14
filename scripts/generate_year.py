"""
Generate year.svg: a GitHub-style day-grid heatmap of the rolling-year
contribution calendar, in the same visual language as stats.svg/streak.svg
(same accent color ramp, same font) rather than a copy of the default
GitHub calendar's look.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import env, GENERATED, write_if_changed, FONT_FAMILY, FG_DIM, embedded_font_style  # noqa: E402
from gh_api import graphql, rolling_year_window  # noqa: E402

QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        weeks {
          contributionDays { date contributionCount }
        }
      }
    }
  }
}
"""

ACCENT_RGB = (88, 166, 255)  # matches ACCENT (#58a6ff) used elsewhere


def level_color(count: int, max_count: int) -> str:
    if count == 0 or max_count == 0:
        return "rgba(139,148,158,0.15)"
    t = min(1.0, count / max_count)
    # 4 discrete bands, GitHub-style, but tinted with our own accent color.
    band = min(3, int(t * 4))
    opacity = [0.30, 0.5, 0.7, 1.0][band]
    r, g, b = ACCENT_RGB
    return f"rgba({r},{g},{b},{opacity})"


def build_svg(weeks: list[list[dict]]) -> str:
    cell = 10
    gap = 2
    pad_l, pad_t = 4, 4
    n_weeks = len(weeks)
    width = pad_l * 2 + n_weeks * (cell + gap)
    height = pad_t * 2 + 7 * (cell + gap) + 14

    all_counts = [d["contributionCount"] for w in weeks for d in w]
    max_count = max(all_counts) if all_counts else 0

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="{FONT_FAMILY}" role="img" '
        f'aria-label="Yearly contribution calendar">',
        embedded_font_style(),
    ]
    for wi, week in enumerate(weeks):
        for day in week:
            # contributionDays omits leading days before the user's first
            # day of that week in some edge weeks; guard defensively.
            dow = None
            parts_date = day["date"]
            import datetime as _dt
            dow = _dt.date.fromisoformat(parts_date).weekday()  # Mon=0..Sun=6
            # GitHub calendars are Sun-first; convert so Sun=0..Sat=6
            dow = (dow + 1) % 7
            x = pad_l + wi * (cell + gap)
            y = pad_t + dow * (cell + gap)
            color = level_color(day["contributionCount"], max_count)
            parts.append(
                f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" fill="{color}">'
                f'<title>{day["date"]}: {day["contributionCount"]} contributions</title>'
                f'</rect>'
            )
    parts.append(
        f'<text x="{pad_l}" y="{height - 2}" font-size="10" fill="{FG_DIM}">'
        f'less</text>'
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

    weeks_raw = data["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    weeks = [w["contributionDays"] for w in weeks_raw]

    svg = build_svg(weeks)
    changed = write_if_changed(GENERATED / "year.svg", svg)
    print(f"{'wrote' if changed else 'unchanged'}: generated/year.svg ({len(weeks)} weeks)")


if __name__ == "__main__":
    main()
