"""
Generate a standalone SEO article from a Wellness, Actually podcast transcript.

Usage: python scripts/generate_episode_post.py transcripts/YYYY-MM-DD-topic.txt
"""

import anthropic
import sys
import os
import json
import re
import html as htmlmod
from datetime import datetime
from pathlib import Path


EPISODES_FOLDER_ID = '1qhx8vF3m6Gd9eYUEntLoeAtaVgZ7N-Si'


def parse_date_from_filename(stem):
    """Extract date from filename like 2026-04-02-creatine or 05-14-26-psychedelics, fallback to today."""
    parts = stem.split('-')
    if len(parts) >= 3:
        # Try YYYY-MM-DD first (e.g. 2026-04-02-creatine)
        try:
            date = datetime.strptime('-'.join(parts[:3]), '%Y-%m-%d')
            return date.strftime('%Y-%m-%d'), date.strftime('%B %-d, %Y')
        except ValueError:
            pass
        # Try MM-DD-YY (e.g. 05-14-26-psychedelics)
        try:
            date = datetime.strptime('-'.join(parts[:3]), '%m-%d-%y')
            return date.strftime('%Y-%m-%d'), date.strftime('%B %-d, %Y')
        except ValueError:
            pass
    today = datetime.now()
    return today.strftime('%Y-%m-%d'), today.strftime('%B %-d, %Y')


def derive_drive_search_terms(stem):
    """
    From a transcript filename stem, return (date_string, topic_word) for Drive search.
    Folder names look like '14. 5.14.26 - Psychedelics' so date format is M.D.YY (no leading zeros).
    """
    parts = stem.split('-')
    date_str = None
    topic = None
    if len(parts) >= 4:
        # MM-DD-YY-topic
        try:
            mm, dd, yy = int(parts[0]), int(parts[1]), int(parts[2])
            if mm <= 12 and dd <= 31:
                date_str = f"{mm}.{dd}.{yy:02d}"
                topic = parts[3]
        except ValueError:
            pass
        # YYYY-MM-DD-topic
        if not topic:
            try:
                date = datetime.strptime('-'.join(parts[:3]), '%Y-%m-%d')
                date_str = f"{date.month}.{date.day}.{date.year % 100:02d}"
                topic = parts[3]
            except ValueError:
                pass
    return date_str, topic


def fetch_drive_script(stem):
    """
    Look up the vetted episode SCRIPT doc in Google Drive and return its plain-text content.
    Returns None on any failure — caller must handle missing script as "no links available."
    """
    creds_json = os.environ.get('GOOGLE_DRIVE_CREDENTIALS')
    if not creds_json:
        print("[drive] GOOGLE_DRIVE_CREDENTIALS not set; skipping Drive fetch.")
        return None

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError as e:
        print(f"[drive] google-api-python-client not installed ({e}); skipping Drive fetch.")
        return None

    date_str, topic = derive_drive_search_terms(stem)
    if not topic and not date_str:
        print(f"[drive] could not derive search terms from filename '{stem}'.")
        return None

    try:
        creds = service_account.Credentials.from_service_account_info(
            json.loads(creds_json),
            scopes=['https://www.googleapis.com/auth/drive.readonly'],
        )
        service = build('drive', 'v3', credentials=creds, cache_discovery=False)

        # Find the episode folder. Try by date first (most precise), then by topic word.
        folder_id = None
        folder_name = None
        for term in filter(None, [date_str, topic]):
            q = (
                f"name contains '{term}' "
                f"and mimeType = 'application/vnd.google-apps.folder' "
                f"and '{EPISODES_FOLDER_ID}' in parents "
                f"and trashed = false"
            )
            results = service.files().list(
                q=q,
                fields='files(id,name)',
                pageSize=10,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute()
            folders = results.get('files', [])
            if folders:
                folder_id = folders[0]['id']
                folder_name = folders[0]['name']
                print(f"[drive] matched episode folder via '{term}': {folder_name}")
                break

        if not folder_id:
            # Distinguish "no access" from "name mismatch": can the SA see ANY episode folder?
            visible = service.files().list(
                q=(
                    f"mimeType = 'application/vnd.google-apps.folder' "
                    f"and '{EPISODES_FOLDER_ID}' in parents and trashed = false"
                ),
                fields='files(id,name)',
                pageSize=5,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            ).execute().get('files', [])
            if not visible:
                print(
                    f"[drive] no episode folder matched date='{date_str}' or topic='{topic}', "
                    f"AND the service account sees ZERO folders under EPISODES "
                    f"({EPISODES_FOLDER_ID}). This is an access problem: grant the service "
                    f"account Viewer on that folder."
                )
            else:
                sample = ', '.join(f['name'] for f in visible)
                print(
                    f"[drive] no episode folder matched date='{date_str}' or topic='{topic}', "
                    f"but the service account CAN see folders (e.g. {sample}). "
                    f"This is a name-match problem, not access."
                )
            return None

        # Find the SCRIPT doc inside that folder.
        q = (
            f"name contains 'SCRIPT' "
            f"and '{folder_id}' in parents "
            f"and trashed = false"
        )
        results = service.files().list(
            q=q,
            fields='files(id,name,mimeType)',
            pageSize=10,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        ).execute()
        scripts = results.get('files', [])
        if not scripts:
            print(f"[drive] no SCRIPT doc found inside '{folder_name}'.")
            return None

        script = scripts[0]
        print(f"[drive] exporting script: {script['name']}")

        # Export Google Doc as plain text. Native binary types would need files().get_media().
        if script['mimeType'] == 'application/vnd.google-apps.document':
            content = service.files().export(
                fileId=script['id'], mimeType='text/plain'
            ).execute()
            # Note: files().export does not accept supportsAllDrives; it works on any
            # file the service account can read, including shared-drive content.
            return content.decode('utf-8') if isinstance(content, bytes) else content
        print(f"[drive] script has unexpected mimeType {script['mimeType']}; skipping.")
        return None

    except Exception as e:
        print(f"[drive] fetch failed: {e}")
        return None


def call_claude(transcript_text, script_text=None):
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

    script_block = ""
    if script_text:
        script_block = f"""

VETTED HYPERLINKS — EPISODE SCRIPT BELOW.
The text below is the show script prepared by the host. It contains pre-sourced URLs for the studies, papers, trials, and clips discussed on the episode. These are the ONLY links you may use.

Rules for hyperlinks:
- Link EVERY study, trial, meta-analysis, or paper the article discusses that has a URL in the script below. Do not stop at one link. Most episodes have several vetted URLs and most should end up in the article. Before finishing, re-scan the script for every URL and confirm you used each applicable one.
- Match each URL to the SPECIFIC study it belongs to in the script. The text immediately around a URL in the script tells you which finding it supports (e.g. a Cochrane link goes on the Cochrane sentence, the runner-study link goes on the runner sentence). Never attach a URL to a different study than the one it documents in the script.
- Link the relevant phrase using a standard HTML anchor: <a href="URL" target="_blank" rel="noopener noreferrer">linked text</a>
- A URL is valid ONLY if that exact string appears verbatim somewhere in the script below. Before you emit any href, find that exact URL in the script text. If you cannot find it character-for-character, do not link at all.
- NEVER build a URL from a journal, publisher, or website name. If the script cites "Journal of Physiotherapy" or "Clinical Journal of Pain" but the adjacent URL is a pubmed.ncbi.nlm.nih.gov link, you MUST use that pubmed link, NOT the journal's homepage. Linking a study to its journal/publisher homepage (e.g. jospt.org, journals.lww.com/.../default.aspx, a frontiersin.org or sciencedirect.com journal landing page) is a fabrication and is forbidden, even if you "know" the journal's website.
- The URL belongs to the SPECIFIC study described in the text right next to it in the script. Most vetted URLs in this script are individual study links (often PubMed). Use the specific article URL, never a generic section or homepage.
- If a study is mentioned in the transcript but does NOT appear in the script below, mention it WITHOUT a hyperlink.
- NEVER fabricate, guess, or infer URLs. NEVER use a search-engine URL. NEVER link to a site you have not been given.
- Do not link the same source more than once in the article.

EPISODE SCRIPT:
{script_text}
"""
    else:
        script_block = """

NO HYPERLINKS AVAILABLE.
You were not given the episode script for this transcript. Do not add hyperlinks to any study, paper, or trial in the article body. Mention studies in plain text. Never fabricate URLs.
"""

    user = f"""From the transcript below, extract ONLY the "What's the deal with" deep-dive segment and ignore all other segments (health news, listener Q&A, intros/outros).

Then write a standalone article with this structure:
1. SEO headline (how someone would Google this topic, e.g. "Does creatine actually work?")
2. Opening hook (1-2 sentences that establish why this matters)
3. Body with 2-4 H2 subheadings covering the key evidence and nuance
4. "Bottom line" section summarizing the takeaway
5. A single closing sentence (not a section) that naturally leads into: "I covered this in depth on Wellness, Actually — listen below."

Then generate 4 to 6 FAQ pairs:
- Questions: phrased exactly the way someone would type them into Google. Mix of the highest-intent queries a reader would have after reading this article (safety, dosing, mechanism, common myths, practical how-to).
- Answers: 2 to 4 sentences each, grounded strictly in the article you just wrote. Reuse the same numbers, study names, and caveats. Plain text only — no HTML tags. No em-dashes.
- Cover the angles most likely to appear in Google "People Also Ask" boxes; do not repeat the headline as a question.

Call the create_article tool with your result.
{script_block}
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
                        "description": "Full article body HTML using only <p> <h2> <ul> <ol> <li> <strong> <em> <a> tags. Use <a href=\"...\" target=\"_blank\" rel=\"noopener noreferrer\"> for any hyperlinks, and only with URLs drawn from the vetted episode script."
                    },
                    "faqs": {
                        "type": "array",
                        "description": "4 to 6 FAQ pairs for the episode. Questions in natural Google-search form; answers are plain text (2 to 4 sentences) grounded strictly in the article.",
                        "minItems": 4,
                        "maxItems": 6,
                        "items": {
                            "type": "object",
                            "properties": {
                                "question": {"type": "string"},
                                "answer": {"type": "string"}
                            },
                            "required": ["question", "answer"]
                        }
                    }
                },
                "required": ["headline", "slug", "meta_description", "episode_title", "article_html", "faqs"]
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


def clean_article_html(article_html):
    """
    Strip stray content-block artifacts the model occasionally prepends to
    article_html (e.g. a serialized '[{"type":"text"}]'). The article body
    always begins with an HTML tag, so drop anything before the first '<'.
    """
    html = (article_html or '').strip()
    first_tag = html.find('<')
    if first_tag > 0:
        print(f"[sanitize] stripped {first_tag} chars of non-HTML preamble from article body.")
        html = html[first_tag:]
    return html


def render_faq_jsonld(faqs):
    if not faqs:
        return ''
    payload = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": f['question'],
                "acceptedAnswer": {"@type": "Answer", "text": f['answer']}
            }
            for f in faqs
        ]
    }
    body = json.dumps(payload, indent=2, ensure_ascii=False)
    indented = '\n'.join('  ' + line for line in body.split('\n'))
    return f'  <script type="application/ld+json">\n{indented}\n  </script>\n'


def render_faq_section(faqs):
    if not faqs:
        return ''
    items = []
    for f in faqs:
        q = htmlmod.escape(f['question'])
        a = htmlmod.escape(f['answer'])
        items.append(
            '      <details style="border-bottom: 1px solid #e0d9d0; padding: 16px 0;">\n'
            f'        <summary style="font-weight: 600; cursor: pointer; font-size: 1.08rem;">{q}</summary>\n'
            f'        <p style="margin-top: 12px; line-height: 1.75;">{a}</p>\n'
            '      </details>'
        )
    return (
        '\n    <section aria-labelledby="faq-heading" style="margin-top: 56px; padding-top: 32px; border-top: 1px solid #e0d9d0;">\n'
        '      <h2 id="faq-heading" style="font-family: var(--font-display); font-size: 1.8rem; margin-bottom: 24px;">Frequently asked questions</h2>\n'
        + '\n'.join(items) + '\n'
        '    </section>\n'
    )


def build_episode_html(data, date_iso, date_display):
    headline = data['headline']
    slug = data['slug']
    meta_desc = data['meta_description']
    article_html = clean_article_html(data['article_html'])
    episode_title = data['episode_title']
    faqs = data.get('faqs') or []
    faq_jsonld = render_faq_jsonld(faqs)
    faq_section = render_faq_section(faqs)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{headline} | F. Perry Wilson, MD</title>
  <meta name="description" content="{meta_desc}">
  <meta name="author" content="F. Perry Wilson">
  <link rel="icon" href="/favicon.ico" sizes="any">
  <link rel="apple-touch-icon" href="/images/apple-touch-icon.png">
  <link rel="alternate" type="application/rss+xml" title="Wellness, Actually — Episode Articles" href="/podcast/rss.xml">
  <link rel="stylesheet" href="../css/style.css">
  <link rel="canonical" href="https://fperrywilson.com/podcast/{slug}.html">
  <meta property="og:title" content="{headline}">
  <meta property="og:description" content="{meta_desc}">
  <meta property="og:type" content="article">
  <meta property="og:url" content="https://fperrywilson.com/podcast/{slug}.html">
  <meta property="og:site_name" content="F. Perry Wilson, MD">
  <meta property="og:image" content="https://fperrywilson.com/images/og-podcast.jpg">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:image:alt" content="Wellness, Actually podcast — with Emily Oster and F. Perry Wilson, MD">
  <meta property="article:published_time" content="{date_iso}">
  <meta property="article:author" content="https://fperrywilson.com">
  <meta property="article:section" content="Health">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:site" content="@fperrywilson">
  <meta name="twitter:creator" content="@fperrywilson">
  <meta name="twitter:title" content="{headline}">
  <meta name="twitter:description" content="{meta_desc}">
  <meta name="twitter:image" content="https://fperrywilson.com/images/og-podcast.jpg">
  <meta name="twitter:image:alt" content="Wellness, Actually podcast — with Emily Oster and F. Perry Wilson, MD">
  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "Article",
    "headline": "{headline}",
    "datePublished": "{date_iso}",
    "dateModified": "{date_iso}",
    "image": "https://fperrywilson.com/images/og-podcast.jpg",
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
{faq_jsonld}</head>
<body>

  <nav class="nav" id="nav">
    <div class="nav-inner">
      <a href="/" class="nav-logo">F. Perry Wilson<span>,</span> MD</a>
      <ul class="nav-links" id="navLinks">
        <li><a href="/#about">About</a></li>
        <li><a href="/#podcast">Podcast</a></li>
        <li><a href="/#book">Book</a></li>
        <li><a href="/#writing">Writing</a></li>
        <li><a href="/#media">Media</a></li>
        <li><a href="/#lab">Lab</a></li>
        <li><a href="/#course">Course</a></li>
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
{faq_section}
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
    <changefreq>yearly</changefreq>
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

    print("Looking for vetted episode script in Drive...")
    script_text = fetch_drive_script(transcript_path.stem)
    if script_text:
        print(f"Drive script fetched ({len(script_text)} chars). Hyperlinks will be added from it.")
    else:
        print("No Drive script available. Article will ship without hyperlinks.")

    print("Calling Claude to generate article...")
    data = call_claude(transcript_text, script_text=script_text)

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
