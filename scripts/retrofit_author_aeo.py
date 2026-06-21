"""Retrofit the answer-engine-optimization blocks onto existing episode pages.

For each podcast/*.html page this adds, when missing:
  1. a visible "Short answer" box at the top, sourced from the page's own meta
     description (already an answer-shaped sentence);
  2. an "About the author" E-E-A-T block at the foot;
  3. the enriched author/publisher entity (with @id) in the Article JSON-LD.

All three are also emitted by generate_episode_post.py for new articles; the
shared markup lives in episode_blocks.py so the two paths can't drift.

Idempotent: each block is keyed on a marker (or, for the schema, on the @id)
and skipped if already present. Safe to re-run.

Usage: python scripts/retrofit_author_aeo.py [--dry-run]
"""
import html as htmlmod
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import episode_blocks  # noqa: E402

# The thin author/publisher objects originally baked into every article page.
_OLD_OBJ = re.compile(
    r'"(author|publisher)": \{\s*'
    r'"@type": "Person",\s*'
    r'"name": "F\. Perry Wilson",\s*'
    r'"url": "https://fperrywilson\.com"\s*\}'
)

# Insertion anchors in the page template.
_BODY_DIV = '    <div style="font-size: 1.08rem; line-height: 1.85;">'
_NAV_DIV = '    <div id="episode-nav"'


def _enrich_schema(src):
    def repl(m):
        role = m.group(1)
        obj = episode_blocks.author_jsonld() if role == 'author' else episode_blocks.publisher_jsonld()
        return f'"{role}": {episode_blocks.indent_json(obj, 4)}'
    return _OLD_OBJ.sub(repl, src)


def retrofit(page, dry_run):
    src = page.read_text(encoding='utf-8')
    actions = []

    # 1. Short-answer box (sourced from the page's meta description)
    if episode_blocks.TLDR_MARKER not in src:
        m = re.search(r'<meta name="description" content="([^"]*)"', src)
        if not m:
            return 'SKIPPED: no meta description to source the Short answer box'
        if _BODY_DIV not in src:
            return 'SKIPPED: article body div not in expected form'
        tldr = episode_blocks.render_tldr(htmlmod.unescape(m.group(1)))
        src = src.replace(_BODY_DIV, tldr + _BODY_DIV, 1)
        actions.append('tldr')

    # 2. Author bio block (before the episode nav)
    if episode_blocks.AUTHOR_BIO_MARKER not in src:
        if _NAV_DIV not in src:
            return 'SKIPPED: episode-nav div not found'
        src = src.replace(_NAV_DIV, episode_blocks.render_author_bio() + _NAV_DIV, 1)
        actions.append('author-bio')

    # 3. Enriched author/publisher schema
    if f'"@id": "{episode_blocks.PERSON_ID}"' not in src:
        new_src = _enrich_schema(src)
        if new_src != src:
            src = new_src
            actions.append('schema')

    if not actions:
        return 'already done'
    if not dry_run:
        page.write_text(src, encoding='utf-8')
    return 'added ' + ', '.join(actions)


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
