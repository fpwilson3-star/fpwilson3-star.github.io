"""Retrofit the SEO/AEO Article fields onto existing episode pages.

Rebuilds each page's Article JSON-LD through the shared
episode_blocks.render_article_block() so the following are present and correct:
  - isPartOf / mainEntityOfPage / inLanguage (collection membership, canonical
    page, language);
  - citation: the vetted study links in the article body, restated as
    schema.org sources.

The existing headline, datePublished, dateModified, and description are read
back out of the current Article block and preserved, so a page whose
dateModified was bumped for a manual edit keeps that date.

Idempotent: a page already carrying the exact rebuilt block is left untouched.
Safe to re-run. Both this and generate_episode_post.py render through the same
shared builder, so the two paths can't drift.

Usage: python scripts/retrofit_article_seo.py [--dry-run]
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import episode_blocks  # noqa: E402

SCRIPT_RE = re.compile(r'  <script type="application/ld\+json">\n(.*?)\n  </script>', re.DOTALL)


def retrofit(page, dry_run):
    src = page.read_text(encoding='utf-8')

    # Locate the Article JSON-LD block (there are several ld+json blocks).
    target = None
    for m in SCRIPT_RE.finditer(src):
        try:
            block = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if block.get('@type') == 'Article':
            target = (m, block)
            break
    if target is None:
        return 'SKIPPED: no Article JSON-LD block found'

    m, block = target
    slug = page.stem
    date_pub = block.get('datePublished')
    date_mod = block.get('dateModified', date_pub)
    headline = block.get('headline')
    description = block.get('description')
    if not (date_pub and headline and description):
        return 'SKIPPED: Article block missing headline/date/description'

    citations = episode_blocks.extract_citations(episode_blocks.body_region(src))
    new_block = episode_blocks.render_article_block(
        headline, date_pub, date_mod, slug, description, citations)

    if src[m.start():m.end()] == new_block:
        return 'already done'
    new_src = src[:m.start()] + new_block + src[m.end():]
    if not dry_run:
        page.write_text(new_src, encoding='utf-8')
    note = f'{len(citations)} citation(s)' if citations else 'no citations'
    return f'rebuilt Article schema ({note})'


def main():
    dry_run = '--dry-run' in sys.argv
    skipped = 0
    for page in sorted(Path('podcast').glob('*.html')):
        if page.stem == 'index':
            continue
        result = retrofit(page, dry_run)
        if result.startswith('SKIPPED'):
            skipped += 1
        print(f'  {page.stem}: {result}')
    print(f'\nDone{" (dry run, nothing written)" if dry_run else ""}. {skipped} page(s) skipped.')


if __name__ == '__main__':
    main()
