"""
Generate langs.svg: top languages across the user's PUBLIC, non-fork
repositories, weighted by bytes of code (via each repo's `languages`
GraphQL field).

Data rule: we deliberately restrict to public repositories only. The
workflow runs with the default GITHUB_TOKEN, which cannot see private
repos anyway -- explicitly filtering to `privacy: PUBLIC` (and excluding
forks) keeps the result identical whether the query is run with a
fine-grained PAT locally or the Actions token in CI, instead of silently
depending on whichever scopes happen to be available.
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import env, GENERATED, write_if_changed, FONT_FAMILY, FG, FG_DIM, embedded_font_style  # noqa: E402
from gh_api import graphql  # noqa: E402

QUERY = """
query($login: String!, $after: String) {
  user(login: $login) {
    repositories(first: 50, after: $after, privacy: PUBLIC, isFork: false, ownerAffiliations: [OWNER]) {
      pageInfo { hasNextPage endCursor }
      nodes {
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges {
            size
            node { name color }
          }
        }
      }
    }
  }
}
"""

TOP_N = 6

# Fallback palette used only if GitHub doesn't report a color for a
# language (rare). Keeps rendering deterministic either way.
FALLBACK_COLORS = ["#58a6ff", "#3fb950", "#f0883e", "#d29922", "#bc8cff", "#f85149"]


def fetch_language_bytes(login: str, token: str) -> dict:
    totals: dict[str, tuple[int, str]] = {}
    after = None
    while True:
        data = graphql(token, QUERY, {"login": login, "after": after})
        repos = data["user"]["repositories"]
        for repo in repos["nodes"]:
            for edge in repo["languages"]["edges"]:
                name = edge["node"]["name"]
                size = edge["size"]
                color = edge["node"]["color"] or "#8b949e"
                prev_size, _ = totals.get(name, (0, color))
                totals[name] = (prev_size + size, color)
        if repos["pageInfo"]["hasNextPage"]:
            after = repos["pageInfo"]["endCursor"]
        else:
            break
    return totals


def build_svg(totals: dict) -> str:
    ranked = sorted(totals.items(), key=lambda kv: kv[1][0], reverse=True)[:TOP_N]
    total_bytes = sum(size for _, (size, _) in ranked) or 1

    width, height = 420, 24 + len(ranked) * 26
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="{FONT_FAMILY}" role="img" '
        f'aria-label="Top languages by bytes across public repositories">',
        embedded_font_style(),
    ]
    bar_x = 110
    bar_max_w = width - bar_x - 60
    for i, (name, (size, color)) in enumerate(ranked):
        pct = size / total_bytes
        y = 20 + i * 26
        bar_w = max(2, pct * bar_max_w)
        parts.append(f'<text x="0" y="{y + 5}" font-size="12" fill="{FG}">{name}</text>')
        parts.append(
            f'<rect x="{bar_x}" y="{y - 8}" width="{bar_max_w}" height="10" rx="5" '
            f'fill="{FG_DIM}" fill-opacity="0.15"/>'
        )
        parts.append(
            f'<rect x="{bar_x}" y="{y - 8}" width="{bar_w:.1f}" height="10" rx="5" fill="{color}"/>'
        )
        parts.append(
            f'<text x="{bar_x + bar_max_w + 8}" y="{y + 5}" font-size="11" fill="{FG_DIM}">'
            f'{pct * 100:.1f}%</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts)


def main():
    login = env("GITHUB_LOGIN")
    token = env("GITHUB_TOKEN")
    totals = fetch_language_bytes(login, token)
    svg = build_svg(totals)
    changed = write_if_changed(GENERATED / "langs.svg", svg)
    print(f"{'wrote' if changed else 'unchanged'}: generated/langs.svg ({len(totals)} languages found)")


if __name__ == "__main__":
    main()
