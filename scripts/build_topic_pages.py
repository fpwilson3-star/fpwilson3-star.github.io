"""Generate the topic hub pages and the topics index from the CLUSTERS map.

For each topic in episode_blocks.CLUSTERS this writes a crawlable hub page at
/podcast/topics/<slug>.html listing that topic's episode articles (newest-first)
with its own CollectionPage -> ItemList schema, and writes a /podcast/topics/
index linking every hub. It also regenerates the "Browse by topic" strip on
podcast/index.html and keeps the topic URLs in sitemap.xml.

Episode metadata (title, description, date) is read from podcast/index.html
(reusing build_rss's parser), so hubs stay in lockstep with the article list.
A hub's <lastmod> is the date of its newest member article, which is a real
content-change signal, never an artificial bump.

Idempotent: safe to re-run; wired into generate_episode_post.py so a pushed
transcript refreshes every hub the new episode belongs to with no manual step.

Usage: python scripts/build_topic_pages.py
"""
import json
import re
from datetime import datetime
from pathlib import Path

import build_rss
import episode_blocks

SITE = 'https://fperrywilson.com'
TOPICS_DIR = Path('podcast/topics')

NAV_HTML = '''  <nav class="nav" id="nav">
    <div class="nav-inner">
      <a href="/" class="nav-logo">F. Perry Wilson<span>,</span> MD</a>
      <ul class="nav-links" id="navLinks">
        <li><a href="/#about">About</a></li>
        <li><a href="/#podcast">Podcast</a></li>
        <li><a href="/#book">Book</a></li>
        <li><a href="/#writing">Writing</a></li>
        <li><a href="/#media">Media</a></li>
        <li><a href="/#lab">Lab</a></li>
        <li><a href="/#course">Course</a></li>
      </ul>
      <button class="nav-toggle" id="navToggle" aria-label="Toggle navigation">
        <span></span><span></span><span></span>
      </button>
    </div>
  </nav>'''

FOOTER_HTML = '''  <footer class="footer">
    <div class="footer-inner">
      <p class="footer-name">F. Perry Wilson, MD MSCE</p>
      <div class="footer-links">
        <a href="https://fperrywilson.medium.com/" target="_blank" rel="noopener noreferrer">Medium</a>
        <a href="https://www.medscape.com/index/list_12471_0" target="_blank" rel="noopener noreferrer">Medscape</a>
        <a href="/podcast/">Episode Articles</a>
        <a href="https://podcasts.apple.com/us/podcast/wellness-actually-with-emily-oster-perry-wilson-md/id1633515294" target="_blank" rel="noopener noreferrer">Podcast</a>
        <a href="https://twitter.com/fperrywilson" target="_blank" rel="noopener noreferrer">X / Twitter</a>
      </div>
    </div>
  </footer>'''

NAV_SCRIPT = '''  <script>
    const nav = document.getElementById('nav');
    window.addEventListener('scroll', () => nav.classList.toggle('scrolled', window.scrollY > 20));
    const navToggle = document.getElementById('navToggle');
    const navLinks = document.getElementById('navLinks');
    navToggle.addEventListener('click', () => navLinks.classList.toggle('open'));
    navLinks.querySelectorAll('a').forEach(l => l.addEventListener('click', () => navLinks.classList.remove('open')));
  </script>'''


def _esc(s):
    import html as htmlmod
    return htmlmod.escape(s)


def _jsonld(obj):
    body = json.dumps(obj, indent=2, ensure_ascii=False)
    indented = '\n'.join('  ' + line for line in body.split('\n'))
    return f'  <script type="application/ld+json">\n{indented}\n  </script>'


def _media_items(entries):
    """The episode list, in the same media-item markup the index uses."""
    rows = []
    for e in entries:
        rows.append(
            '      <div class="media-item" data-date="%s">\n'
            '        <span class="media-date">%s</span>\n'
            '        <div>\n'
            '          <div class="media-outlet"><a href="%s">%s</a></div>\n'
            '          <p class="media-description">%s</p>\n'
            '        </div>\n'
            '      </div>' % (
                e['date'], _display_date(e['date']),
                e['url'].replace(SITE, ''), _esc(e['title']), _esc(e['description']))
        )
    return '\n'.join(rows)


def _display_date(iso):
    dt = datetime.strptime(iso, '%Y-%m-%d')
    return f"{dt.strftime('%B')} {dt.day}, {dt.year}"


def render_hub(name, meta, entries):
    slug = meta['slug']
    intro = meta['intro']
    url = f'{SITE}/podcast/topics/{slug}.html'
    collection = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": f'{name} — Wellness, Actually Episode Articles',
        "description": intro,
        "url": url,
        "isPartOf": {"@type": "CollectionPage", "name": episode_blocks.COLLECTION_NAME,
                     "url": episode_blocks.COLLECTION_URL},
        "author": {"@type": "Person", "name": "F. Perry Wilson", "url": SITE},
        "mainEntity": {
            "@type": "ItemList",
            "itemListOrder": "https://schema.org/ItemListOrderDescending",
            "numberOfItems": len(entries),
            "itemListElement": [
                {"@type": "ListItem", "position": i + 1, "url": e['url'], "name": e['title']}
                for i, e in enumerate(entries)
            ],
        },
    }
    breadcrumb = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE},
            {"@type": "ListItem", "position": 2, "name": "Episode Articles", "item": f"{SITE}/podcast/"},
            {"@type": "ListItem", "position": 3, "name": "Topics", "item": f"{SITE}/podcast/topics/"},
            {"@type": "ListItem", "position": 4, "name": name, "item": url},
        ],
    }
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{_esc(name)} — Wellness, Actually Episode Articles | F. Perry Wilson, MD</title>
  <meta name="description" content="{_esc(intro)}">
  <meta name="author" content="F. Perry Wilson">
  <link rel="icon" href="/favicon.ico" sizes="any">
  <link rel="apple-touch-icon" href="/images/apple-touch-icon.png">
  <link rel="alternate" type="application/rss+xml" title="Wellness, Actually — Episode Articles" href="/podcast/rss.xml">
  <link rel="stylesheet" href="../../css/style.css">
  <link rel="canonical" href="{url}">
  <meta property="og:title" content="{_esc(name)} — Wellness, Actually Episode Articles">
  <meta property="og:description" content="{_esc(intro)}">
  <meta property="og:type" content="website">
  <meta property="og:url" content="{url}">
  <meta property="og:site_name" content="F. Perry Wilson, MD">
  <meta property="og:image" content="https://fperrywilson.com/images/og-podcast.jpg">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:image:alt" content="Wellness, Actually podcast — with Emily Oster and F. Perry Wilson, MD">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:site" content="@fperrywilson">
  <meta name="twitter:title" content="{_esc(name)} — Wellness, Actually Episode Articles">
  <meta name="twitter:description" content="{_esc(intro)}">
  <meta name="twitter:image" content="https://fperrywilson.com/images/og-podcast.jpg">
{_jsonld(collection)}
{_jsonld(breadcrumb)}
</head>
<body>

{NAV_HTML}

  <div style="max-width: 860px; margin: 100px auto 80px; padding: 0 24px;">

    <div class="section-header" style="margin-bottom: 48px;">
      <p class="section-label"><a href="/podcast/topics/" style="color: inherit; text-decoration: none;">Topics</a></p>
      <h1 class="section-title">{_esc(name)}</h1>
      <div class="section-rule"></div>
      <p style="margin-top: 20px; font-size: 1.05rem; color: var(--color-muted); max-width: 600px;">{_esc(intro)}</p>
    </div>

    <div class="media-list">
{_media_items(entries)}
    </div>

    <p style="margin-top: 40px; font-family: var(--font-mono); font-size: 0.85rem;">
      <a href="/podcast/topics/" style="color: var(--color-accent); text-decoration: none;">All topics</a>
      &nbsp;&middot;&nbsp;
      <a href="/podcast/" style="color: var(--color-muted); text-decoration: none;">All articles</a>
    </p>

{episode_blocks.render_author_bio()}
  </div>

{FOOTER_HTML}

{NAV_SCRIPT}

</body>
</html>
'''


def render_topics_index(topic_rows):
    """topic_rows: [(name, meta, entries), ...] in CLUSTERS order."""
    url = f'{SITE}/podcast/topics/'
    intro = ("Browse the Wellness, Actually episode articles by topic. Each hub "
             "collects the evidence-based deep dives on a single area of health.")
    collection = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "Browse Wellness, Actually Episode Articles by Topic",
        "description": intro,
        "url": url,
        "isPartOf": {"@type": "CollectionPage", "name": episode_blocks.COLLECTION_NAME,
                     "url": episode_blocks.COLLECTION_URL},
        "mainEntity": {
            "@type": "ItemList",
            "numberOfItems": len(topic_rows),
            "itemListElement": [
                {"@type": "ListItem", "position": i + 1,
                 "url": f"{SITE}/podcast/topics/{meta['slug']}.html", "name": name}
                for i, (name, meta, _entries) in enumerate(topic_rows)
            ],
        },
    }
    breadcrumb = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": SITE},
            {"@type": "ListItem", "position": 2, "name": "Episode Articles", "item": f"{SITE}/podcast/"},
            {"@type": "ListItem", "position": 3, "name": "Topics", "item": url},
        ],
    }
    cards = []
    for name, meta, entries in topic_rows:
        count = len(entries)
        cards.append(
            '      <div class="media-item">\n'
            f'        <span class="media-date">{count} article{"s" if count != 1 else ""}</span>\n'
            '        <div>\n'
            f'          <div class="media-outlet"><a href="/podcast/topics/{meta["slug"]}.html">{_esc(name)}</a></div>\n'
            f'          <p class="media-description">{_esc(meta["intro"])}</p>\n'
            '        </div>\n'
            '      </div>')
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Browse Episode Articles by Topic | F. Perry Wilson, MD</title>
  <meta name="description" content="{_esc(intro)}">
  <meta name="author" content="F. Perry Wilson">
  <link rel="icon" href="/favicon.ico" sizes="any">
  <link rel="apple-touch-icon" href="/images/apple-touch-icon.png">
  <link rel="alternate" type="application/rss+xml" title="Wellness, Actually — Episode Articles" href="/podcast/rss.xml">
  <link rel="stylesheet" href="../../css/style.css">
  <link rel="canonical" href="{url}">
  <meta property="og:title" content="Browse Episode Articles by Topic | F. Perry Wilson, MD">
  <meta property="og:description" content="{_esc(intro)}">
  <meta property="og:type" content="website">
  <meta property="og:url" content="{url}">
  <meta property="og:site_name" content="F. Perry Wilson, MD">
  <meta property="og:image" content="https://fperrywilson.com/images/og-podcast.jpg">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:image:alt" content="Wellness, Actually podcast — with Emily Oster and F. Perry Wilson, MD">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:site" content="@fperrywilson">
  <meta name="twitter:title" content="Browse Episode Articles by Topic | F. Perry Wilson, MD">
  <meta name="twitter:description" content="{_esc(intro)}">
  <meta name="twitter:image" content="https://fperrywilson.com/images/og-podcast.jpg">
{_jsonld(collection)}
{_jsonld(breadcrumb)}
</head>
<body>

{NAV_HTML}

  <div style="max-width: 860px; margin: 100px auto 80px; padding: 0 24px;">

    <div class="section-header" style="margin-bottom: 48px;">
      <p class="section-label"><a href="/podcast/" style="color: inherit; text-decoration: none;">Episode Articles</a></p>
      <h1 class="section-title">Browse by Topic</h1>
      <div class="section-rule"></div>
      <p style="margin-top: 20px; font-size: 1.05rem; color: var(--color-muted); max-width: 600px;">{_esc(intro)}</p>
    </div>

    <div class="media-list">
{chr(10).join(cards)}
    </div>

    <p style="margin-top: 40px; font-family: var(--font-mono); font-size: 0.85rem;">
      <a href="/podcast/" style="color: var(--color-accent); text-decoration: none;">All articles</a>
    </p>

  </div>

{FOOTER_HTML}

{NAV_SCRIPT}

</body>
</html>
'''


def render_index_strip(topic_rows):
    """The 'Browse by topic' chip strip regenerated on podcast/index.html."""
    chips = '\n'.join(
        f'        <a href="/podcast/topics/{meta["slug"]}.html" class="topic-chip" '
        f'style="display: inline-block; font-family: var(--font-mono); font-size: 0.8rem; '
        f'padding: 8px 14px; border: 1px solid #e0d9d0; border-radius: 999px; '
        f'color: var(--color-ink); text-decoration: none;">{_esc(name)}</a>'
        for name, meta, _e in topic_rows
    )
    return (
        '\n    <div style="margin-bottom: 48px;">\n'
        '      <p style="font-family: var(--font-mono); font-size: 0.72rem; text-transform: uppercase; '
        'letter-spacing: 0.12em; color: var(--color-muted); margin-bottom: 14px;">'
        '<a href="/podcast/topics/" style="color: inherit; text-decoration: none;">Browse by topic</a></p>\n'
        '      <div style="display: flex; flex-wrap: wrap; gap: 10px;">\n'
        f'{chips}\n'
        '      </div>\n'
        '    </div>\n'
    )


def update_index_strip(topic_rows):
    path = Path('podcast/index.html')
    src = path.read_text(encoding='utf-8')
    strip = render_index_strip(topic_rows)
    new_src = re.sub(r'<!-- TOPICS-START -->.*?<!-- TOPICS-END -->',
                     f'<!-- TOPICS-START -->{strip}<!-- TOPICS-END -->', src, flags=re.DOTALL)
    if new_src != src:
        path.write_text(new_src, encoding='utf-8')


def update_sitemap(topic_rows):
    """Add/refresh a <url> for each hub and the topics index. lastmod is the
    newest member article's date (topics index: newest article overall)."""
    path = Path('sitemap.xml')
    content = path.read_text(encoding='utf-8')
    # Drop any existing topic entries so we re-emit them cleanly.
    content = re.sub(
        r'  <url>\s*<loc>' + re.escape(SITE) + r'/podcast/topics/[^<]*</loc>.*?</url>\n',
        '', content, flags=re.DOTALL)

    newest_overall = max((e['date'] for _n, _m, es in topic_rows for e in es), default=None)
    blocks = []
    if newest_overall:
        blocks.append(_sitemap_url(f'{SITE}/podcast/topics/', newest_overall, 'monthly', '0.6'))
    for name, meta, entries in topic_rows:
        lastmod = max(e['date'] for e in entries)
        blocks.append(_sitemap_url(f'{SITE}/podcast/topics/{meta["slug"]}.html', lastmod, 'monthly', '0.5'))
    content = content.replace('</urlset>', ''.join(blocks) + '</urlset>')
    path.write_text(content, encoding='utf-8')


def _sitemap_url(loc, lastmod, changefreq, priority):
    return (f'  <url>\n    <loc>{loc}</loc>\n    <lastmod>{lastmod}</lastmod>\n'
            f'    <changefreq>{changefreq}</changefreq>\n    <priority>{priority}</priority>\n  </url>\n')


def topic_rows():
    """[(name, meta, entries newest-first), ...] in CLUSTERS order, entries
    limited to episodes that actually have a published article."""
    if set(episode_blocks.TOPIC_META) != set(episode_blocks.CLUSTERS):
        missing = set(episode_blocks.CLUSTERS) ^ set(episode_blocks.TOPIC_META)
        raise SystemExit(f'ERROR: CLUSTERS and TOPIC_META keys differ: {sorted(missing)}')
    by_slug = {e['url'].rsplit('/', 1)[-1][:-5]: e for e in build_rss.parse_entries()}
    rows = []
    for name, members in episode_blocks.CLUSTERS.items():
        entries = [by_slug[s] for s in members if s in by_slug]
        entries.sort(key=lambda e: e['date'], reverse=True)
        rows.append((episode_blocks.TOPIC_META[name], name, entries))
    # normalize to (name, meta, entries)
    return [(name, meta, entries) for meta, name, entries in rows]


def main():
    rows = topic_rows()
    TOPICS_DIR.mkdir(parents=True, exist_ok=True)
    for name, meta, entries in rows:
        (TOPICS_DIR / f'{meta["slug"]}.html').write_text(render_hub(name, meta, entries), encoding='utf-8')
    (TOPICS_DIR / 'index.html').write_text(render_topics_index(rows), encoding='utf-8')
    update_index_strip(rows)
    update_sitemap(rows)
    print(f'Wrote {len(rows)} topic hub pages + topics index, updated podcast/index.html strip and sitemap.xml')


if __name__ == '__main__':
    main()
