"""Pre-render the prev/next episode nav into every podcast/*.html page.

Reads the EPISODES array (oldest-first) from js/episodes.js — the single
source of truth for episode order — and rewrites the contents of each page's
<div id="episode-nav" ...> to exactly match what js/episodes.js renders at
runtime. This keeps the internal-link chain crawlable without JavaScript.

Idempotent: safe to run any time. Run it after adding an episode — it also
updates the previously-newest page, whose nav otherwise dead-ends at
"Newest article".

Usage: python scripts/prerender_nav.py
"""
import re
import sys
from pathlib import Path

LINK_STYLE = 'font-family:var(--font-mono);font-size:0.85rem;color:var(--color-accent);text-decoration:none;'
MUTED_STYLE = 'font-family:var(--font-mono);font-size:0.85rem;color:var(--color-muted);'

NAV_DIV_RE = re.compile(r'(<div id="episode-nav"[^>]*>).*?(</div>)', re.DOTALL)
EPISODE_RE = re.compile(r"\{\s*slug:\s*'([^']+)'\s*,\s*title:\s*'([^']*)'\s*\}")


def parse_episodes():
    src = Path('js/episodes.js').read_text(encoding='utf-8')
    episodes = EPISODE_RE.findall(src)
    if not episodes:
        sys.exit('ERROR: could not parse EPISODES array from js/episodes.js')
    return episodes


def render_nav(prev, nxt):
    prev_html = (
        f'<a href="/podcast/{prev[0]}.html" style="{LINK_STYLE}">← {prev[1]}</a>'
        if prev else f'<span style="{MUTED_STYLE}">Oldest article</span>'
    )
    next_html = (
        f'<a href="/podcast/{nxt[0]}.html" style="{LINK_STYLE}">{nxt[1]} →</a>'
        if nxt else f'<span style="{MUTED_STYLE}">Newest article</span>'
    )
    return prev_html + f'<a href="/podcast/" style="{MUTED_STYLE}">All articles</a>' + next_html


def main():
    episodes = parse_episodes()
    changed = 0
    for i, (slug, _title) in enumerate(episodes):
        page = Path(f'podcast/{slug}.html')
        if not page.exists():
            print(f'WARNING: js/episodes.js lists {slug} but {page} does not exist')
            continue
        prev = episodes[i - 1] if i > 0 else None
        nxt = episodes[i + 1] if i + 1 < len(episodes) else None
        nav = render_nav(prev, nxt)
        src = page.read_text(encoding='utf-8')
        new_src, n = NAV_DIV_RE.subn(lambda m: m.group(1) + nav + m.group(2), src)
        if n == 0:
            print(f'WARNING: no <div id="episode-nav"> found in {page}')
            continue
        if new_src != src:
            page.write_text(new_src, encoding='utf-8')
            changed += 1
            print(f'Updated nav: {page}')
    print(f'Done. {changed} page(s) updated, {len(episodes)} episodes in chain.')


if __name__ == '__main__':
    main()
