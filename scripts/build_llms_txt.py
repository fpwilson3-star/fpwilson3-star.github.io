"""Regenerate /llms.txt from the site's content.

llms.txt (see llmstxt.org) is a plain-markdown map of the site for large
language models and answer engines: a title, a one-line summary, then curated
sections of links. The static top matter describes who Dr. Wilson is; the
episode list is generated from podcast/index.html (reusing build_rss's parser)
so it stays in lockstep with the articles, the RSS feed, and the sitemap.

Usage: python scripts/build_llms_txt.py
"""
from pathlib import Path

import build_rss

HEADER = """# F. Perry Wilson, MD MSCE

> Yale physician, clinical researcher, and science communicator. Director of the Clinical and Translational Research Accelerator (CTRA) at Yale. Host of the Wellness, Actually podcast with Emily Oster and author of How Medicine Works and When It Doesn't.

F. Perry Wilson is a nephrologist and Associate Professor of Medicine and Public Health at Yale University. His work focuses on separating medical fact from fiction through rigorous analysis of the evidence. This site collects his evidence-based podcast episode articles, his book, his popular writing, media appearances, research, and teaching.

## Main pages
- [About F. Perry Wilson](https://fperrywilson.com/#about): Bio, credentials (Harvard College, Columbia P&S, Penn), and board certifications in internal medicine and nephrology.
- [Wellness, Actually podcast](https://fperrywilson.com/#podcast): Weekly evidence-based wellness podcast co-hosted with economist Emily Oster, distributed by iHeartMedia.
- [How Medicine Works and When It Doesn't](https://fperrywilson.com/#book): His 2023 book (Grand Central Publishing) on evaluating medical claims and knowing who to trust.
- [Understanding Medical Research (Coursera)](https://www.coursera.org/learn/medical-research): Free Yale course on how to critically evaluate medical studies.
- [CTRA at Yale](https://medicine.yale.edu/internal-medicine/ctra/): The clinical and translational research lab he directs.

## Episode articles
Evidence-based deep dives, one per podcast episode. Each answers a specific wellness question with what the research actually shows.
"""

FOOTER = """
## Indexes
- [All episode articles](https://fperrywilson.com/podcast/)
- [Episode article RSS feed](https://fperrywilson.com/podcast/rss.xml)
- [Sitemap](https://fperrywilson.com/sitemap.xml)
"""


def build(entries):
    lines = [f"- [{e['title']}]({e['url']}): {e['description']}" for e in entries]
    return HEADER + '\n'.join(lines) + '\n' + FOOTER


def main():
    entries = build_rss.parse_entries()  # newest-first [{date, url, title, description}]
    out = Path('llms.txt')
    out.write_text(build(entries), encoding='utf-8')
    print(f'Wrote {out} with {len(entries)} episode articles')


if __name__ == '__main__':
    main()
