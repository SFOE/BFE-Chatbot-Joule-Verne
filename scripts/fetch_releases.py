"""Fetch GitHub releases from the app repo and save as JSON.

Run during Docker build. Uses the default GITHUB_TOKEN available in GitHub Actions.
"""

import json
import os
import urllib.request
import urllib.error

APP_REPO = "SFOE/BFE-Chatbot-Joule-Verne"
GITHUB_API_BASE = "https://api.github.com/repos"
OUTPUT_FILE = "release_notes.json"

# Only include releases from this version onwards (inclusive)
MIN_VERSION = "v0.3.0"


def fetch_releases(repo: str) -> list:
    """Fetch releases from a GitHub repo."""
    url = f"{GITHUB_API_BASE}/{repo}/releases"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "jouleverne-build"}

    token = os.environ.get("GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"Warning: Could not fetch releases from {repo}: {e.code}")
        return []
    except Exception as e:
        print(f"Warning: Could not fetch releases from {repo}: {e}")
        return []


def main():
    releases = fetch_releases(APP_REPO)

    # Sort by publication date (newest first)
    releases.sort(key=lambda r: r.get("published_at", ""), reverse=True)

    # Find the cutoff: only include releases >= MIN_VERSION by date
    min_date = None
    for r in releases:
        if r.get("tag_name") == MIN_VERSION:
            min_date = r.get("published_at", "")
            break

    # Keep only the fields we need
    slim_releases = []
    for r in releases:
        # Skip releases older than MIN_VERSION
        if min_date and r.get("published_at", "") < min_date:
            continue

        body = r.get("body", "")

        # Remove auto-generated "What's Changed" and "New Contributors" sections
        for section in ["## What's Changed", "## New Contributors"]:
            idx = body.find(section)
            if idx != -1:
                body = body[:idx].strip()

        slim_releases.append({
            "name": r.get("name") or r.get("tag_name", ""),
            "tag": r.get("tag_name", ""),
            "date": r.get("published_at", "")[:10],
            "body": body,
            "prerelease": r.get("prerelease", False),
        })

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(slim_releases, f, ensure_ascii=False, indent=2)

    print(f"Saved {len(slim_releases)} releases to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
