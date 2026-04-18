"""Regenerate /podcast/rss.xml from podcast/index.html entries.

Reads the episode list out of podcast/index.html between <!-- EPISODES-START -->
and </div>, then writes a valid RSS 2.0 feed.
"""
import re
from pathlib import Path
from datetime import datetime, timezone
import html as htmlmod

SITE = 'https://fperrywilson.com'
FEED_TITLE = 'Wellness, Actually — Episode Articles'
FEED_DESC = ('Evidence-based health articles by F. Perry Wilson, MD MSCE, '
             'drawn from the Wellness, Actually podcast.')


def parse_entries():
    src = Path('podcast/index.html').read_text(encoding='utf-8')
    # Grab every media-item inside the EPISODES block
    m = re.search(r'<!-- EPISODES-START -->(.*?)</div>\s*</div>\s*</div>',
                  src, re.DOTALL)
    block = m.group(1) if m else src

    entries = []
    item_re = re.compile(
        r'<div class="media-item"[^>]*data-date="([^"]+)"[^>]*>.*?'
        r'<div class="media-outlet"><a href="([^"]+)">(.*?)</a></div>.*?'
        r'<p class="media-description">(.*?)</p>',
        re.DOTALL
    )
    for date, href, title, desc in item_re.findall(block):
        full_url = SITE + href if href.startswith('/') else href
        entries.append({
            'date': date,
            'url': full_url,
            'title': re.sub(r'<[^>]+>', '', title).strip(),
            'description': re.sub(r'<[^>]+>', '', desc).strip(),
        })
    # Newest first
    entries.sort(key=lambda e: e['date'], reverse=True)
    return entries


def to_rfc822(iso_date):
    dt = datetime.strptime(iso_date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    return dt.strftime('%a, %d %b %Y %H:%M:%S +0000')


def build_rss(entries):
    now = datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S +0000')
    items = []
    for e in entries:
        items.append(f'''    <item>
      <title>{htmlmod.escape(e['title'])}</title>
      <link>{e['url']}</link>
      <guid isPermaLink="true">{e['url']}</guid>
      <pubDate>{to_rfc822(e['date'])}</pubDate>
      <description>{htmlmod.escape(e['description'])}</description>
    </item>''')

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{FEED_TITLE}</title>
    <link>{SITE}/podcast/</link>
    <atom:link href="{SITE}/podcast/rss.xml" rel="self" type="application/rss+xml"/>
    <description>{FEED_DESC}</description>
    <language>en-us</language>
    <lastBuildDate>{now}</lastBuildDate>
{chr(10).join(items)}
  </channel>
</rss>
'''


def main():
    entries = parse_entries()
    rss = build_rss(entries)
    out = Path('podcast/rss.xml')
    out.write_text(rss, encoding='utf-8')
    print(f'Wrote {out} with {len(entries)} items')


if __name__ == '__main__':
    main()
