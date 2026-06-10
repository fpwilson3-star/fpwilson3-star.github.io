"""Validate cross-file consistency of the episode pages.

Catches the drift that happens when the publishing checklist is only
partially run. Checks every podcast/*.html episode page against
podcast/index.html, js/episodes.js, sitemap.xml, and podcast/rss.xml:

  1. Every episode page is listed in the index, episodes.js, sitemap, and RSS
     (and nothing is listed that doesn't exist on disk).
  2. The index listing is sorted newest-first and its dates match each page's
     article:published_time, the page's JSON-LD dates, and the RSS pubDate.
  3. No published date is in the future; sitemap lastmod is never before the
     publish date.
  4. Every episode page has a visible FAQ section and FAQPage JSON-LD, and
     the visible questions exactly match the schema (required for Google
     FAQ rich results).
  5. Every page's pre-rendered episode-nav matches the chain in episodes.js
     (run scripts/prerender_nav.py to fix).

Exits non-zero with a readable report if anything is wrong.

Usage: python scripts/check_site.py
"""
import html
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import prerender_nav  # noqa: E402

SITE = 'https://fperrywilson.com'
errors = []


def err(msg):
    errors.append(msg)


def parse_index():
    src = Path('podcast/index.html').read_text(encoding='utf-8')
    item_re = re.compile(
        r'<div class="media-item"[^>]*data-date="([^"]+)"[^>]*>.*?'
        r'<div class="media-outlet"><a href="/podcast/([^"]+)\.html">',
        re.DOTALL
    )
    return item_re.findall(src)  # [(date, slug), ...] in page order


def jsonld_blocks(src):
    for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', src, re.DOTALL):
        try:
            yield json.loads(m.group(1))
        except json.JSONDecodeError:
            err('invalid JSON-LD block (could not parse)')


def main():
    pages = {p.stem for p in Path('podcast').glob('*.html')} - {'index'}
    episodes = prerender_nav.parse_episodes()  # oldest-first [(slug, title)]
    js_slugs = [s for s, _ in episodes]
    index_entries = parse_index()
    index_slugs = [s for _, s in index_entries]
    index_dates = {s: d for d, s in index_entries}
    sitemap = Path('sitemap.xml').read_text(encoding='utf-8')
    sitemap_pairs = re.findall(
        r'<loc>' + re.escape(SITE) + r'/podcast/([^<]+)\.html</loc>\s*<lastmod>([^<]+)</lastmod>', sitemap)
    sitemap_lastmod = dict(sitemap_pairs)
    rss = Path('podcast/rss.xml').read_text(encoding='utf-8')
    rss_pairs = re.findall(r'<link>' + re.escape(SITE) + r'/podcast/([^<]+)\.html</link>.*?<pubDate>([^<]+)</pubDate>', rss, re.DOTALL)
    rss_dates = {}
    for link, pub in rss_pairs:
        rss_dates[link] = datetime.strptime(pub, '%a, %d %b %Y %H:%M:%S +0000').strftime('%Y-%m-%d')

    # No file may list the same episode twice (e.g. from a re-run of the generator)
    for name, slugs in [('podcast/index.html', index_slugs),
                        ('js/episodes.js', js_slugs),
                        ('sitemap.xml', [s for s, _ in sitemap_pairs]),
                        ('podcast/rss.xml', [s for s, _ in rss_pairs])]:
        for slug in sorted({s for s in slugs if slugs.count(s) > 1}):
            err(f'{slug}: listed more than once in {name}')

    # 1. Listing completeness
    for name, listed in [('podcast/index.html', set(index_slugs)),
                         ('js/episodes.js', set(js_slugs)),
                         ('sitemap.xml', set(sitemap_lastmod)),
                         ('podcast/rss.xml', set(rss_dates))]:
        for slug in sorted(pages - listed):
            err(f'{slug}: missing from {name}')
        for slug in sorted(listed - pages):
            err(f'{slug}: listed in {name} but podcast/{slug}.html does not exist')

    # 2. Index sorted newest-first, and matches episodes.js order reversed
    if index_slugs != sorted(index_slugs, key=lambda s: index_dates[s], reverse=True):
        err('podcast/index.html: episode list is not sorted newest-first')
    if set(index_slugs) == set(js_slugs) and index_slugs != list(reversed(js_slugs)):
        err('podcast/index.html order does not match js/episodes.js order reversed '
            '(a date or list position is probably wrong)')

    today = datetime.now()
    for slug in sorted(pages):
        src = Path(f'podcast/{slug}.html').read_text(encoding='utf-8')
        m = re.search(r'article:published_time" content="([^"]+)"', src)
        pub = m.group(1) if m else None
        if not pub:
            err(f'{slug}: missing article:published_time meta')
            continue

        # 3. Date consistency and sanity
        pub_dt = datetime.strptime(pub, '%Y-%m-%d')
        if pub_dt > today + timedelta(days=2):
            err(f'{slug}: published_time {pub} is in the future')
        if slug in index_dates and index_dates[slug] != pub:
            err(f'{slug}: index data-date {index_dates[slug]} != page published_time {pub}')
        if slug in rss_dates and rss_dates[slug] != pub:
            err(f'{slug}: RSS pubDate {rss_dates[slug]} != page published_time {pub} '
                '(run scripts/build_rss.py)')
        if slug in sitemap_lastmod and sitemap_lastmod[slug] < pub:
            err(f'{slug}: sitemap lastmod {sitemap_lastmod[slug]} is before published_time {pub}')
        for block in jsonld_blocks(src):
            if block.get('@type') == 'Article':
                if block.get('datePublished') != pub:
                    err(f'{slug}: JSON-LD datePublished {block.get("datePublished")} != {pub}')

        # 4. FAQ presence and visible/schema parity
        faq = next((b for b in jsonld_blocks(src) if b.get('@type') == 'FAQPage'), None)
        visible_qs = [html.unescape(re.sub(r'<[^>]+>', '', q)).strip()
                      for q in re.findall(r'<summary[^>]*>(.*?)</summary>', src, re.DOTALL)]
        if faq is None:
            err(f'{slug}: missing FAQPage JSON-LD')
        elif not visible_qs:
            err(f'{slug}: has FAQPage JSON-LD but no visible <details> FAQ section')
        else:
            schema_qs = [q.get('name', '').strip() for q in faq.get('mainEntity', [])]
            if schema_qs != visible_qs:
                err(f'{slug}: visible FAQ questions do not exactly match FAQPage schema names')

        # 5. Pre-rendered episode-nav matches the chain
        m = re.search(r'<div id="episode-nav"[^>]*>(.*?)</div>', src, re.DOTALL)
        if not m:
            err(f'{slug}: missing <div id="episode-nav">')
        elif slug in js_slugs:
            i = js_slugs.index(slug)
            expected = prerender_nav.render_nav(
                episodes[i - 1] if i > 0 else None,
                episodes[i + 1] if i + 1 < len(episodes) else None)
            if m.group(1).strip() != expected.strip():
                err(f'{slug}: pre-rendered episode-nav is empty or stale '
                    '(run scripts/prerender_nav.py)')

    if errors:
        print(f'FAILED: {len(errors)} problem(s) found\n')
        for e in errors:
            print(f'  - {e}')
        sys.exit(1)
    print(f'OK: {len(pages)} episode pages consistent across index, episodes.js, sitemap, and RSS.')


if __name__ == '__main__':
    main()
