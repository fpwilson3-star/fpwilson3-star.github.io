"""Retrofit episode-specific Apple Podcasts links onto existing episode pages.

For each podcast/*.html page, finds the matching episode via the iTunes
Lookup API and, when a confident match exists:
  1. wraps the episode title in the "listen" box in a link to the episode,
  2. points the Apple Podcasts button at the episode instead of the show,
  3. inserts a PodcastEpisode JSON-LD block.

Matching is title-first: a page is only updated when the episode title on the
page matches the Apple episode name (exactly, or by distinctive topic words
plus a date sanity check). Pages with no confident match are skipped and
reported — on this site a missing episode link is better than a wrong one.

Idempotent: pages that already have PodcastEpisode JSON-LD are skipped.

Usage: python scripts/retrofit_episode_links.py [--dry-run]
"""
import html as htmlmod
import json
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

SHOW_APPLE_URL = ('https://podcasts.apple.com/us/podcast/'
                  'wellness-actually-with-emily-oster-perry-wilson-md/id1633515294')
LOOKUP_URL = 'https://itunes.apple.com/lookup?id=1633515294&entity=podcastEpisode&limit=200'

# Words too generic to identify a topic ("What's the deal with...?" boilerplate)
STOPWORDS = {
    'what', 'whats', 'the', 'deal', 'with', 'and', 'for', 'are', 'is', 'do',
    'does', 'did', 'actually', 'work', 'works', 'working', 'really', 'your',
    'you', 'evidence', 'says', 'show', 'shows', 'about', 'a', 'an', 'of',
    'in', 'on', 'to', 'how', 'much', 'should', 'can', 'we', 'it', 'anything',
}


def norm(s):
    s = htmlmod.unescape(s).lower()
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]', ' ', s)).strip()


def topic_words(title):
    return {w for w in norm(title).split() if w not in STOPWORDS and len(w) >= 3}


def fetch_episodes():
    payload = json.loads(urllib.request.urlopen(LOOKUP_URL, timeout=30).read())
    episodes = []
    for item in payload.get('results', []):
        if item.get('kind') != 'podcast-episode' or not item.get('trackViewUrl'):
            continue
        try:
            released = datetime.strptime(item['releaseDate'][:10], '%Y-%m-%d')
        except (KeyError, ValueError):
            continue
        episodes.append({
            'name': item['trackName'],
            'url': item['trackViewUrl'],
            'date': released,
        })
    return episodes


def match_episode(page_title, page_date, episodes):
    """Return the matching episode dict or None. Title-first; never date-only."""
    exact = [e for e in episodes if norm(e['name']) == norm(page_title)]
    if len(exact) == 1:
        return exact[0]

    words = topic_words(page_title)
    candidates = []
    for e in episodes:
        overlap = len(words & topic_words(e['name']))
        delta = abs((e['date'] - page_date).days)
        if overlap >= 1 and delta <= 21:
            candidates.append((overlap, -delta, e))
    if not candidates:
        return None
    candidates.sort(key=lambda c: (c[0], c[1]), reverse=True)
    # Require a unique best match
    if len(candidates) > 1 and candidates[0][:2] == candidates[1][:2]:
        return None
    return candidates[0][2]


def render_episode_jsonld(name, date_iso, url):
    payload = {
        "@context": "https://schema.org",
        "@type": "PodcastEpisode",
        "name": name,
        "datePublished": date_iso,
        "url": url,
        "partOfSeries": {
            "@type": "PodcastSeries",
            "name": "Wellness, Actually",
            "url": "https://fperrywilson.com/podcast/"
        }
    }
    body = json.dumps(payload, indent=2, ensure_ascii=False)
    indented = '\n'.join('  ' + line for line in body.split('\n'))
    return f'  <script type="application/ld+json">\n{indented}\n  </script>\n'


def retrofit(page, episodes, dry_run):
    src = page.read_text(encoding='utf-8')
    if '"@type": "PodcastEpisode"' in src:
        return 'already done'

    m = re.search(r'article:published_time" content="([^"]+)"', src)
    if not m:
        return 'SKIPPED: no published_time'
    page_date = datetime.strptime(m.group(1), '%Y-%m-%d')

    m = re.search(
        r'(<p style="font-size: 1\.05rem; margin-bottom: 20px;">)(<strong>"([^<]+)"</strong>)', src)
    if not m:
        return 'SKIPPED: listen-box title not found'
    box_prefix, title_html, page_title = m.group(1), m.group(2), m.group(3)

    ep = match_episode(page_title, page_date, episodes)
    if not ep:
        return f'SKIPPED: no confident Apple match for "{page_title}"'

    apple_button = (f'<a href="{SHOW_APPLE_URL}" target="_blank" rel="noopener noreferrer" '
                    f'class="btn btn-primary">Apple Podcasts</a>')
    if apple_button not in src:
        return 'SKIPPED: Apple Podcasts button not in expected form'

    linked_title = (f'<a href="{ep["url"]}" target="_blank" rel="noopener noreferrer" '
                    f'style="color: inherit;">{title_html}</a>')
    new_src = src.replace(box_prefix + title_html, box_prefix + linked_title, 1)
    new_src = new_src.replace(
        apple_button,
        f'<a href="{ep["url"]}" target="_blank" rel="noopener noreferrer" '
        f'class="btn btn-primary">Apple Podcasts</a>', 1)
    jsonld = render_episode_jsonld(ep['name'], ep['date'].strftime('%Y-%m-%d'), ep['url'])
    new_src = new_src.replace('</head>', jsonld + '</head>', 1)

    if not dry_run:
        page.write_text(new_src, encoding='utf-8')
    return f'linked -> {ep["name"]} ({ep["date"].strftime("%Y-%m-%d")})'


def main():
    dry_run = '--dry-run' in sys.argv
    episodes = fetch_episodes()
    print(f'Fetched {len(episodes)} episodes from Apple.\n')
    skipped = 0
    for page in sorted(Path('podcast').glob('*.html')):
        if page.stem == 'index':
            continue
        result = retrofit(page, episodes, dry_run)
        if result.startswith('SKIPPED'):
            skipped += 1
        print(f'  {page.stem}: {result}')
    print(f'\nDone{" (dry run, nothing written)" if dry_run else ""}. {skipped} page(s) skipped.')


if __name__ == '__main__':
    main()
