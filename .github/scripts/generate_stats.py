#!/usr/bin/env python3
"""Generate self-hosted GitHub stats + top-languages SVGs for the profile README.

Runs in GitHub Actions with GITHUB_TOKEN. No third-party card service is
involved, so the cards render even when external stats services are down.

Strict mode (default): ANY API failure exits non-zero WITHOUT writing, so a
partial or wrong card is never committed.
--test: skip the search endpoints (those rows render as an em dash) and write
to --out for local inspection. Never use --test output in a real commit.
"""

import argparse
import datetime
import json
import os
import sys
import urllib.error
import urllib.request
from xml.sax.saxutils import escape

OWNER = "mabdulrafay7zip"
API = "https://api.github.com"
HIDE_LANGS = {"HTML", "CSS"}

LANG_COLORS = {
    "Python": "#3572A5",
    "C++": "#f34b7c",
    "Jupyter Notebook": "#DA5B0B",
    "JavaScript": "#f1e05a",
    "TypeScript": "#3178c6",
    "HTML": "#e34c26",
    "CSS": "#563d7c",
    "C": "#555555",
    "Java": "#b07219",
    "Go": "#00ADD8",
    "Rust": "#dea584",
    "Shell": "#89e051",
}
DEFAULT_LANG_COLOR = "#d4af37"

FONT = "Segoe UI, Helvetica, Arial, sans-serif"
BG = "#050a18"
BORDER = "#23325e"
GOLD = "#d4af37"
GOLD_LIGHT = "#e9cf7a"
TEXT = "#e6e6e6"
MUTED = "#8b949e"


def get_json(url, token):
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "profile-stats-generator")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError("GitHub API %s -> HTTP %s" % (url, exc.code)) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("GitHub API %s -> %s" % (url, exc.reason)) from exc


def fetch_data(token, skip_search):
    user = get_json(API + "/users/" + OWNER, token)
    repos = get_json(
        API + "/users/%s/repos?per_page=100&type=owner" % OWNER, token
    )
    stars = sum(r.get("stargazers_count", 0) for r in repos)
    forks = sum(r.get("forks_count", 0) for r in repos)
    lang_bytes = {}
    for repo in repos:
        langs = get_json(repo["languages_url"], token)
        for name, size in langs.items():
            if name in HIDE_LANGS:
                continue
            lang_bytes[name] = lang_bytes.get(name, 0) + size
    total_bytes = sum(lang_bytes.values())
    top_langs = sorted(lang_bytes.items(), key=lambda kv: -kv[1])[:5]
    langs = [
        (name, size / total_bytes * 100.0 if total_bytes else 0.0)
        for name, size in top_langs
    ]

    if skip_search:
        commits = prs = issues = None
    else:
        commits = get_json(
            API + "/search/commits?q=author:%s&per_page=1" % OWNER, token
        )["total_count"]
        prs = get_json(
            API + "/search/issues?q=author:%s+type:pr&per_page=1" % OWNER, token
        )["total_count"]
        issues = get_json(
            API + "/search/issues?q=author:%s+type:issue&per_page=1" % OWNER,
            token,
        )["total_count"]

    return {
        "stars": stars,
        "forks": forks,
        "commits": commits,
        "prs": prs,
        "issues": issues,
        "followers": user.get("followers", 0),
        "repos": user.get("public_repos", len(repos)),
        "langs": langs,
    }


# --- SVG builders -----------------------------------------------------------

def star_icon(x, y):
    return (
        '<g transform="translate(%d,%d)" fill="%s">'
        '<path d="M6 0 L7.6 4.2 L12 4.6 L8.7 7.6 L9.7 12 L6 9.6 L2.3 12 '
        'L3.3 7.6 L0 4.6 L4.4 4.2 Z"/></g>' % (x, y, GOLD)
    )


def commits_icon(x, y):
    return (
        '<g transform="translate(%d,%d)" fill="none" stroke="%s" '
        'stroke-width="1.4"><path d="M2.5 2.5 L6 9.5 L9.5 2.5"/>'
        '<circle cx="2.5" cy="2.5" r="1.9" fill="%s" stroke="none"/>'
        '<circle cx="9.5" cy="2.5" r="1.9" fill="%s" stroke="none"/>'
        '<circle cx="6" cy="9.5" r="1.9" fill="%s" stroke="none"/>'
        "</g>" % (x, y, GOLD, GOLD, GOLD, GOLD)
    )


def pr_icon(x, y):
    return (
        '<g transform="translate(%d,%d)" fill="none" stroke="%s" '
        'stroke-width="1.4"><path d="M3.5 2.5 L3.5 9.5 M9.5 2.5 C9.5 7 6 7.5 '
        '4.2 8.6"/><circle cx="3.5" cy="2.5" r="1.9" fill="%s" stroke="none"/>'
        '<circle cx="3.5" cy="9.5" r="1.9" fill="%s" stroke="none"/>'
        '<circle cx="9.5" cy="2.5" r="1.9" fill="%s" stroke="none"/>'
        "</g>" % (x, y, GOLD, GOLD, GOLD, GOLD)
    )


def issue_icon(x, y):
    return (
        '<g transform="translate(%d,%d)"><circle cx="6" cy="6" r="5" fill="none" '
        'stroke="%s" stroke-width="1.4"/><circle cx="6" cy="6" r="1.7" '
        'fill="%s"/></g>' % (x, y, GOLD, GOLD)
    )


def followers_icon(x, y):
    return (
        '<g transform="translate(%d,%d)" fill="%s"><circle cx="6" cy="3.8" r="2.4"/>'
        '<path d="M1 11 C1 7.6 11 7.6 11 11 Z"/></g>' % (x, y, GOLD)
    )


def repos_icon(x, y):
    return (
        '<g transform="translate(%d,%d)" fill="none" stroke="%s" stroke-width="1.4">'
        '<rect x="1" y="1.5" width="10" height="9" rx="1.5"/>'
        '<path d="M1 5.5 L11 5.5"/></g>' % (x, y, GOLD)
    )


def fmt(value):
    return "—" if value is None else str(value)


def stats_svg(data, updated):
    cells = [
        (star_icon, "Total Stars", fmt(data["stars"])),
        (commits_icon, "Total Commits", fmt(data["commits"])),
        (pr_icon, "Total PRs", fmt(data["prs"])),
        (issue_icon, "Total Issues", fmt(data["issues"])),
        (followers_icon, "Followers", fmt(data["followers"])),
        (repos_icon, "Repositories", fmt(data["repos"])),
    ]
    rows = []
    for i, (icon, label, value) in enumerate(cells):
        col = i % 2
        row = i // 2
        x = 28 + col * 235
        y = 62 + row * 38
        rows.append(icon(x, y))
        rows.append(
            '<text x="%d" y="%d" font-family="%s" font-size="13" fill="%s">%s</text>'
            % (x + 20, y + 11, FONT, TEXT, escape(label))
        )
        rows.append(
            '<text x="%d" y="%d" font-family="%s" font-size="15" font-weight="700" '
            'fill="%s" text-anchor="end">%s</text>'
            % (x + 205, y + 12, FONT, GOLD_LIGHT, escape(value))
        )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="495" height="195" '
        'viewBox="0 0 495 195" role="img" aria-label="GitHub stats">'
        '<rect x="0.5" y="0.5" width="494" height="194" rx="6" fill="%s" '
        'stroke="%s"/>'
        '<text x="25" y="34" font-family="%s" font-size="17" font-weight="600" '
        'fill="%s">%s\'s GitHub Stats</text>'
        "%s"
        '<text x="470" y="184" font-family="%s" font-size="10" fill="%s" '
        'text-anchor="end">Updated %s UTC</text></svg>'
        % (
            BG,
            BORDER,
            FONT,
            GOLD,
            escape(OWNER),
            "".join(rows),
            FONT,
            MUTED,
            escape(updated),
        )
    )


def langs_svg(data, updated):
    rows = []
    for i, (name, pct) in enumerate(data["langs"]):
        y = 58 + i * 26
        color = LANG_COLORS.get(name, DEFAULT_LANG_COLOR)
        bar_w = 270.0 * pct / 100.0
        rows.append(
            '<text x="25" y="%d" font-family="%s" font-size="13" fill="%s">%s</text>'
            % (y + 4, FONT, TEXT, escape(name))
        )
        rows.append(
            '<rect x="145" y="%d" width="270" height="10" rx="5" fill="%s"/>'
            % (y - 5, BORDER)
        )
        rows.append(
            '<rect x="145" y="%d" width="%.1f" height="10" rx="5" fill="%s"/>'
            % (y - 5, max(bar_w, 6.0), color)
        )
        rows.append(
            '<text x="425" y="%d" font-family="%s" font-size="13" font-weight="600" '
            'fill="%s">%.1f%%</text>' % (y + 4, FONT, GOLD_LIGHT, pct)
        )
    note = "By code size across public repositories"
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="495" height="195" '
        'viewBox="0 0 495 195" role="img" aria-label="Top languages">'
        '<rect x="0.5" y="0.5" width="494" height="194" rx="6" fill="%s" '
        'stroke="%s"/>'
        '<text x="25" y="34" font-family="%s" font-size="17" font-weight="600" '
        'fill="%s">Top Languages</text>'
        "%s"
        '<text x="25" y="184" font-family="%s" font-size="10" fill="%s">%s</text>'
        '<text x="470" y="184" font-family="%s" font-size="10" fill="%s" '
        'text-anchor="end">Updated %s UTC</text></svg>'
        % (
            BG,
            BORDER,
            FONT,
            GOLD,
            "".join(rows),
            FONT,
            MUTED,
            note,
            FONT,
            MUTED,
            escape(updated),
        )
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="profile")
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN", "")
    try:
        data = fetch_data(token, skip_search=args.test)
    except RuntimeError as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 1

    updated = datetime.datetime.now(datetime.timezone.utc).strftime("%d %b %Y")
    os.makedirs(args.out, exist_ok=True)
    for name, svg in (
        ("stats.svg", stats_svg(data, updated)),
        ("top-langs.svg", langs_svg(data, updated)),
    ):
        path = os.path.join(args.out, name)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(svg)
        os.replace(tmp, path)
        print("wrote %s (%d bytes)" % (path, len(svg)))
    print(
        "stars=%s commits=%s prs=%s issues=%s followers=%s repos=%s langs=%s"
        % (
            data["stars"],
            data["commits"],
            data["prs"],
            data["issues"],
            data["followers"],
            data["repos"],
            [(n, round(p, 1)) for n, p in data["langs"]],
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
