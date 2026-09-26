"""Render a share card for every episode article and point its tags at it.

Every article used to share images/og-podcast.jpg, so a link to the sweeteners
article looked identical to a link to the ticks article on X, LinkedIn, Slack,
or iMessage, and Google Discover / article rich results had no distinct image
to show. This renders a 1200x630 card per article -- headline on the podcast
cover's teal -- into images/og/<slug>.jpg and rewrites the page's og:image,
twitter:image, image alt text, and Article JSON-LD image to use it.

Deliberately text-only and template-driven (no YouTube thumbnails, no AI art):
the cards are consistent, deterministic, can't misspell a headline, and need no
API key. The font ships in scripts/fonts/ (OFL) so CI renders identically.

Idempotent: a card is re-rendered only when its bytes would change, and a page
is rewritten only when its tags don't already point at its card. The episode
generator runs this after writing a new article; check_site.py fails if any
article lacks its card.

Usage: python scripts/build_og_images.py [--dry-run] [--sample SLUG OUT.jpg]
"""
import html as htmlmod
import io
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent))
import episode_blocks  # noqa: E402

SITE = 'https://fperrywilson.com'
OG_DIR = Path('images/og')
FONT = Path(__file__).parent / 'fonts' / 'Outfit.ttf'

W, H = 1200, 630
MARGIN = 80
TEAL = (0x1f, 0x6f, 0x78)       # sampled from the podcast cover art
WHITE = (255, 255, 255)
SOFT = (0xbf, 0xda, 0xdc)       # white at ~70% over the teal
RULE = (0x4c, 0x8c, 0x93)

# Headline sizes to try, largest first; the first that fits in MAX_LINES wins.
HEADLINE_SIZES = (78, 72, 66, 60, 54, 50)
MAX_LINES = 4


def font(size, weight):
    f = ImageFont.truetype(str(FONT), size)
    f.set_variation_by_name(weight)
    return f


def wrap(draw, text, f, width):
    lines, line = [], ''
    for word in text.split():
        trial = f'{line} {word}'.strip()
        if draw.textlength(trial, font=f) <= width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def render_card(headline):
    img = Image.new('RGB', (W, H), TEAL)
    d = ImageDraw.Draw(img)

    # Top: show name, as a small letter-spaced label.
    label = font(26, 'SemiBold')
    x = MARGIN
    for ch in 'WELLNESS, ACTUALLY':
        d.text((x, MARGIN - 8), ch, font=label, fill=WHITE)
        x += d.textlength(ch, font=label) + 3.5
    d.line([(MARGIN, MARGIN + 36), (MARGIN + 64, MARGIN + 36)], fill=WHITE, width=4)

    # Bottom: byline and domain.
    foot = font(28, 'Medium')
    foot_y = H - MARGIN - 24
    d.line([(MARGIN, foot_y - 28), (W - MARGIN, foot_y - 28)], fill=RULE, width=2)
    d.text((MARGIN, foot_y), 'F. Perry Wilson, MD', font=foot, fill=WHITE)
    domain = 'fperrywilson.com'
    d.text((W - MARGIN - d.textlength(domain, font=foot), foot_y), domain,
           font=foot, fill=SOFT)

    # Middle: the headline, as large as fits, vertically centred in the space
    # between the label and the footer rule.
    top, bottom = MARGIN + 70, foot_y - 56
    for size in HEADLINE_SIZES:
        f = font(size, 'Bold')
        lines = wrap(d, headline, f, W - 2 * MARGIN)
        line_h = round(size * 1.12)
        if len(lines) <= MAX_LINES and len(lines) * line_h <= bottom - top:
            break
    y = top + (bottom - top - len(lines) * line_h) // 2
    for line in lines:
        d.text((MARGIN, y), line, font=f, fill=WHITE)
        y += line_h

    buf = io.BytesIO()
    img.save(buf, 'JPEG', quality=88, optimize=True, progressive=True)
    return buf.getvalue()


def article_pages():
    """(slug, path) for every episode article, from the validated index."""
    src = Path('podcast/index.html').read_text(encoding='utf-8')
    slugs = re.findall(r'<div class="media-outlet"><a href="/podcast/([^"]+)\.html">', src)
    return [(s, Path(f'podcast/{s}.html')) for s in slugs]


def headline_of(page_src):
    m = re.search(r'<h1[^>]*>(.*?)</h1>', page_src, re.DOTALL)
    return htmlmod.unescape(re.sub(r'<[^>]+>', '', m.group(1))).strip()


def retarget_tags(src, slug, headline):
    url = episode_blocks.og_image_url(slug)
    alt = htmlmod.escape(episode_blocks.og_image_alt(headline), quote=True)
    src = re.sub(r'(<meta property="og:image" content=")[^"]*(")', rf'\g<1>{url}\2', src)
    src = re.sub(r'(<meta name="twitter:image" content=")[^"]*(")', rf'\g<1>{url}\2', src)
    src = re.sub(r'(<meta property="og:image:alt" content=")[^"]*(")', lambda m: m.group(1) + alt + m.group(2), src)
    src = re.sub(r'(<meta name="twitter:image:alt" content=")[^"]*(")', lambda m: m.group(1) + alt + m.group(2), src)
    # The Article JSON-LD image. Only the og-podcast default or a prior card is
    # replaced, so a VideoObject thumbnailUrl is never touched.
    src = re.sub(r'("image": ")' + re.escape(SITE) + r'/images/(?:og-podcast\.jpg|og/[^"]+\.jpg)(")',
                 rf'\g<1>{url}\2', src)
    return src


def build(dry_run=False):
    OG_DIR.mkdir(parents=True, exist_ok=True)
    cards = pages = 0
    for slug, path in article_pages():
        src = path.read_text(encoding='utf-8')
        headline = headline_of(src)
        card, jpg = OG_DIR / f'{slug}.jpg', render_card(headline)
        if not card.exists() or card.read_bytes() != jpg:
            cards += 1
            if not dry_run:
                card.write_bytes(jpg)
        new = retarget_tags(src, slug, headline)
        if new != src:
            pages += 1
            if not dry_run:
                path.write_text(new, encoding='utf-8')
    print(f'og cards: {cards} rendered, {pages} page(s) retargeted'
          f'{" [dry run]" if dry_run else ""}')


def main():
    if '--sample' in sys.argv:
        i = sys.argv.index('--sample')
        slug, out = sys.argv[i + 1], sys.argv[i + 2]
        src = Path(f'podcast/{slug}.html').read_text(encoding='utf-8')
        Path(out).write_bytes(render_card(headline_of(src)))
        print(f'wrote {out}')
        return
    build(dry_run='--dry-run' in sys.argv)


if __name__ == '__main__':
    main()
