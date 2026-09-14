"""Small GitHub GraphQL/REST client used by the stats/streak/lang/year generators."""
from __future__ import annotations
import json
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

from common import env

API_GRAPHQL = "https://api.github.com/graphql"
API_REST = "https://api.github.com"


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "profile-readme-generator",
        "Accept": "application/vnd.github+json",
    }


def graphql(token: str, query: str, variables: dict) -> dict:
    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(API_GRAPHQL, data=body, headers=_headers(token), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"GraphQL request failed: {e.code} {e.read().decode('utf-8')}") from e
    if "errors" in data:
        raise RuntimeError(f"GraphQL errors: {data['errors']}")
    return data["data"]


def rest_get(token: str, path: str, params: dict | None = None) -> list | dict:
    url = f"{API_REST}{path}"
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{qs}"
    req = urllib.request.Request(url, headers=_headers(token), method="GET")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def combine_end_of_day(d) -> datetime:
    return datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=timezone.utc)


def combine_start_of_day(d) -> datetime:
    return datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=timezone.utc)


def rolling_year_window():
    """today - 364 days at 00:00:00Z  ->  today at 23:59:59Z (inclusive, 365 whole days)."""
    today = datetime.now(timezone.utc).date()
    start = combine_start_of_day(today - timedelta(days=364))
    end = combine_end_of_day(today)
    return start, end
