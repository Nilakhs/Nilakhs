"""
Generate stats.svg: a weekly-activity bar chart built from the same
deterministic rolling-year contribution window used by generate_streak.py
and generate_year.py.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import env, GENERATED, write_if_changed, FONT_FAMILY, FG_DIM, ACCENT, embedded_font_style  # noqa: E402
from gh_api import graphql, rolling_year_window  # noqa: E402

QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        weeks {
          contributionDays { contributionCount }
        }
      }
    }
  }
}
"""


def build_svg(weekly_totals: list[int]) -> str:
    width, height = 720, 160
    pad_l, pad_r, pad_t, pad_b = 10, 10, 16, 24
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    n = len(weekly_totals)
    bar_gap = 2
    bar_w = max(1.0, (plot_w / n) - bar_gap)
    max_val = max(weekly_totals) or 1

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="{FONT_FAMILY}" role="img" '
        f'aria-label="Weekly contribution activity, past year">',
        embedded_font_style(),
    ]
    for i, val in enumerate(weekly_totals):
        bar_h = (val / max_val) * plot_h
        x = pad_l + i * (bar_w + bar_gap)
        y = pad_t + (plot_h - bar_h)
        opacity = 0.35 + 0.65 * (val / max_val)
        parts.append(
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_w:.2f}" height="{max(bar_h, 1):.2f}" '
            f'fill="{ACCENT}" fill-opacity="{opacity:.2f}" rx="1"/>'
        )
    parts.append(
        f'<text x="{pad_l}" y="{height - 6}" font-size="11" fill="{FG_DIM}">52 weeks ago</text>'
    )
    parts.append(
        f'<text x="{width - pad_r}" y="{height - 6}" font-size="11" fill="{FG_DIM}" '
        f'text-anchor="end">today</text>'
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

    weeks = data["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    weekly_totals = [sum(d["contributionCount"] for d in w["contributionDays"]) for w in weeks]

    svg = build_svg(weekly_totals)
    changed = write_if_changed(GENERATED / "stats.svg", svg)
    print(f"{'wrote' if changed else 'unchanged'}: generated/stats.svg ({len(weekly_totals)} weeks)")


if __name__ == "__main__":
    main()
