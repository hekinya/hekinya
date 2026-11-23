#!/usr/bin/env python3
"""Generate Kawaii Pastel Light (Yotsugi) & Cyber Dark (Shinobu) GitHub Profile SVG cards."""

from __future__ import annotations

import base64
import datetime as dt
import html
import json
import math
import os
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = ROOT / "assets"
DIST_DIR = ROOT / "dist"

USERNAME = os.environ.get("GITHUB_USERNAME", "hekinya")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()


def b64_png(path: Path) -> str:
    data = path.read_bytes()
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def graphql_query(query: str, variables: dict, token: str) -> dict:
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=payload,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": f"{USERNAME}-profile-card",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        if "errors" in body:
            raise RuntimeError(f"GraphQL errors: {body['errors']}")
        return body["data"]


def rest_get(url: str) -> dict | list:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"{USERNAME}-profile-card",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def compute_streak(days: list[dict]) -> int:
    """Compute current (or most recent active) streak from sorted contribution days."""
    if not days:
        return 0
    # Walk backwards; allow today to be 0 if user hasn't committed yet today
    streak = 0
    idx = len(days) - 1
    if days[idx]["count"] == 0 and idx > 0:
        idx -= 1
    while idx >= 0 and days[idx]["count"] > 0:
        streak += 1
        idx -= 1
    if streak > 0:
        return streak
    # If current streak is 0, show longest streak in the past year so card stays motivating
    best = 0
    cur = 0
    for d in days:
        if d["count"] > 0:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def compute_rank(commits: int, stars: int, prs: int, streak: int) -> str:
    score = commits * 0.5 + stars * 3.0 + prs * 4.0 + streak * 2.5
    if score >= 1200:
        return "S+"
    if score >= 700:
        return "S"
    if score >= 350:
        return "A+"
    if score >= 150:
        return "A"
    if score >= 60:
        return "B+"
    return "B"


def fetch_github_stats(username: str, token: str) -> dict:
    if token:
        query = """
        query($login: String!) {
          user(login: $login) {
            contributionsCollection {
              totalCommitContributions
              restrictedContributionsCount
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
            pullRequests(first: 1) {
              totalCount
            }
            repositories(ownerAffiliations: OWNER, isFork: false, first: 100, orderBy: {field: STARGAZERS, direction: DESC}) {
              nodes {
                stargazerCount
                languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
                  edges {
                    size
                    node {
                      name
                    }
                  }
                }
              }
            }
          }
        }
        """
        data = graphql_query(query, {"login": username}, token)
        user = data["user"]
        cc = user["contributionsCollection"]
        commits = cc["totalCommitContributions"] + cc["restrictedContributionsCount"]
        prs = user["pullRequests"]["totalCount"]

        stars = 0
        lang_sizes: dict[str, int] = {}
        for repo in user["repositories"]["nodes"]:
            stars += repo["stargazerCount"]
            for edge in repo["languages"]["edges"]:
                name = edge["node"]["name"]
                lang_sizes[name] = lang_sizes.get(name, 0) + edge["size"]

        total_bytes = sum(lang_sizes.values()) or 1
        top_langs = sorted(lang_sizes.items(), key=lambda kv: kv[1], reverse=True)[:3]
        languages = [(name, size / total_bytes) for name, size in top_langs]
        if not languages:
            languages = [("TypeScript", 0.50), ("Python", 0.30), ("Go", 0.20)]

        days = []
        for w in cc["contributionCalendar"]["weeks"]:
            for d in w["contributionDays"]:
                days.append({"date": d["date"], "count": d["contributionCount"]})

        streak = compute_streak(days)
        rank = compute_rank(commits, stars, prs, streak)
        return {
            "username": username,
            "commits": commits,
            "stars": stars,
            "prs": prs,
            "streak": streak,
            "rank": rank,
            "languages": languages,
            "days": days,
        }

    # Fallback without GITHUB_TOKEN (e.g. local preview): try public REST API for stars & languages
    stars = 0
    lang_counts: dict[str, int] = {}
    try:
        repos = rest_get(f"https://api.github.com/users/{username}/repos?per_page=100&type=owner")
        if isinstance(repos, list):
            for r in repos:
                if not r.get("fork"):
                    stars += int(r.get("stargazers_count", 0))
                    lang = r.get("language")
                    if lang:
                        lang_counts[lang] = lang_counts.get(lang, 0) + 1
    except Exception:
        pass

    if lang_counts:
        total = sum(lang_counts.values())
        top = sorted(lang_counts.items(), key=lambda kv: kv[1], reverse=True)[:3]
        languages = [(n, c / total) for n, c in top]
    else:
        languages = [("TypeScript", 0.48), ("Python", 0.32), ("Go", 0.20)]

    # Build a natural-looking contribution pattern for local preview
    today = dt.date.today()
    days = []
    for i in range(180):
        d = today - dt.timedelta(days=179 - i)
        val = int(max(0, round(3 + 4 * math.sin(i * 0.17) + 2.5 * math.cos(i * 0.43))))
        if (i * 7 + d.weekday()) % 11 == 0:
            val = 0
        days.append({"date": d.isoformat(), "count": val})

    commits = sum(d["count"] for d in days)
    prs = max(12, commits // 20)
    streak = compute_streak(days)
    rank = compute_rank(commits, stars, prs, streak)
    return {
        "username": username,
        "commits": commits,
        "stars": stars,
        "prs": prs,
        "streak": streak,
        "rank": rank,
        "languages": languages,
        "days": days,
    }


def smooth_wave_path(values: list[float], x0: float, y0: float, w: float, h: float) -> tuple[str, str]:
    """Return (fill_path, stroke_path) for a smooth cubic Bezier area chart."""
    if not values:
        values = [2, 5, 3, 7, 5, 10, 6, 8]
    vmax = max(values) or 1.0
    n = len(values)
    pts = []
    for i, v in enumerate(values):
        x = x0 + (w * i / max(1, n - 1))
        # Leave 16% headroom at top and 10% floor at bottom
        norm = v / vmax
        y = y0 + h - (h * 0.10 + norm * h * 0.74)
        pts.append((x, y))

    d_parts = [f"M {pts[0][0]:.1f} {pts[0][1]:.1f}"]
    for i in range(len(pts) - 1):
        x1, y1 = pts[i]
        x2, y2 = pts[i + 1]
        cx = (x1 + x2) / 2.0
        d_parts.append(f"C {cx:.1f} {y1:.1f}, {cx:.1f} {y2:.1f}, {x2:.1f} {y2:.1f}")

    stroke_d = " ".join(d_parts)
    fill_d = f"{stroke_d} L {x0 + w:.1f} {y0 + h:.1f} L {x0:.1f} {y0 + h:.1f} Z"
    return fill_d, stroke_d


def build_light_svg(stats: dict, yotsugi_uri: str) -> str:
    user = html.escape(stats["username"])
    commits_str = f"{stats['commits']:,}"
    stars_str = f"{stats['stars']:,}"
    prs_str = f"{stats['prs']:,}"
    streak = stats["streak"]

    # Grid: 19 cols x 6 rows (114 recent days)
    cols, rows = 19, 6
    recent = stats["days"][-(cols * rows):]
    while len(recent) < cols * rows:
        recent.insert(0, {"date": "", "count": 0})
    max_c = max((d["count"] for d in recent), default=1) or 1

    # Pastel sky-blue -> lavender -> sakura-pink horizontal + intensity coloring
    def cell_color(col: int, count: int) -> str:
        t = col / max(1, cols - 1)
        # Base horizontal pastel hue: sky blue (#8FD8FF) -> lavender (#C5B6FA) -> sakura pink (#FFA6CC)
        if t < 0.5:
            k = t * 2
            r = int(143 + (197 - 143) * k)
            g = int(216 + (182 - 216) * k)
            b = int(255 + (250 - 255) * k)
        else:
            k = (t - 0.5) * 2
            r = int(197 + (255 - 197) * k)
            g = int(182 + (166 - 182) * k)
            b = int(250 + (204 - 250) * k)
        if count == 0:
            # Very soft pastel tint
            r = int(r * 0.28 + 255 * 0.72)
            g = int(g * 0.28 + 255 * 0.72)
            b = int(b * 0.28 + 255 * 0.72)
        else:
            intensity = 0.55 + 0.45 * min(1.0, count / max_c)
            r = int(r * intensity + 255 * (1 - intensity))
            g = int(g * intensity + 255 * (1 - intensity))
            b = int(b * intensity + 255 * (1 - intensity))
        return f"#{r:02x}{g:02x}{b:02x}"

    grid_rects = []
    gx0, gy0 = 56, 174
    cell_size, gap = 18.5, 4.2
    for idx, d in enumerate(recent):
        c = idx // rows
        r = idx % rows
        x = gx0 + c * (cell_size + gap)
        y = gy0 + r * (cell_size + gap)
        fill = cell_color(c, d["count"])
        grid_rects.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{cell_size:.1f}" height="{cell_size:.1f}" rx="4.5" fill="{fill}" stroke="#FFFFFF" stroke-opacity="0.6" stroke-width="0.6"/>'
        )

    # Top Languages segmented pill bar
    langs = stats["languages"][:3]
    total_ratio = sum(r for _, r in langs) or 1.0
    langs = [(n, r / total_ratio) for n, r in langs]
    lang_colors = ["#8DD4FF", "#FFA1C8", "#C8B6FF"]
    bar_x, bar_y, bar_w, bar_h = 66, 514, 408, 16
    bar_segments = []
    cur_x = bar_x
    for i, (name, ratio) in enumerate(langs):
        seg_w = bar_w * ratio
        bar_segments.append(
            f'<rect x="{cur_x:.1f}" y="{bar_y}" width="{seg_w + 1:.1f}" height="{bar_h}" fill="{lang_colors[i % 3]}"/>'
        )
        cur_x += seg_w

    legend_items = []
    legend_start_x = 122 if len(langs) == 3 else 165
    step_x = 112
    for i, (name, _) in enumerate(langs):
        lx = legend_start_x + i * step_x
        col = lang_colors[i % 3]
        safe_name = html.escape(name[:12])
        legend_items.append(
            f'<circle cx="{lx}" cy="548" r="5.5" fill="{col}"/>'
            f'<text x="{lx + 11}" y="553" font-size="14" font-weight="600" fill="#2D3248">{safe_name}</text>'
        )

    # Streak ring arc (show full pastel pink-to-blue aesthetic with subtle progress emphasis)
    ring_cx, ring_cy, ring_r = 418, 396, 56
    circ = 2 * math.pi * ring_r
    pct = min(1.0, max(0.35, streak / 100.0))
    dash = circ * pct

    return f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="540" height="620" viewBox="0 0 540 620" fill="none">
  <defs>
    <linearGradient id="outerBorder" x1="28" y1="90" x2="512" y2="590" gradientUnits="userSpaceOnUse">
      <stop offset="0%" stop-color="#87D3FF"/>
      <stop offset="50%" stop-color="#C8B6FF"/>
      <stop offset="100%" stop-color="#FF9CC8"/>
    </linearGradient>
    <linearGradient id="ringGrad" x1="362" y1="340" x2="474" y2="452" gradientUnits="userSpaceOnUse">
      <stop offset="0%" stop-color="#FFA0C9"/>
      <stop offset="50%" stop-color="#C7B6FF"/>
      <stop offset="100%" stop-color="#87D3FF"/>
    </linearGradient>
    <filter id="cardShadow" x="0" y="70" width="540" height="550" filterUnits="userSpaceOnUse">
      <feDropShadow dx="0" dy="8" stdDeviation="12" flood-color="#9BB7E8" flood-opacity="0.22"/>
    </filter>
    <filter id="softBox" x="30" y="140" width="480" height="460" filterUnits="userSpaceOnUse">
      <feDropShadow dx="0" dy="3" stdDeviation="5" flood-color="#A6C1EE" flood-opacity="0.16"/>
    </filter>
    <clipPath id="langPillClip">
      <rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="8"/>
    </clipPath>
    <style>
      text {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Nunito", "Quicksand", Roboto, Helvetica, Arial, sans-serif; }}
    </style>
  </defs>

  <!-- Main Card Base -->
  <g filter="url(#cardShadow)">
    <rect x="28" y="96" width="484" height="496" rx="28" fill="#F8FBFF" stroke="url(#outerBorder)" stroke-width="6"/>
  </g>
  <rect x="34" y="102" width="472" height="484" rx="23" fill="none" stroke="#FFFFFF" stroke-width="2"/>

  <!-- Cute Sparkles inside card -->
  <g opacity="0.85">
    <path d="M275 130 L277.5 136 L283.5 138.5 L277.5 141 L275 147 L272.5 141 L266.5 138.5 L272.5 136 Z" fill="#FFA3CB"/>
    <path d="M294 118 L295.5 122 L299.5 123.5 L295.5 125 L294 129 L292.5 125 L288.5 123.5 L292.5 122 Z" fill="#89D4FF"/>
    <circle cx="305" cy="140" r="2.2" fill="#C6B4FF"/>
    <path d="M46 420 L48 425 L53 427 L48 429 L46 434 L44 429 L39 427 L44 425 Z" fill="#89D4FF"/>
    <path d="M494 480 L496 485 L501 487 L496 489 L494 494 L492 489 L487 487 L492 485 Z" fill="#FFA3CB"/>
  </g>

  <!-- Username Header -->
  <text x="56" y="144" font-size="28" font-weight="800" fill="#2A2E45" letter-spacing="-0.3">{user}</text>

  <!-- Contribution Heatmap Box -->
  <g filter="url(#softBox)">
    <rect x="46" y="160" width="448" height="156" rx="16" fill="#FFFFFF" stroke="#D8E7FF" stroke-width="1.5"/>
  </g>
  <g>
    {"".join(grid_rects)}
  </g>

  <!-- Stats Card (Middle Left) -->
  <g filter="url(#softBox)">
    <rect x="46" y="330" width="286" height="132" rx="16" fill="#FFFFFF" stroke="#D8E7FF" stroke-width="1.5"/>
  </g>
  <text x="66" y="362" font-size="18" font-weight="800" fill="#2A2E45">{user}&apos;s Stats</text>

  <!-- Commits row -->
  <g transform="translate(66, 382)">
    <circle cx="8" cy="5" r="4.2" stroke="#5B6785" stroke-width="1.8" fill="none"/>
    <line x1="0" y1="5" x2="3.8" y2="5" stroke="#5B6785" stroke-width="1.8" stroke-linecap="round"/>
    <line x1="12.2" y1="5" x2="16" y2="5" stroke="#5B6785" stroke-width="1.8" stroke-linecap="round"/>
    <text x="26" y="10" font-size="15.5" font-weight="600" fill="#3B4258">Commits:</text>
    <text x="140" y="10" font-size="16" font-weight="800" fill="#23273A">{commits_str}</text>
  </g>

  <!-- Stars row -->
  <g transform="translate(66, 410)">
    <path d="M8 0 L10.2 4.6 L15.2 5.3 L11.6 8.8 L12.5 13.8 L8 11.4 L3.5 13.8 L4.4 8.8 L0.8 5.3 L5.8 4.6 Z" stroke="#5B6785" stroke-width="1.5" fill="#FFF3C4" stroke-linejoin="round"/>
    <text x="26" y="11" font-size="15.5" font-weight="600" fill="#3B4258">Stars:</text>
    <text x="140" y="11" font-size="16" font-weight="800" fill="#23273A">{stars_str}</text>
  </g>

  <!-- PRs row -->
  <g transform="translate(66, 437)">
    <circle cx="4" cy="3.5" r="2.6" stroke="#5B6785" stroke-width="1.6" fill="none"/>
    <circle cx="4" cy="13.5" r="2.6" stroke="#5B6785" stroke-width="1.6" fill="none"/>
    <line x1="4" y1="6.2" x2="4" y2="10.8" stroke="#5B6785" stroke-width="1.6"/>
    <circle cx="13" cy="13.5" r="2.6" stroke="#5B6785" stroke-width="1.6" fill="none"/>
    <path d="M13 10.8 V6.5 Q13 3.5 10 3.5 H8.5" stroke="#5B6785" stroke-width="1.6" fill="none" stroke-linecap="round"/>
    <text x="26" y="12" font-size="15.5" font-weight="600" fill="#3B4258">PRs:</text>
    <text x="140" y="12" font-size="16" font-weight="800" fill="#23273A">{prs_str}</text>
  </g>

  <!-- Streak Ring (Middle Right) -->
  <g>
    <circle cx="{ring_cx}" cy="{ring_cy}" r="{ring_r}" fill="#FFFFFF" stroke="#EEF3FF" stroke-width="13"/>
    <circle cx="{ring_cx}" cy="{ring_cy}" r="{ring_r}" fill="none" stroke="url(#ringGrad)" stroke-width="13"
            stroke-linecap="round" stroke-dasharray="{dash:.1f} {circ:.1f}" transform="rotate(-90 {ring_cx} {ring_cy})"/>
    <text x="{ring_cx}" y="{ring_cy - 2}" text-anchor="middle" font-size="27" font-weight="800" fill="#2A2E45">{streak}</text>
    <text x="{ring_cx}" y="{ring_cy + 20}" text-anchor="middle" font-size="15" font-weight="700" fill="#525B76">Days</text>
  </g>

  <!-- Top Languages Card (Bottom) -->
  <g filter="url(#softBox)">
    <rect x="46" y="476" width="448" height="94" rx="16" fill="#FFFFFF" stroke="#D8E7FF" stroke-width="1.5"/>
  </g>
  <text x="66" y="502" font-size="17" font-weight="800" fill="#2A2E45">Top Languages</text>
  <g clip-path="url(#langPillClip)">
    {"".join(bar_segments)}
  </g>
  <g>
    {"".join(legend_items)}
  </g>

  <!-- Cute Floating Pastel Clouds -->
  <g transform="translate(10, 444)">
    <path d="M12 24 C6 24 2 20 2 15 C2 10.5 5.5 7 10 6.5 C12 2.5 16.5 0 21.5 0 C28 0 33 4.8 33.8 11 C37.5 11.8 40 15 40 18.8 C40 22 37.5 24 34 24 Z"
          fill="#FFFFFF" stroke="#D7C8FF" stroke-width="1.8"/>
  </g>
  <g transform="translate(474, 212)">
    <path d="M12 24 C6 24 2 20 2 15 C2 10.5 5.5 7 10 6.5 C12 2.5 16.5 0 21.5 0 C28 0 33 4.8 33.8 11 C37.5 11.8 40 15 40 18.8 C40 22 37.5 24 34 24 Z"
          fill="#FFFFFF" stroke="#D7C8FF" stroke-width="1.8"/>
  </g>
  <g transform="translate(454, 548) scale(1.22)">
    <path d="M12 24 C6 24 2 20 2 15 C2 10.5 5.5 7 10 6.5 C12 2.5 16.5 0 21.5 0 C28 0 33 4.8 33.8 11 C37.5 11.8 40 15 40 18.8 C40 22 37.5 24 34 24 Z"
          fill="#FFFFFF" stroke="#D7C8FF" stroke-width="1.6"/>
  </g>

  <!-- Chibi Yotsugi Ononoki peeking over top-right corner -->
  <image href="{yotsugi_uri}" x="338" y="0" width="160" height="168" preserveAspectRatio="xMidYMid meet"/>
</svg>
'''


def build_dark_svg(stats: dict, shinobu_uri: str) -> str:
    user = html.escape(stats["username"])
    streak = stats["streak"]
    rank = html.escape(stats["rank"])

    # Grid: 19 cols x 6 rows
    cols, rows = 19, 6
    recent = stats["days"][-(cols * rows):]
    while len(recent) < cols * rows:
        recent.insert(0, {"date": "", "count": 0})
    max_c = max((d["count"] for d in recent), default=1) or 1

    # Snake occupies a cute winding path across the middle of the grid
    snake_cells = {
        (7, 2), (8, 2), (8, 3), (9, 3), (10, 3), (11, 3), (12, 3), (12, 2), (13, 2)
    }

    def dark_cell_color(col: int, count: int) -> tuple[str, float]:
        if count == 0:
            return "#242339", 0.9
        t = col / max(1, cols - 1)
        if t < 0.45:
            color = "#74E8FF"
        elif t < 0.72:
            color = "#B79CFF"
        else:
            color = "#FF86C8"
        op = 0.55 + 0.45 * min(1.0, count / max_c)
        return color, op

    gx0, gy0 = 60, 172
    cell_size, gap = 18.5, 4.0
    grid_rects = []
    for idx, d in enumerate(recent):
        c = idx // rows
        r = idx % rows
        x = gx0 + c * (cell_size + gap)
        y = gy0 + r * (cell_size + gap)
        if (c, r) in snake_cells:
            grid_rects.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{cell_size:.1f}" height="{cell_size:.1f}" rx="4" fill="#242339" opacity="0.9"/>'
            )
            continue
        fill, op = dark_cell_color(c, d["count"])
        grid_rects.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{cell_size:.1f}" height="{cell_size:.1f}" rx="4" fill="{fill}" opacity="{op:.2f}"/>'
        )

    # Compute snake visual path coordinates on the grid
    def cell_center(c: int, r: int) -> tuple[float, float]:
        return (gx0 + c * (cell_size + gap) + cell_size / 2, gy0 + r * (cell_size + gap) + cell_size / 2)

    s_pts = [cell_center(c, r) for (c, r) in [(13, 2), (12, 2), (12, 3), (11, 3), (10, 3), (9, 3), (8, 3), (8, 2), (7, 2)]]
    snake_path = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in s_pts)
    head_x, head_y = cell_center(7, 2)
    food_x, food_y = cell_center(5, 2)

    # Wave graph: group last 98 days into 14 weekly buckets
    wave_days = stats["days"][-98:]
    buckets = []
    step = max(1, len(wave_days) // 14)
    for i in range(0, len(wave_days), step):
        chunk = wave_days[i:i + step]
        if chunk:
            buckets.append(sum(d["count"] for d in chunk))
    if len(buckets) < 8:
        buckets = [4, 12, 7, 16, 11, 24, 15, 19, 13, 22]

    wx0, wy0, ww, wh = 62, 412, 416, 146
    fill_d, stroke_d = smooth_wave_path(buckets, wx0, wy0, ww, wh)

    # Subtle grid lines for wave chart
    chart_grid = []
    for i in range(1, 5):
        gy = wy0 + wh * i / 5
        chart_grid.append(f'<line x1="{wx0}" y1="{gy:.1f}" x2="{wx0 + ww}" y2="{gy:.1f}" stroke="#2A2945" stroke-width="1"/>')
    for i in range(1, 8):
        gx = wx0 + ww * i / 8
        chart_grid.append(f'<line x1="{gx:.1f}" y1="{wy0}" x2="{gx:.1f}" y2="{wy0 + wh}" stroke="#2A2945" stroke-width="1"/>')

    return f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="540" height="620" viewBox="0 0 540 620" fill="none">
  <defs>
    <linearGradient id="neonBorder" x1="28" y1="96" x2="512" y2="592" gradientUnits="userSpaceOnUse">
      <stop offset="0%" stop-color="#FF78C4"/>
      <stop offset="50%" stop-color="#B892FF"/>
      <stop offset="100%" stop-color="#6BE5FF"/>
    </linearGradient>
    <linearGradient id="waveFill" x1="62" y1="440" x2="478" y2="540" gradientUnits="userSpaceOnUse">
      <stop offset="0%" stop-color="#FF78C4" stop-opacity="0.72"/>
      <stop offset="50%" stop-color="#B992FF" stop-opacity="0.65"/>
      <stop offset="100%" stop-color="#6BE5FF" stop-opacity="0.75"/>
    </linearGradient>
    <linearGradient id="waveStroke" x1="62" y1="0" x2="478" y2="0" gradientUnits="userSpaceOnUse">
      <stop offset="0%" stop-color="#FF8ED0"/>
      <stop offset="50%" stop-color="#D2B6FF"/>
      <stop offset="100%" stop-color="#8AF0FF"/>
    </linearGradient>
    <filter id="neonGlow" x="-10%" y="-10%" width="120%" height="120%">
      <feGaussianBlur stdDeviation="4" result="blur"/>
      <feMerge>
        <feMergeNode in="blur"/>
        <feMergeNode in="SourceGraphic"/>
      </feMerge>
    </filter>
    <filter id="cardGlow" x="0" y="70" width="540" height="550" filterUnits="userSpaceOnUse">
      <feDropShadow dx="0" dy="8" stdDeviation="12" flood-color="#FF78C4" flood-opacity="0.18"/>
    </filter>
    <style>
      text {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Nunito", Roboto, Helvetica, Arial, sans-serif; }}
      .snake-float {{
        animation: snakeBob 2.6s ease-in-out infinite;
      }}
      .food-pulse {{
        animation: foodPulse 1.6s ease-in-out infinite;
        transform-origin: {food_x:.1f}px {food_y:.1f}px;
      }}
      @keyframes snakeBob {{
        0%, 100% {{ transform: translateX(0px); }}
        50% {{ transform: translateX(-4px); }}
      }}
      @keyframes foodPulse {{
        0%, 100% {{ opacity: 0.7; transform: scale(0.92); }}
        50% {{ opacity: 1; transform: scale(1.12); }}
      }}
    </style>
  </defs>

  <!-- Main Dark Neon Card Base -->
  <g filter="url(#cardGlow)">
    <rect x="28" y="96" width="484" height="496" rx="28" fill="#151426" stroke="url(#neonBorder)" stroke-width="5"/>
  </g>
  <rect x="36" y="104" width="468" height="480" rx="22" fill="none" stroke="#2D2B4B" stroke-width="1.2"/>

  <!-- Cute Neon Pixel Hearts & Sparkles -->
  <g filter="url(#neonGlow)">
    <!-- Top-left pink heart -->
    <path d="M56 125 C56 121 50 120 50 125 C50 129 56 134 56 134 C56 134 62 129 62 125 C62 120 56 121 56 125 Z" fill="#FF7AC6"/>
    <!-- Cyan heart near Shinobu -->
    <path d="M322 124 C322 120.5 317 120 317 124 C317 127.5 322 131.5 322 131.5 C322 131.5 327 127.5 327 124 C327 120 322 120.5 322 124 Z" fill="none" stroke="#6BE5FF" stroke-width="1.8"/>
    <!-- Right-side pink outline heart -->
    <path d="M494 318 C494 314.5 489 314 489 318 C489 321.5 494 325.5 494 325.5 C494 325.5 499 321.5 499 318 C499 314 494 314.5 494 318 Z" fill="none" stroke="#FF7AC6" stroke-width="1.8"/>
    <!-- Left-side pink outline heart -->
    <path d="M44 374 C44 370.5 39 370 39 374 C39 377.5 44 381.5 44 381.5 C44 381.5 49 377.5 49 374 C49 370 44 370.5 44 374 Z" fill="none" stroke="#FF7AC6" stroke-width="1.8"/>
    <!-- Bottom-right cyan heart -->
    <path d="M494 562 C494 558.5 489 558 489 562 C489 565.5 494 569.5 494 569.5 C494 569.5 499 565.5 499 562 C499 558 494 558.5 494 562 Z" fill="none" stroke="#6BE5FF" stroke-width="1.8"/>
  </g>
  <circle cx="48" cy="147" r="2.8" fill="#6BE5FF"/>
  <circle cx="338" cy="134" r="2.5" fill="#FF7AC6"/>
  <path d="M496 205 L498 209 L502 211 L498 213 L496 217 L494 213 L490 211 L494 209 Z" fill="#6BE5FF"/>

  <!-- Username Header -->
  <text x="72" y="138" font-size="26" font-weight="800" fill="#F2F6FF" letter-spacing="-0.2">{user}</text>

  <!-- Contribution Grid + Pink Snake Panel -->
  <rect x="48" y="158" width="444" height="156" rx="16" fill="#0E0E1D" stroke="#2D2B4B" stroke-width="1.5"/>
  <g>
    {"".join(grid_rects)}
  </g>

  <!-- Glowing Food Dot -->
  <g class="food-pulse" filter="url(#neonGlow)">
    <rect x="{food_x - 6:.1f}" y="{food_y - 6:.1f}" width="12" height="12" rx="3.5" fill="#74E8FF"/>
  </g>

  <!-- Animated Cute Pink Pixel Snake -->
  <g class="snake-float" filter="url(#neonGlow)">
    <path d="{snake_path}" stroke="#FF88CC" stroke-width="15" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
    <path d="{snake_path}" stroke="#FFB8E2" stroke-width="7" stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="6 10" fill="none"/>
    <!-- Snake Head -->
    <circle cx="{head_x:.1f}" cy="{head_y:.1f}" r="9.5" fill="#FF88CC"/>
    <!-- Cute Eyes -->
    <circle cx="{head_x - 3:.1f}" cy="{head_y - 2.5:.1f}" r="1.8" fill="#151426"/>
    <circle cx="{head_x - 3:.1f}" cy="{head_y + 2.5:.1f}" r="1.8" fill="#151426"/>
    <!-- Tiny Tongue -->
    <path d="M{head_x - 9.5:.1f} {head_y:.1f} L{head_x - 15:.1f} {head_y:.1f} M{head_x - 15:.1f} {head_y:.1f} L{head_x - 18:.1f} {head_y - 2.5:.1f} M{head_x - 15:.1f} {head_y:.1f} L{head_x - 18:.1f} {head_y + 2.5:.1f}"
          stroke="#FF5CA8" stroke-width="1.8" stroke-linecap="round"/>
  </g>

  <!-- Middle Stat Pills -->
  <text x="64" y="336" font-size="13" font-weight="600" fill="#7D83A8">@{user}</text>

  <!-- STREAK Pill -->
  <g filter="url(#neonGlow)">
    <rect x="60" y="346" width="202" height="44" rx="22" fill="#17162B" stroke="#FF7AC6" stroke-width="2.2"/>
  </g>
  <text x="161" y="375" text-anchor="middle" font-size="19" font-weight="800" fill="#E8F8FF" letter-spacing="0.5">
    STREAK: <tspan fill="#FF8CD0">{streak}</tspan>
  </text>

  <!-- RANK Pill -->
  <g filter="url(#neonGlow)">
    <rect x="278" y="346" width="202" height="44" rx="22" fill="#17162B" stroke="#6BE5FF" stroke-width="2.2"/>
  </g>
  <text x="379" y="375" text-anchor="middle" font-size="19" font-weight="800" fill="#E8F8FF" letter-spacing="0.5">
    RANK: <tspan fill="#7AEBFF">{rank}</tspan>
  </text>

  <!-- Bottom Wave Graph Container -->
  <rect x="48" y="404" width="444" height="162" rx="16" fill="#0E0E1D" stroke="#2D2B4B" stroke-width="1.5"/>
  <g>
    {"".join(chart_grid)}
  </g>
  <path d="{fill_d}" fill="url(#waveFill)"/>
  <path d="{stroke_d}" stroke="url(#waveStroke)" stroke-width="3.5" stroke-linecap="round" filter="url(#neonGlow)" fill="none"/>

  <!-- Chibi Shinobu Oshino peeking over top-right corner -->
  <image href="{shinobu_uri}" x="348" y="10" width="158" height="152" preserveAspectRatio="xMidYMid meet"/>
</svg>
'''


def main() -> None:
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    stats = fetch_github_stats(USERNAME, GITHUB_TOKEN)

    yotsugi_uri = b64_png(ASSETS_DIR / "yotsugi-light.png")
    shinobu_uri = b64_png(ASSETS_DIR / "shinobu-dark.png")

    light_svg = build_light_svg(stats, yotsugi_uri)
    dark_svg = build_dark_svg(stats, shinobu_uri)

    (DIST_DIR / "profile-light.svg").write_text(light_svg, encoding="utf-8")
    (DIST_DIR / "profile-dark.svg").write_text(dark_svg, encoding="utf-8")
    print(
        f"Generated SVGs for @{stats['username']}: "
        f"commits={stats['commits']}, stars={stats['stars']}, prs={stats['prs']}, "
        f"streak={stats['streak']}, rank={stats['rank']}"
    )


if __name__ == "__main__":
    main()
