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

    system = """You are a medical content writer helping Dr. F. Perry Wilson (nephrologist, Yale University, science communicator) publish evidence-based health articles. Dr. Wilson co-hosts the "Wellness, Actually" podcast with economist Emily Oster. The podcast has a recurring segment called "What's the deal with [topic]" — a deep dive into a specific health or wellness subject.

Your job is to transform the deep-dive segment of a podcast transcript into a compelling, standalone article for Dr. Wilson's website. The article must:
- Read as authoritative first-person health journalism, NOT a podcast recap
- Never mention the podcast conversation, Emily Oster, or "we discussed"
- Be grounded strictly in claims and evidence from the transcript — don't add outside claims
- Be optimized for how people actually search (question-style or plain-English headlines)
- Be written in Dr. Wilson's voice: rigorous but accessible, plain-spoken, occasionally wry"""

    user = f"""From the transcript below, extract ONLY the "What's the deal with" deep-dive segment and ignore all other segments (health news, listener Q&A, intros/outros).

Then write a standalone article with this structure:
1. SEO headline (how someone would Google this topic, e.g. "Does creatine actually work?")
2. Opening hook (1-2 sentences that establish why this matters)
3. Body with 2-4 H2 subheadings covering the key evidence and nuance
4. "Bottom line" section summarizing the takeaway
5. A single closing sentence (not a section) that naturally leads into: "I covered this in depth on Wellness, Actually — listen below."

Return ONLY a JSON object with these exact fields (no markdown fences, no extra text):
{{
  "headline": "SEO-optimized article headline",
  "slug": "url-friendly-slug",
  "meta_description": "150-160 character meta description for search results",
  "episode_title": "The podcast episode title as it would appear (e.g. What's the deal with creatine?)",
  "article_html": "Full article body HTML using only <p> <h2> <ul> <ol> <li> <strong> <em> tags"
}}

TRANSCRIPT:
{transcript_text}"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user}],
    )

    raw = message.content[0].text.strip()

    # Strip markdown fences if Claude wrapped the JSON anyway
    fence_match = re.search(r'```(?:json)?\s*(.*?)\s*```', raw, re.DOTALL)
    if fence_match:
        raw = fence_match.group(1)

    return json.loads(raw)


def build_episode_html(data, date_iso, date_display):
    headline = data['headline']
    slug = data['slug']
    meta_desc = data['meta_description']
    article_html = data['article_html']
    episode_title = data['episode_title']

    # Escape curly braces in JSON-LD to avoid Python format issues
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
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:site" content="@fperrywilson">
  <meta name="twitter:title" content="{headline}">
  <meta name="twitter:description" content="{meta_desc}">
  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "Article",
    "headline": "{headline}",
    "datePublished": "{date_iso}",
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

    <div style="margin-top: 40px; padding-top: 24px; border-top: 1px solid #e0d9d0;">
      <a href="/podcast/" style="font-family: var(--font-mono); font-size: 0.85rem; color: var(--color-accent); text-decoration: none;">← All episode articles</a>
    </div>

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

</body>
</html>
"""


def update_podcast_index(slug, headline, date_iso, date_display, meta_desc):
    index_path = Path('podcast/index.html')
    if not index_path.exists():
        return  # Created separately; shouldn't be missing

    content = index_path.read_text(encoding='utf-8')
    new_entry = f"""      <div class="media-item">
        <span class="media-date">{date_display}</span>
        <div>
          <div class="media-outlet"><a href="/podcast/{slug}.html">{headline}</a></div>
          <p class="media-description">{meta_desc}</p>
        </div>
      </div>
"""
    content = content.replace('<!-- EPISODES-START -->', f'<!-- EPISODES-START -->\n{new_entry}')
    index_path.write_text(content, encoding='utf-8')


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

    # Update index and sitemap
    update_podcast_index(slug, headline, date_iso, date_display, data['meta_description'])
    update_sitemap(slug, date_iso)
    print("Updated podcast/index.html and sitemap.xml")

    set_output('slug', slug)
    set_output('headline', headline)


if __name__ == '__main__':
    main()
