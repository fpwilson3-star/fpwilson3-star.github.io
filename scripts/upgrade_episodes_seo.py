"""One-shot SEO upgrade for all /podcast/*.html episode pages."""
import re
from pathlib import Path

# Oldest-first, matches js/episodes.js
EPISODES = [
    ('are-sperm-counts-really-declining',           'Are sperm counts really declining?',            '2026-02-12', 'February 12, 2026'),
    ('do-peptide-injections-actually-work',         'Do peptide injections actually work?',          '2026-02-19', 'February 19, 2026'),
    ('cold-plunges-saunas-health-benefits',         'Do cold plunges and saunas work?',              '2026-02-26', 'February 26, 2026'),
    ('glp-1-weight-loss-evidence',                  'GLP-1s for weight loss',                        '2026-03-05', 'March 5, 2026'),
    ('does-red-light-therapy-actually-work',        'Does red light therapy work?',                  '2026-03-12', 'March 12, 2026'),
    ('are-microplastics-actually-harming-your-health', 'Are microplastics harming your health?',     '2026-03-19', 'March 19, 2026'),
    ('do-stem-cell-injections-actually-work',       'Do stem cell injections work?',                 '2026-03-26', 'March 26, 2026'),
    ('does-creatine-actually-work',                 'Does creatine actually work?',                  '2026-04-02', 'April 2, 2026'),
    ('how-much-protein-do-you-actually-need',       'How much protein do you need?',                 '2026-04-09', 'April 9, 2026'),
]


def upgrade_head(html: str, slug: str, title: str) -> str:
    # 1. Inject favicon + RSS alternate after the stylesheet link
    if 'rel="icon"' not in html:
        html = html.replace(
            '<link rel="stylesheet" href="../css/style.css">',
            '<link rel="icon" href="/favicon.ico" sizes="any">\n'
            '  <link rel="apple-touch-icon" href="/images/apple-touch-icon.png">\n'
            '  <link rel="alternate" type="application/rss+xml" title="Wellness, Actually — Episode Articles" href="/podcast/rss.xml">\n'
            '  <link rel="stylesheet" href="../css/style.css">'
        )

    # 2. Swap old OG image → new 1200x630 og-podcast.jpg everywhere
    html = html.replace(
        'https://fperrywilson.com/images/wellness%20actually%20cover.png',
        'https://fperrywilson.com/images/og-podcast.jpg',
    )

    # 3. Add OG/Twitter extras right after og:image
    if 'og:image:width' not in html:
        html = html.replace(
            '<meta property="og:image" content="https://fperrywilson.com/images/og-podcast.jpg">',
            '<meta property="og:image" content="https://fperrywilson.com/images/og-podcast.jpg">\n'
            '  <meta property="og:image:width" content="1200">\n'
            '  <meta property="og:image:height" content="630">\n'
            '  <meta property="og:image:alt" content="Wellness, Actually podcast — with Emily Oster and F. Perry Wilson, MD">\n'
            '  <meta property="og:site_name" content="F. Perry Wilson, MD">'
        )

    if 'twitter:creator' not in html:
        html = html.replace(
            '<meta name="twitter:site" content="@fperrywilson">',
            '<meta name="twitter:site" content="@fperrywilson">\n'
            '  <meta name="twitter:creator" content="@fperrywilson">'
        )

    if 'twitter:image:alt' not in html:
        html = html.replace(
            '<meta name="twitter:image" content="https://fperrywilson.com/images/og-podcast.jpg">',
            '<meta name="twitter:image" content="https://fperrywilson.com/images/og-podcast.jpg">\n'
            '  <meta name="twitter:image:alt" content="Wellness, Actually podcast — with Emily Oster and F. Perry Wilson, MD">'
        )

    # 4. Add PodcastEpisode JSON-LD right before </head>
    if 'PodcastEpisode' not in html:
        podcast_ep = (
            '  <script type="application/ld+json">\n'
            '  {\n'
            '    "@context": "https://schema.org",\n'
            '    "@type": "PodcastEpisode",\n'
            f'    "name": "{title.replace(chr(34), chr(92)+chr(34))}",\n'
            f'    "url": "https://fperrywilson.com/podcast/{slug}.html",\n'
            '    "image": "https://fperrywilson.com/images/wellness-actually-cover.jpg",\n'
            '    "partOfSeries": {\n'
            '      "@type": "PodcastSeries",\n'
            '      "name": "Wellness, Actually",\n'
            '      "url": "https://fperrywilson.com/podcast/"\n'
            '    },\n'
            '    "author": [\n'
            '      {"@type": "Person", "name": "F. Perry Wilson", "url": "https://fperrywilson.com"},\n'
            '      {"@type": "Person", "name": "Emily Oster"}\n'
            '    ]\n'
            '  }\n'
            '  </script>\n'
        )
        html = html.replace('</head>', podcast_ep + '</head>')

    return html


def upgrade_body(html: str, slug: str) -> str:
    idx = next((i for i, e in enumerate(EPISODES) if e[0] == slug), -1)
    if idx == -1:
        return html

    prev_ep = EPISODES[idx - 1] if idx > 0 else None
    next_ep = EPISODES[idx + 1] if idx < len(EPISODES) - 1 else None

    link_style = ('font-family:var(--font-mono);font-size:0.85rem;'
                  'color:var(--color-accent);text-decoration:none;')
    muted_style = ('font-family:var(--font-mono);font-size:0.85rem;'
                   'color:var(--color-muted);')

    prev_html = (f'<a href="/podcast/{prev_ep[0]}.html" style="{link_style}">← {prev_ep[1]}</a>'
                 if prev_ep else f'<span style="{muted_style}">Oldest article</span>')
    next_html = (f'<a href="/podcast/{next_ep[0]}.html" style="{link_style}">{next_ep[1]} →</a>'
                 if next_ep else f'<span style="{muted_style}">Newest article</span>')
    all_html = f'<a href="/podcast/" style="{muted_style}">All articles</a>'

    # Pre-render the prev/next nav for crawlers (JS will re-render on client)
    html = re.sub(
        r'<div id="episode-nav"([^>]*)></div>',
        lambda m: f'<div id="episode-nav"{m.group(1)}>{prev_html}{all_html}{next_html}</div>',
        html,
        count=1,
    )

    return html


def main():
    root = Path('podcast')
    for slug, title, _, _ in EPISODES:
        path = root / f'{slug}.html'
        if not path.exists():
            print(f'SKIP (missing): {path}')
            continue
        html = path.read_text(encoding='utf-8')
        before = html
        html = upgrade_head(html, slug, title)
        html = upgrade_body(html, slug)
        if html != before:
            path.write_text(html, encoding='utf-8')
            print(f'UPDATED: {path}')
        else:
            print(f'unchanged: {path}')


if __name__ == '__main__':
    main()
