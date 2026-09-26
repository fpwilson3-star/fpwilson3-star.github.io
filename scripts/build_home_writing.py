"""Bake the newest Medium essays into the homepage's #writing section.

The section used to ship a hand-baked set of cards and refresh them in the
browser through rss2json, a free third-party proxy. Nothing ever rebaked the
static cards, so whenever the proxy failed -- and always for crawlers that don't
run JS -- the homepage showed essays from April while the feed moved on. The
site's highest-authority page looked like it had stopped updating.

This fetches the Medium feed directly and writes the cards between the
HOME-WRITING markers, so the HTML itself is current and no client-side fetch is
needed. update-podcast.yml runs it weekly.

A failed fetch is a warning, not an error: the existing cards stay and the rest
of the weekly run (the latest-episode box) still goes through. Per the sitemap
freshness policy, the homepage's <lastmod> is bumped only when the rendered
block actually changes.

Usage: python scripts/build_home_writing.py [--dry-run]
"""
import html as htmlmod
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

FEED_URL = 'https://medium.com/feed/@fperrywilson'
CARD_COUNT = 6

START = '<!-- HOME-WRITING-START -->'
END = '<!-- HOME-WRITING-END -->'


def fetch_essays(limit=CARD_COUNT):
    req = urllib.request.Request(
        FEED_URL, headers={'User-Agent': 'fperrywilson.com homepage builder'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        root = ET.fromstring(resp.read())

    essays = []
    for item in root.iter('item'):
        title = (item.findtext('title') or '').strip()
        link = (item.findtext('link') or '').strip()
        pub = item.findtext('pubDate')
        if not (title and link and pub):
            continue
        # Medium appends a ?source=rss-... tracking param; link the clean URL.
        link = link.split('?', 1)[0]
        # The feed's description is an HTML fragment whose snippet paragraph is
        # the essay's subtitle -- the same one-liner Medium shows on its cards.
        snippet = re.search(r'<p class="medium-feed-snippet">(.*?)</p>',
                            item.findtext('description') or '', re.DOTALL)
        subtitle = htmlmod.unescape(re.sub(r'<[^>]+>', '', snippet.group(1))).strip() if snippet else ''
        essays.append({
            'title': title,
            'link': link,
            'date': parsedate_to_datetime(pub),
            'subtitle': subtitle,
        })
    essays.sort(key=lambda e: e['date'], reverse=True)
    return essays[:limit]


def render_block(essays):
    lines = [f'        {START}']
    for e in essays:
        date = f'{e["date"]:%b} {e["date"].day}, {e["date"].year}'
        lines.append(
            f'        <a href="{htmlmod.escape(e["link"])}" target="_blank" rel="noopener noreferrer" class="article-card">\n'
            f'          <p class="article-date">{date}</p>\n'
            f'          <h3>{htmlmod.escape(e["title"])}</h3>\n'
            + (f'          <p>{htmlmod.escape(e["subtitle"])}</p>\n' if e['subtitle'] else '')
            + '        </a>'
        )
    lines.append(f'        {END}')
    return '\n'.join(lines)


def bump_home_lastmod(dry_run):
    path = Path('sitemap.xml')
    src = path.read_text(encoding='utf-8')
    today = datetime.now().strftime('%Y-%m-%d')
    new, n = re.subn(
        r'(<loc>https://fperrywilson\.com/</loc>\s*<lastmod>)[^<]+(</lastmod>)',
        rf'\g<1>{today}\g<2>', src, count=1)
    if not n:
        print('  WARNING: no homepage entry in sitemap.xml to bump.')
        return
    if not dry_run:
        path.write_text(new, encoding='utf-8')
    print(f'  sitemap.xml homepage lastmod -> {today}')


def main():
    dry_run = '--dry-run' in sys.argv
    try:
        essays = fetch_essays()
    except Exception as exc:  # network, HTTP, or XML error
        print(f'WARNING: could not read the Medium feed ({exc}); keeping current cards.')
        return
    if not essays:
        print('WARNING: Medium feed had no usable items; keeping current cards.')
        return

    path = Path('index.html')
    src = path.read_text(encoding='utf-8')
    if START not in src or END not in src:
        sys.exit(f'ERROR: {START} / {END} markers not found in index.html.')

    block = render_block(essays)
    pattern = re.compile(r' *' + re.escape(START) + r'.*?' + re.escape(END), re.DOTALL)
    if pattern.search(src).group(0) == block:
        print('index.html: writing cards already current.')
        return

    if not dry_run:
        path.write_text(pattern.sub(lambda _: block, src, count=1), encoding='utf-8')
    print(f'index.html: writing cards updated ({len(essays)} essays, newest '
          f'{essays[0]["date"]:%Y-%m-%d}){" [dry run]" if dry_run else ""}')
    bump_home_lastmod(dry_run)


if __name__ == '__main__':
    main()
