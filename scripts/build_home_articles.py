"""Surface recent episode articles on the homepage, inside the podcast section.

The homepage is the site's highest-authority page and its main landing point
for people who just googled the host's name. Before this it linked to
/podcast/ once and to no individual article, so the evidence archive -- the
best argument for listening to the show -- sat behind a single button.

This writes three things into a marker block in the #podcast section:

  1. a "Read the evidence" link for the latest episode, but only when that
     episode can be matched to an article by exact title (see below);
  2. cards for the newest HOME_CARD_COUNT articles, reusing the .articles-grid
     / .article-card markup the Writing section already uses;
  3. a topic strip linking all the hub pages, which is what keeps the older
     articles reachable from the homepage as the card list rotates past them.

The block sits *after* the LATEST-EPISODE markers rather than inside them,
because update-podcast.yml rewrites that block weekly from the podcast feed and
would otherwise clobber whatever we put there.

Per the sitemap freshness policy, the homepage's <lastmod> is bumped only when
the rendered block actually changes -- same rule update-podcast.yml follows.

Usage: python scripts/build_home_articles.py [--dry-run]
"""
import html as htmlmod
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import episode_blocks  # noqa: E402

HOME_CARD_COUNT = 3

START = '<!-- HOME-ARTICLES-START -->'
END = '<!-- HOME-ARTICLES-END -->'

# The block is anchored between the latest-episode box and the platform buttons.
_LATEST_END = '<!-- LATEST-EPISODE-END -->'
_PODCAST_LINKS = '        <div class="podcast-links">'


def recent_articles(limit=HOME_CARD_COUNT):
    """The newest episode articles, from podcast/index.html.

    That file is the validated newest-first ordering (check_site.py enforces it
    against episodes.js), so it is the right source for "recent" rather than
    re-deriving an order here.
    """
    src = Path('podcast/index.html').read_text(encoding='utf-8')
    entries = re.findall(
        r'<div class="media-item"[^>]*data-date="([^"]+)"[^>]*>.*?'
        r'<span class="media-date">([^<]+)</span>.*?'
        r'<div class="media-outlet"><a href="/podcast/([^"]+)\.html">(.*?)</a></div>',
        src, re.DOTALL)
    out = []
    for date_iso, date_display, slug, headline in entries[:limit]:
        page = Path(f'podcast/{slug}.html')
        if not page.exists():
            continue
        m = re.search(r'<meta name="description" content="([^"]*)"',
                      page.read_text(encoding='utf-8'))
        out.append({
            'slug': slug,
            'date_iso': date_iso,
            'date_display': date_display.strip(),
            # The headline as written in the index (already HTML-escaped there).
            'headline': htmlmod.unescape(re.sub(r'<[^>]+>', '', headline)).strip(),
            # The meta description is written to earn a click, which is exactly
            # this card's job -- so it, not the answer-shaped Short answer box.
            'description': htmlmod.unescape(m.group(1)) if m else '',
        })
    return out


def latest_episode_article():
    """The article for the episode currently in the latest-episode box, or None.

    Matches on the episode title in each article's PodcastEpisode JSON-LD. The
    box is driven by the podcast feed and the article by a transcript, so the
    two can legitimately disagree (an episode airs before its article exists).
    Rather than guess, this returns None and the caller omits the link -- the
    same "skip rather than mislink" rule the rest of the pipeline follows.
    """
    home = Path('index.html').read_text(encoding='utf-8')
    box = re.search(re.escape('<!-- LATEST-EPISODE-START -->') + r'(.*?)'
                    + re.escape(_LATEST_END), home, re.DOTALL)
    if not box:
        return None
    title_m = re.search(r'<a href="https://podcasts\.apple\.com[^"]*"[^>]*>(.*?)</a>',
                        box.group(1), re.DOTALL)
    if not title_m:
        return None
    episode_title = htmlmod.unescape(re.sub(r'<[^>]+>', '', title_m.group(1))).strip()

    for page in sorted(Path('podcast').glob('*.html')):
        if page.stem == 'index':
            continue
        src = page.read_text(encoding='utf-8')
        m = re.search(r'"@type": "PodcastEpisode",\s*\n\s*"name": "((?:[^"\\]|\\.)*)"', src)
        if not m:
            continue
        import json
        if json.loads(f'"{m.group(1)}"').strip() == episode_title:
            h1 = re.search(r'<h1[^>]*>(.*?)</h1>', src, re.DOTALL)
            return {
                'slug': page.stem,
                'headline': htmlmod.unescape(re.sub(r'<[^>]+>', '', h1.group(1))).strip()
                if h1 else page.stem,
            }
    return None


def render_block():
    """The full marker block, including the markers themselves."""
    articles = recent_articles()
    lines = [f'        {START}']

    latest = latest_episode_article()
    if latest:
        lines.append(
            '        <p style="margin: -12px 0 24px;">'
            f'<a href="/podcast/{latest["slug"]}.html" '
            'style="font-family: var(--font-mono); font-size: 0.8rem; '
            'text-transform: uppercase; letter-spacing: 0.08em; '
            'color: var(--color-accent); text-decoration: none;">'
            'Read the evidence &rarr;</a></p>'
        )

    if articles:
        lines.append('        <p style="font-size: 0.85rem; font-family: var(--font-mono); '
                     'color: var(--color-muted); text-transform: uppercase; '
                     'letter-spacing: 0.08em; margin-bottom: 12px;">Recent episode articles</p>')
        lines.append('        <div class="articles-grid">')
        for a in articles:
            lines.append(
                f'          <a href="/podcast/{a["slug"]}.html" class="article-card">\n'
                f'            <p class="article-date">{htmlmod.escape(a["date_display"])}</p>\n'
                f'            <h3>{htmlmod.escape(a["headline"])}</h3>\n'
                f'            <p>{htmlmod.escape(a["description"])}</p>\n'
                '          </a>'
            )
        lines.append('        </div>')

    # The card list rotates, so the hubs are what keep older articles linked
    # from the homepage at all.
    topics = [(name, episode_blocks.topic_slug(name))
              for name in episode_blocks.TOPIC_META]
    topic_links = '\n'.join(
        f'          <a href="/podcast/topics/{slug}.html" '
        'style="color: var(--color-accent); text-decoration: none;">'
        f'{htmlmod.escape(name)}</a>'
        + ('' if i == len(topics) - 1 else '<span style="color: var(--color-faint);"> &middot; </span>')
        for i, (name, slug) in enumerate(topics))
    lines.append(
        '        <p style="font-size: 0.85rem; font-family: var(--font-mono); '
        'color: var(--color-muted); text-transform: uppercase; letter-spacing: 0.08em; '
        'margin: 28px 0 10px;">Browse by topic</p>\n'
        '        <p style="font-size: 0.95rem; line-height: 1.9; margin-bottom: 28px;">\n'
        + topic_links + '\n        </p>'
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
    path = Path('index.html')
    src = path.read_text(encoding='utf-8')
    block = render_block()

    if START in src and END in src:
        pattern = re.compile(r' *' + re.escape(START) + r'.*?' + re.escape(END), re.DOTALL)
        current = pattern.search(src).group(0)
        if current == block:
            print('index.html: recent-articles block already current.')
            return
        src = pattern.sub(lambda _: block, src, count=1)
        action = 'updated'
    else:
        if _PODCAST_LINKS not in src:
            sys.exit('ERROR: could not find the .podcast-links div to anchor the block.')
        src = src.replace(_PODCAST_LINKS, block + '\n' + _PODCAST_LINKS, 1)
        action = 'inserted'

    if not dry_run:
        path.write_text(src, encoding='utf-8')
    n = len(recent_articles())
    print(f'index.html: recent-articles block {action} '
          f'({n} card(s) + {len(episode_blocks.TOPIC_META)} topic links)'
          f'{" [dry run]" if dry_run else ""}')
    bump_home_lastmod(dry_run)


if __name__ == '__main__':
    main()
