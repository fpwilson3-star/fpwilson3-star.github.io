"""Pre-render the prev/next nav and related-episodes block into every page.

Reads the EPISODES array (oldest-first) from js/episodes.js — the single
source of truth for episode order — and, for each podcast/*.html page:
  - rewrites the contents of <div id="episode-nav"> to match what
    js/episodes.js renders at runtime (keeps the prev/next chain crawlable
    without JavaScript), and
  - stamps the <div id="related-episodes"> block from the topic clusters in
    episode_blocks.py (inserting it above the nav if the page predates the
    feature).

Idempotent: safe to run any time. Run it after adding an episode — it also
updates the previously-newest page, whose nav otherwise dead-ends at
"Newest article", and refreshes related blocks whose recency tiebreak shifted.

Usage: python scripts/prerender_nav.py
"""
import re
import sys
from pathlib import Path

import episode_blocks

LINK_STYLE = 'font-family:var(--font-mono);font-size:0.85rem;color:var(--color-accent);text-decoration:none;'
MUTED_STYLE = 'font-family:var(--font-mono);font-size:0.85rem;color:var(--color-muted);'

NAV_DIV_RE = re.compile(r'(<div id="episode-nav"[^>]*>).*?(</div>)', re.DOTALL)
RELATED_DIV_RE = re.compile(r'(<div id="related-episodes"[^>]*>).*?(</div>)', re.DOTALL)
NAV_ANCHOR = '    <div id="episode-nav"'
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


def stamp_related(src, inner):
    """Replace the related-episodes block's contents, or insert the whole block
    above the nav if the page predates the feature."""
    if RELATED_DIV_RE.search(src):
        return RELATED_DIV_RE.sub(lambda m: m.group(1) + inner + m.group(2), src, count=1)
    block = episode_blocks.RELATED_DIV_OPEN + inner + '</div>'
    if NAV_ANCHOR in src:
        return src.replace(NAV_ANCHOR, '    ' + block + '\n\n' + NAV_ANCHOR, 1)
    print('WARNING: no episode-nav anchor to place related block before')
    return src


def main():
    episodes = parse_episodes()
    order = [s for s, _ in reversed(episodes)]  # newest-first, for recency tiebreak
    title_by_slug = dict(episodes)
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
        related_inner = episode_blocks.render_related_inner(
            [(s, title_by_slug[s]) for s in episode_blocks.compute_related(slug, order)],
            episode_blocks.topics_for_episode(slug))
        new_src = stamp_related(new_src, related_inner)
        if new_src != src:
            page.write_text(new_src, encoding='utf-8')
            changed += 1
            print(f'Updated: {page}')
    print(f'Done. {changed} page(s) updated, {len(episodes)} episodes in chain.')


if __name__ == '__main__':
    main()
