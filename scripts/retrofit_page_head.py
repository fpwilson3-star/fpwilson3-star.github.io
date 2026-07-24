"""Retrofit shared <head> requirements onto every page on the site.

For each HTML page this adds, when missing:
  1. the GA4 analytics snippet. Episode pages, topic hubs, and the podcast
     index all shipped without it, so every visit the SEO/AEO work earned was
     invisible in analytics;
  2. the Google Fonts preconnect hints, which shorten the render-blocking
     HTML -> style.css -> fonts.googleapis.com chain;
  3. VideoObject JSON-LD for pages carrying a YouTube episode embed, so the
     video is more than an opaque <iframe> to a crawler.

It also repairs meta descriptions whose text contains a raw double quote. Those
terminate the HTML attribute early, silently truncating the description search
engines read (and, downstream, the visible "Short answer" box that
retrofit_author_aeo.py sources from it).

The same markup is emitted by generate_episode_post.py for new articles; the
shared fragments live in episode_blocks.py so the two paths can't drift.

Idempotent: every step is keyed on a marker and skipped if already present.

Usage: python scripts/retrofit_page_head.py [--dry-run]
"""
import html as htmlmod
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import episode_blocks  # noqa: E402

_STYLESHEET = re.compile(r'^ *<link rel="stylesheet" href="[^"]*style\.css">\n', re.M)
_FAVICON = re.compile(r'^ *<link rel="icon" href="/favicon\.ico"[^>]*>\n', re.M)
_EMBED_ID = re.compile(r'src="https://www\.youtube\.com/embed/([\w-]+)"')

# The meta tags whose content is the article description, in the order the
# template emits them. A raw " in the text breaks all of them identically.
_DESC_TAGS = ('name="description"', 'property="og:description"',
              'name="twitter:description"')


def _fix_broken_desc(src):
    """Re-escape a description attribute that was terminated early by a raw ".

    The signature is a meta tag whose content attribute closes and is followed
    by leftover prose instead of `>`. The full text is recoverable from the
    Article JSON-LD, where json.dumps escaped it correctly.
    """
    m = re.search(r'"description": "((?:[^"\\]|\\.)*)"', src)
    if not m:
        return src, False
    full = json_unescape(m.group(1))
    if '"' not in full:
        return src, False
    fixed = False
    for tag in _DESC_TAGS:
        # Match the whole malformed tag: content=" ... up to the line's end >
        pat = re.compile(r'<meta ' + re.escape(tag) + r' content="[^\n]*">')
        mm = pat.search(src)
        if not mm:
            continue
        good = f'<meta {tag} content="{htmlmod.escape(full, quote=True)}">'
        if mm.group(0) != good:
            src = src.replace(mm.group(0), good, 1)
            fixed = True
    # The visible Short answer box was rendered from the truncated attribute.
    if fixed:
        src = _resync_tldr(src, full)
    return src, fixed


def json_unescape(raw):
    """Undo the JSON string escaping in a JSON-LD value."""
    import json
    return json.loads(f'"{raw}"')


def _resync_tldr(src, text):
    """Repair a Short answer box that was truncated from a broken description.

    Only fires when the box's current text is a strict prefix of the full
    description, which is the signature of having been copied from the
    truncated attribute. Short answers are now written independently of the
    meta description (see backfill_short_answers.py), so anything else in that
    box is deliberate and must not be overwritten.
    """
    pat = re.compile(
        r'(' + re.escape(episode_blocks.TLDR_MARKER) +
        r'.*?<p style="font-size: 1\.1rem; line-height: 1\.6; margin: 0;">)'
        r'(.*?)(</p>)', re.S)
    m = pat.search(src)
    if not m:
        return src
    current = htmlmod.unescape(m.group(2)).strip()
    full = text.strip()
    if current == full or not full.startswith(current):
        return src
    return (src[:m.start()] + m.group(1) + htmlmod.escape(full) + m.group(3)
            + src[m.end():])


def retrofit(page, dry_run):
    src = page.read_text(encoding='utf-8')
    actions = []

    # 1. Repair a description broken by an unescaped double quote
    src, fixed = _fix_broken_desc(src)
    if fixed:
        actions.append('escaped-description')

    # 2. GA4 (immediately above the stylesheet link, as on index.html)
    if 'googletagmanager' not in src:
        m = _STYLESHEET.search(src)
        if not m:
            return 'SKIPPED: no stylesheet link to anchor the analytics snippet'
        src = src[:m.start()] + episode_blocks.ANALYTICS_SNIPPET + src[m.start():]
        actions.append('analytics')

    # 3. Font preconnect hints + direct font stylesheet (above the favicon
    #    links). Inserted line by line so a page that already has the
    #    preconnects from an earlier run still picks up the stylesheet link.
    missing = [ln for ln in episode_blocks.FONT_PRECONNECT.splitlines(keepends=True)
               if ln.strip() not in src]
    if missing:
        m = _FAVICON.search(src)
        if not m:
            return 'SKIPPED: no favicon link to anchor the font hints'
        src = src[:m.start()] + ''.join(missing) + src[m.start():]
        actions.append('font-hints')

    # 4. VideoObject schema for pages with an episode embed
    if episode_blocks.VIDEO_JSONLD_MARKER not in src:
        m = _EMBED_ID.search(src)
        if m:
            block = _video_block_for(src, m.group(1), page.stem)
            if block is None:
                return 'SKIPPED: embed found but page metadata incomplete'
            src = src.replace('</head>', block + '</head>', 1)
            actions.append('video-schema')

    if not actions:
        return 'already done'
    if not dry_run:
        page.write_text(src, encoding='utf-8')
    return 'added ' + ', '.join(actions)


def _video_block_for(src, video_id, slug):
    """Build the VideoObject block from the page's own existing metadata."""
    title = re.search(r'"@type": "PodcastEpisode",\s*\n\s*"name": "((?:[^"\\]|\\.)*)"', src)
    date = re.search(r'"datePublished": "([\d-]{10})"', src)
    desc = re.search(r'"description": "((?:[^"\\]|\\.)*)"', src)
    if not (title and date and desc):
        return None
    return episode_blocks.render_video_jsonld(
        video_id, json_unescape(title.group(1)), date.group(1),
        json_unescape(desc.group(1)), slug)


def main():
    dry_run = '--dry-run' in sys.argv
    pages = ([Path('index.html')]
             + sorted(Path('podcast').glob('*.html'))
             + sorted(Path('podcast/topics').glob('*.html')))
    skipped = 0
    for page in pages:
        result = retrofit(page, dry_run)
        if result.startswith('SKIPPED'):
            skipped += 1
        print(f'  {page.as_posix()}: {result}')
    print(f'\nDone{" (dry run, nothing written)" if dry_run else ""}. '
          f'{skipped} page(s) skipped.')


if __name__ == '__main__':
    main()
