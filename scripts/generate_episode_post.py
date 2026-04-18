"""
Generate a standalone SEO article from a Wellness, Actually podcast transcript.

Usage: python scripts/generate_episode_post.py transcripts/YYYY-MM-DD-topic.txt
"""

import anthropic
import sys
import os
import json
import re
from datetime import datetime
from pathlib import Path


def parse_date_from_filename(stem):
    """Extract date from filename like 2026-04-02-creatine, fallback to today."""
    parts = stem.split('-')
    if len(parts) >= 3:
        try:
            date = datetime.strptime('-'.join(parts[:3]), '%Y-%m-%d')
            return date.strftime('%Y-%m-%d'), date.strftime('%B %-d, %Y')
        except ValueError:
            pass
    today = datetime.now()
    return today.strftime('%Y-%m-%d'), today.strftime('%B %-d, %Y')


def call_claude(transcript_text):
    client = anthropic.Anthropic()

    system = """You are ghostwriting for Dr. F. Perry Wilson — nephrologist, Yale professor, and science communicator. He writes the weekly "Impact Factor" column on Medscape and his goal is: rigorous analysis, delivered accessibly.

His voice on the page:
- Direct and plain-spoken. Short sentences. He doesn't build to a point — he makes it, then supports it.
- Wry but not jokey. Occasional dry aside, never a punchline.
- Confident without being arrogant. He'll say "the evidence is weak" without hedging it into mush.
- Uses "you" and "I" naturally. Talks to the reader like an intelligent adult, not a patient.
- Cites numbers and study details when they matter. Skips them when they don't.

Hard rules on style:
- No em-dashes. Use a comma, a period, or rewrite the sentence.
- No AI filler phrases: "it's worth noting," "delve into," "in conclusion," "it's important to remember," "navigate," "the good news is," "the bottom line is" (as an opener), "at the end of the day."
- No rhetorical questions as subheadings.
- No bullet-pointed "takeaways" lists unless the content genuinely calls for it.
- Vary sentence length. A short sentence after a longer one lands harder.
- Never use the word "boundaries."

His articles are grounded strictly in evidence from the source material. Don't add outside claims."""

    user = f"""From the transcript below, extract ONLY the "What's the deal with" deep-dive segment and ignore all other segments (health news, listener Q&A, intros/outros).

Then write a standalone article with this structure:
1. SEO headline (how someone would Google this topic, e.g. "Does creatine actually work?")
2. Opening hook (1-2 sentences that establish why this matters)
3. Body with 2-4 H2 subheadings covering the key evidence and nuance
4. "Bottom line" section summarizing the takeaway
5. A single closing sentence (not a section) that naturally leads into: "I covered this in depth on Wellness, Actually — listen below."

Call the create_article tool with your result.

TRANSCRIPT:
{transcript_text}"""

    tools = [
        {
            "name": "create_article",
            "description": "Publish the generated SEO article for the episode",
            "input_schema": {
                "type": "object",
                "properties": {
                    "headline": {
                        "type": "string",
                        "description": "SEO-optimized headline (how someone would Google this topic)"
                    },
                    "slug": {
                        "type": "string",
                        "description": "URL-friendly slug, e.g. does-creatine-actually-work"
                    },
                    "meta_description": {
                        "type": "string",
                        "description": "150-160 character meta description for search results"
                    },
                    "episode_title": {
                        "type": "string",
                        "description": "Podcast episode title, e.g. What's the deal with creatine?"
                    },
                    "article_html": {
                        "type": "string",
                        "description": "Full article body HTML using only <p> <h2> <ul> <ol> <li> <strong> <em> tags"
                    }
                },
                "required": ["headline", "slug", "meta_description", "episode_title", "article_html"]
            }
        }
    ]

    message = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=4096,
        system=system,
        tools=tools,
        tool_choice={"type": "tool", "name": "create_article"},
        messages=[{"role": "user", "content": user}],
    )

    for block in message.content:
        if block.type == "tool_use":
            return block.input

    raise RuntimeError("Claude did not call create_article tool")


def build_episode_html(data, date_iso, date_display):
    headline = data['headline']
    slug = data['slug']
    meta_desc = data['meta_description']
    article_html = data['article_html']
    episode_title = data['episode_title']

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{headline} | F. Perry Wilson, MD</title>
  <meta name="description" content="{meta_desc}">
  <meta name="author" content="F. Perry Wilson">
  <link rel="stylesheet" href="../css/style.css">
  <link rel="canonical" href="https://fperrywilson.com/podcast/{slug}.html">
  <meta property="og:title" content="{headline}">
  <meta property="og:description" content="{meta_desc}">
  <meta property="og:type" content="article">
  <meta property="og:url" content="https://fperrywilson.com/podcast/{slug}.html">
  <meta property="og:image" content="https://fperrywilson.com/images/wellness%20actually%20cover.png">
  <meta property="article:published_time" content="{date_iso}">
  <meta property="article:author" content="https://fperrywilson.com">
  <meta property="article:section" content="Health">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:site" content="@fperrywilson">
  <meta name="twitter:title" content="{headline}">
  <meta name="twitter:description" content="{meta_desc}">
  <meta name="twitter:image" content="https://fperrywilson.com/images/wellness%20actually%20cover.png">
  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "Article",
    "headline": "{headline}",
    "datePublished": "{date_iso}",
    "dateModified": "{date_iso}",
    "image": "https://fperrywilson.com/images/wellness%20actually%20cover.png",
    "author": {{
      "@type": "Person",
      "name": "F. Perry Wilson",
      "url": "https://fperrywilson.com"
    }},
    "publisher": {{
      "@type": "Person",
      "name": "F. Perry Wilson",
      "url": "https://fperrywilson.com"
    }},
    "description": "{meta_desc}",
    "url": "https://fperrywilson.com/podcast/{slug}.html"
  }}
  </script>
  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    "itemListElement": [
      {{"@type": "ListItem", "position": 1, "name": "Home", "item": "https://fperrywilson.com"}},
      {{"@type": "ListItem", "position": 2, "name": "Episode Articles", "item": "https://fperrywilson.com/podcast/"}},
      {{"@type": "ListItem", "position": 3, "name": "{headline}", "item": "https://fperrywilson.com/podcast/{slug}.html"}}
    ]
  }}
  </script>
</head>
<body>

  <nav class="nav" id="nav">
    <div class="nav-inner">
      <a href="/" class="nav-logo">F. Perry Wilson<span>,</span> MD</a>
      <ul class="nav-links" id="navLinks">
        <li><a href="/#about">About</a></li>
        <li><a href="/#podcast">Podcast</a></li>
        <li><a href="/podcast/">Articles</a></li>
        <li><a href="/#book">Book</a></li>
        <li><a href="/#writing">Writing</a></li>
        <li><a href="/#media">Media</a></li>
        <li><a href="/#lab">Lab</a></li>
      </ul>
      <button class="nav-toggle" id="navToggle" aria-label="Toggle navigation">
        <span></span><span></span><span></span>
      </button>
    </div>
  </nav>

  <article style="max-width: 740px; margin: 100px auto 80px; padding: 0 24px;">

    <p style="font-family: var(--font-mono); font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.1em; color: var(--color-muted); margin-bottom: 12px;">
      <a href="/podcast/" style="color: var(--color-muted); text-decoration: none;">Wellness, Actually</a>&nbsp;&nbsp;·&nbsp;&nbsp;{date_display}
    </p>

    <h1 style="font-family: var(--font-display); font-size: clamp(1.8rem, 4vw, 2.8rem); line-height: 1.15; margin-bottom: 20px;">{headline}</h1>

    <p style="font-family: var(--font-mono); font-size: 0.8rem; color: var(--color-muted); text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 48px; padding-bottom: 24px; border-bottom: 1px solid #e0d9d0;">
      By <a href="/" style="color: var(--color-muted);">F. Perry Wilson, MD MSCE</a>
    </p>

    <div style="font-size: 1.08rem; line-height: 1.85;">
      {article_html}
    </div>

    <div style="margin-top: 56px; padding: 32px; background: #f3ede6; border-left: 4px solid var(--color-accent); border-radius: 0 4px 4px 0;">
      <p style="font-family: var(--font-mono); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.12em; color: var(--color-accent); margin-bottom: 8px;">Wellness, Actually Podcast</p>
      <p style="font-size: 1.05rem; margin-bottom: 20px;"><strong>"{episode_title}"</strong> — Listen to the full episode, including the week's health news and listener Q&amp;A.</p>
      <div style="display: flex; gap: 12px; flex-wrap: wrap;">
        <a href="https://podcasts.apple.com/us/podcast/wellness-actually-with-emily-oster-perry-wilson-md/id1633515294" target="_blank" rel="noopener noreferrer" class="btn btn-primary">Apple Podcasts</a>
        <a href="https://open.spotify.com/show/5igTryEwHMmAJfODAFKp3W" target="_blank" rel="noopener noreferrer" class="btn btn-outline">Spotify</a>
        <a href="https://www.iheart.com/podcast/1119-wellness-actually-with-em-99325147/" target="_blank" rel="noopener noreferrer" class="btn btn-outline">iHeart</a>
      </div>
    </div>

    <div id="episode-nav" style="margin-top: 40px; padding-top: 24px; border-top: 1px solid #e0d9d0; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;"></div>

  </article>

  <footer class="footer">
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
  </footer>

  <script>
    const nav = document.getElementById('nav');
    window.addEventListener('scroll', () => nav.classList.toggle('scrolled', window.scrollY > 20));
    const navToggle = document.getElementById('navToggle');
    const navLinks = document.getElementById('navLinks');
    navToggle.addEventListener('click', () => navLinks.classList.toggle('open'));
    navLinks.querySelectorAll('a').forEach(l => l.addEventListener('click', () => navLinks.classList.remove('open')));
  </script>
  <script src="../js/episodes.js"></script>

</body>
</html>
"""


def update_podcast_index(slug, headline, date_iso, date_display, meta_desc):
    index_path = Path('podcast/index.html')
    if not index_path.exists():
        return

    content = index_path.read_text(encoding='utf-8')

    # Extract existing entries between <!-- EPISODES-START --> and the next blank line / closing tag
    entry_pattern = re.compile(
        r'      <div class="media-item">.*?</div>\n      </div>\n',
        re.DOTALL
    )
    existing_entries = entry_pattern.findall(content)

    # Remove all existing entries from content
    for entry in existing_entries:
        content = content.replace(entry, '')

    # Build new entry
    new_entry = f"""      <div class="media-item" data-date="{date_iso}">
        <span class="media-date">{date_display}</span>
        <div>
          <div class="media-outlet"><a href="/podcast/{slug}.html">{headline}</a></div>
          <p class="media-description">{meta_desc}</p>
        </div>
      </div>
"""

    # Migrate any existing entries that lack data-date by extracting date from media-date span
    all_entries = existing_entries + [new_entry]
    def entry_date(entry):
        m = re.search(r'data-date="([\d-]+)"', entry)
        if m:
            return m.group(1)
        m = re.search(r'<span class="media-date">([^<]+)</span>', entry)
        if m:
            try:
                return datetime.strptime(m.group(1).strip(), '%B %d, %Y').strftime('%Y-%m-%d')
            except ValueError:
                pass
        return '0000-00-00'

    all_entries.sort(key=entry_date, reverse=True)

    sorted_block = ''.join(all_entries)
    content = content.replace('<!-- EPISODES-START -->', f'<!-- EPISODES-START -->\n{sorted_block}')
    index_path.write_text(content, encoding='utf-8')


def update_episodes_js(slug, headline):
    """Append new episode to js/episodes.js EPISODES array (oldest-first order)."""
    js_path = Path('js/episodes.js')
    if not js_path.exists():
        return

    # Derive a short nav title: strip trailing punctuation detail after "?"
    nav_title = headline
    content = js_path.read_text(encoding='utf-8')

    # Don't add if already present
    if f"'{slug}'" in content or f'"{slug}"' in content:
        return

    new_entry = f"    {{ slug: '{slug}', title: '{nav_title}' }},\n"
    content = re.sub(r'(\n  \];\n\n  const linkStyle)', f'\n{new_entry}\\1', content)
    js_path.write_text(content, encoding='utf-8')


def update_sitemap(slug, date_iso):
    sitemap_path = Path('sitemap.xml')
    content = sitemap_path.read_text(encoding='utf-8')
    new_entry = f"""  <url>
    <loc>https://fperrywilson.com/podcast/{slug}.html</loc>
    <lastmod>{date_iso}</lastmod>
    <changefreq>never</changefreq>
    <priority>0.7</priority>
  </url>
"""
    content = content.replace('</urlset>', f'{new_entry}</urlset>')
    sitemap_path.write_text(content, encoding='utf-8')


def set_output(name, value):
    """Write a GitHub Actions step output."""
    output_file = os.environ.get('GITHUB_OUTPUT')
    if output_file:
        with open(output_file, 'a') as f:
            f.write(f"{name}={value}\n")
    else:
        print(f"Output: {name}={value}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/generate_episode_post.py <transcript_path>")
        sys.exit(1)

    transcript_path = Path(sys.argv[1])
    print(f"Reading transcript: {transcript_path}")

    transcript_text = transcript_path.read_text(encoding='utf-8')
    date_iso, date_display = parse_date_from_filename(transcript_path.stem)

    print("Calling Claude to generate article...")
    data = call_claude(transcript_text)

    slug = data['slug']
    headline = data['headline']
    print(f"Generated: '{headline}' → podcast/{slug}.html")

    # Write episode page
    episode_html = build_episode_html(data, date_iso, date_display)
    output_path = Path(f'podcast/{slug}.html')
    output_path.parent.mkdir(exist_ok=True)
    output_path.write_text(episode_html, encoding='utf-8')
    print(f"Written: {output_path}")

    # Update index, sitemap, and episodes nav
    update_podcast_index(slug, headline, date_iso, date_display, data['meta_description'])
    update_sitemap(slug, date_iso)
    update_episodes_js(slug, headline)
    print("Updated podcast/index.html, sitemap.xml, and js/episodes.js")

    set_output('slug', slug)
    set_output('headline', headline)


if __name__ == '__main__':
    main()
