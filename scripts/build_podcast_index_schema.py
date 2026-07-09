"""Regenerate the CollectionPage / ItemList JSON-LD on podcast/index.html.

The episode-article index used to carry a bare CollectionPage that named the
collection but listed none of its members. This enumerates every episode
article as an ItemList (newest-first, matching the visible list), so search and
answer engines see the full corpus as one browseable set rather than a stub.

The episode list is read from podcast/index.html itself (reusing build_rss's
parser) so it stays in lockstep with the visible list, the RSS feed, the
sitemap, and llms.txt.

Idempotent: safe to re-run; it replaces the CollectionPage block in place.

Usage: python scripts/build_podcast_index_schema.py
"""
import json
import re
from pathlib import Path

import build_rss
import episode_blocks

INDEX = Path('podcast/index.html')
SCRIPT_RE = re.compile(r'  <script type="application/ld\+json">\n(.*?)\n  </script>', re.DOTALL)


def render_block(entries):
    """CollectionPage whose mainEntity is an ordered ItemList of every article."""
    items = [
        {"@type": "ListItem", "position": i + 1, "url": e['url'], "name": e['title']}
        for i, e in enumerate(entries)
    ]
    obj = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": episode_blocks.COLLECTION_NAME,
        "description": build_rss.FEED_DESC,
        "url": episode_blocks.COLLECTION_URL,
        "author": {"@type": "Person", "name": "F. Perry Wilson", "url": "https://fperrywilson.com"},
        "mainEntity": {
            "@type": "ItemList",
            "itemListOrder": "https://schema.org/ItemListOrderDescending",
            "numberOfItems": len(items),
            "itemListElement": items,
        },
    }
    body = json.dumps(obj, indent=2, ensure_ascii=False)
    indented = '\n'.join('  ' + line for line in body.split('\n'))
    return f'  <script type="application/ld+json">\n{indented}\n  </script>'


def main():
    entries = build_rss.parse_entries()  # newest-first [{date, url, title, description}]
    src = INDEX.read_text(encoding='utf-8')

    def replace(m):
        try:
            block = json.loads(m.group(1))
        except json.JSONDecodeError:
            return m.group(0)
        if block.get('@type') == 'CollectionPage':
            return render_block(entries)
        return m.group(0)

    new_src, n = SCRIPT_RE.subn(replace, src)
    if not any(json.loads(m.group(1)).get('@type') == 'CollectionPage'
               for m in SCRIPT_RE.finditer(src)):
        raise SystemExit('ERROR: no CollectionPage JSON-LD block found in podcast/index.html')
    if new_src != src:
        INDEX.write_text(new_src, encoding='utf-8')
    print(f'Wrote CollectionPage ItemList with {len(entries)} episode articles')


if __name__ == '__main__':
    main()
