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
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

import build_rss
import build_llms_txt
import build_podcast_index_schema
import build_topic_pages
import prerender_nav
import episode_blocks


EPISODES_FOLDER_ID = '1qhx8vF3m6Gd9eYUEntLoeAtaVgZ7N-Si'


class _GDocTextExtractor(HTMLParser):
    """Render a Google Docs HTML export to text while preserving the real
    destination URL of every inline hyperlink.

    This exists because Google Docs' text/plain export silently drops inline
    hyperlinks (URLs attached to words rather than pasted as bare text). On the
    HSDD episode that stripped every study citation out of the script, so the
    model only saw the one bare URL and the article shipped with a single link.
    Exporting HTML and re-inserting each link's URL right after its anchor text
    keeps the URL adjacent to the study it documents, which is exactly what both
    the model prompt and validate_links() depend on.
    """

    BLOCK = {'p', 'div', 'br', 'li', 'tr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}
    SKIP = {'style', 'script', 'head'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self._href = None
        self._skip_depth = 0

    @staticmethod
    def _unwrap(href):
        # Google wraps external links as https://www.google.com/url?q=REAL&sa=...
        if not href:
            return None
        if 'google.com/url' in href:
            qs = parse_qs(urlparse(href).query)
            if qs.get('q'):
                href = qs['q'][0]
        href = unquote(href)
        return href if href.startswith('http') else None

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == 'a':
            self._href = self._unwrap(dict(attrs).get('href'))
        if tag in self.BLOCK:
            self.parts.append('\n')

    def handle_startendtag(self, tag, attrs):
        if not self._skip_depth and tag in self.BLOCK:
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag == 'a' and self._href:
            # Put the URL right after the linked text so it stays attached to
            # the specific study it documents.
            self.parts.append(f' ({self._href})')
            self._href = None
        if tag in self.BLOCK:
            self.parts.append('\n')

    def handle_data(self, data):
        if not self._skip_depth:
            self.parts.append(data)

    def get_text(self):
        text = ''.join(self.parts)
        text = re.sub(r'\n[ \t]*\n[ \t]*\n+', '\n\n', text)
        return text.strip()


def gdoc_html_to_text(content):
    """Convert a Google Docs text/html export (bytes or str) to link-preserving text."""
    html_str = content.decode('utf-8', 'replace') if isinstance(content, bytes) else content
    parser = _GDocTextExtractor()
    parser.feed(html_str)
    return parser.get_text()


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

        # Export the Google Doc as HTML, not text/plain: text/plain drops inline
        # hyperlinks, which is how the host attaches most study URLs. We convert
        # the HTML back to text but keep each link's real URL inline next to its
        # anchor. Native binary types would need files().get_media().
        if script['mimeType'] == 'application/vnd.google-apps.document':
            content = service.files().export(
                fileId=script['id'], mimeType='text/html'
            ).execute()
            # Note: files().export does not accept supportsAllDrives; it works on any
            # file the service account can read, including shared-drive content.
            return gdoc_html_to_text(content)
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

    topic_names = list(episode_blocks.CLUSTERS.keys())
    topics_list = '\n'.join(
        f"- {name}: {episode_blocks.TOPIC_META[name]['intro']}" for name in topic_names)

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

Then pick the 1 or 2 site topic categories that best fit this article. Choose from this exact list (name: what the category covers):
{topics_list}
At least one is required; only add a second if the article genuinely fits both.

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
                    },
                    "topics": {
                        "type": "array",
                        "description": "The 1 or 2 site topic categories that best fit this article, from the fixed list in the prompt.",
                        "minItems": 1,
                        "maxItems": 2,
                        "items": {"type": "string", "enum": topic_names}
                    }
                },
                "required": ["headline", "slug", "meta_description", "episode_title", "article_html", "faqs", "topics"]
            }
        }
    ]

    message = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=16000,
        system=system,
        tools=tools,
        tool_choice={"type": "tool", "name": "create_article"},
        messages=[{"role": "user", "content": user}],
    )

    # A truncated response silently drops whatever the model was mid-writing —
    # the FAQs went missing this way once. Fail loudly instead.
    if message.stop_reason == "max_tokens":
        raise RuntimeError(
            "Claude hit the max_tokens limit and the article was truncated. "
            "Increase max_tokens in call_claude() and re-run."
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


def validate_links(article_html, script_text):
    """Every href must appear verbatim in the vetted Drive script.

    The prompt instructs the model to only use script URLs, but mislinks have
    shipped twice — this makes the rule mechanical. With no script available,
    the article must contain no links at all.
    """
    hrefs = [htmlmod.unescape(h) for h in re.findall(r'href="([^"]+)"', article_html)]
    if script_text:
        bad = sorted({h for h in hrefs if h not in script_text})
    else:
        bad = sorted(set(hrefs))
    if bad:
        sys.exit(
            "ERROR: article contains link(s) that do not appear verbatim in the vetted "
            "episode script:\n  " + "\n  ".join(bad) +
            "\nRefusing to publish. Every hyperlink must come from the Drive SCRIPT doc."
        )
    print(f"[links] {len(hrefs)} link(s) verified against the episode script."
          if hrefs else "[links] article contains no hyperlinks.")


def strip_em_dashes(data):
    """House style bans em-dashes; enforce it deterministically."""
    count = 0

    def fix(s):
        nonlocal count
        if '—' in s:
            count += s.count('—')
            s = s.replace(' — ', ', ').replace('— ', ', ').replace(' —', ', ').replace('—', ', ')
        return s

    for key in ('headline', 'meta_description', 'episode_title', 'article_html'):
        if isinstance(data.get(key), str):
            data[key] = fix(data[key])
    for f in data.get('faqs') or []:
        f['question'] = fix(f['question'])
        f['answer'] = fix(f['answer'])
    if count:
        print(f"[sanitize] replaced {count} em-dash(es) with commas (house style).")
    return data


def fetch_episode_link(date_iso, episode_title=None):
    """Find this episode's Apple Podcasts URL via the iTunes Lookup API.

    Same API the update-podcast.yml homepage workflow uses. Matches by title
    first; a date-proximity match is only accepted when the episode name
    shares a topic word with the article's episode title, because episodes
    can air on adjacent days and the nearest date alone can pick the wrong
    one. Returns the episode URL, or None to fall back to the show page
    (e.g. when the article is generated before the episode is live on Apple).
    """
    import urllib.request

    def norm(s):
        return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]', ' ', s.lower())).strip()

    boilerplate = {'what', 'whats', 'the', 'deal', 'with', 'and', 'for', 'about'}

    def topic_words(title):
        return {w for w in norm(title).split() if w not in boilerplate and len(w) >= 3}

    try:
        api_url = "https://itunes.apple.com/lookup?id=1633515294&entity=podcastEpisode&limit=200"
        payload = json.loads(urllib.request.urlopen(api_url, timeout=30).read())
        target = datetime.strptime(date_iso, '%Y-%m-%d')
        episodes = []
        for item in payload.get('results', []):
            if item.get('kind') != 'podcast-episode' or not item.get('trackViewUrl'):
                continue
            try:
                released = datetime.strptime(item.get('releaseDate', '')[:10], '%Y-%m-%d')
            except ValueError:
                continue
            episodes.append((released, item))

        if episode_title:
            exact = [i for _, i in episodes if norm(i['trackName']) == norm(episode_title)]
            if len(exact) == 1:
                print(f"[episode] matched Apple episode by title: {exact[0]['trackName']}")
                return exact[0]['trackViewUrl']

        best = None
        for released, item in episodes:
            delta = abs((released - target).days)
            if delta <= 3 and (best is None or delta < best[0]):
                best = (delta, item)
        if best:
            name = best[1]['trackName']
            if episode_title and not (topic_words(episode_title) & topic_words(name)):
                print(f"[episode] nearest-dated episode '{name}' does not match topic "
                      f"'{episode_title}'; using show link rather than risk a mislink.")
                return None
            print(f"[episode] matched Apple episode: {name} ({best[1]['releaseDate'][:10]})")
            return best[1]['trackViewUrl']
        print(f"[episode] no Apple episode within 3 days of {date_iso}; using show link.")
    except Exception as e:
        print(f"[episode] iTunes lookup failed ({e}); using show link.")
    return None


YOUTUBE_CHANNEL_ID = 'UCu4OHd94MHqjlMp_Mgks84w'  # @fperrywilson


def fetch_episode_video(episode_title):
    """Find this episode's YouTube video id on the host's channel feed.

    Deliberately does not look at dates. The channel feed reports wrong
    publish dates for some uploads (the alcohol episode comes back as 2015),
    so a date-proximity match like fetch_episode_link's would pick the wrong
    video or none at all. Instead: keep only full-episode uploads, which all
    carry the show name, then match on topic-word overlap with the episode
    title. The channel also posts near-daily short clips whose titles mention
    the same topics, which is what the show-name gate filters out.

    Returns a video id, or None to ship the article with no embed (better
    than embedding the wrong discussion).
    """
    import urllib.request
    import xml.etree.ElementTree as ET

    # Show-name words are in every full-episode title, so they carry no
    # topic signal; the rest is the same boilerplate fetch_episode_link drops.
    boilerplate = {'what', 'whats', 'the', 'deal', 'with', 'and', 'for', 'about',
                   'wellness', 'actually', 'podcast'}

    def topic_words(title):
        norm = re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]', ' ', title.lower())).strip()
        return {w for w in norm.split() if w not in boilerplate and len(w) >= 3}

    wanted = topic_words(episode_title)
    if not wanted:
        print(f"[video] episode title '{episode_title}' has no topic words; skipping embed.")
        return None

    try:
        feed_url = ('https://www.youtube.com/feeds/videos.xml?channel_id='
                    + YOUTUBE_CHANNEL_ID)
        req = urllib.request.Request(feed_url, headers={'User-Agent': 'Mozilla/5.0'})
        raw = urllib.request.urlopen(req, timeout=30).read()
        ns = {'atom': 'http://www.w3.org/2005/Atom',
              'yt': 'http://www.youtube.com/xml/schemas/2015',
              'media': 'http://search.yahoo.com/mrss/'}
        scored = []
        for entry in ET.fromstring(raw).findall('atom:entry', ns):
            vid = entry.findtext('yt:videoId', default='', namespaces=ns)
            title = entry.findtext('media:group/media:title', default='',
                                   namespaces=ns) or entry.findtext(
                                       'atom:title', default='', namespaces=ns)
            if not vid or not title:
                continue
            flat = re.sub(r'[^a-z0-9 ]', ' ', title.lower())
            if 'wellness' not in flat or 'actually' not in flat:
                continue  # a short clip, not the full episode
            scored.append((len(wanted & topic_words(title)) / len(wanted), title, vid))

        if not scored:
            print("[video] no full-episode videos in the channel feed; skipping embed.")
            return None

        scored.sort(key=lambda s: -s[0])
        best = scored[0]
        if best[0] < 0.5:
            print(f"[video] best channel match '{best[1]}' shares too little with "
                  f"'{episode_title}'; skipping embed rather than risk the wrong video.")
            return None
        if len(scored) > 1 and scored[1][0] == best[0]:
            print(f"[video] '{best[1]}' and '{scored[1][1]}' match "
                  f"'{episode_title}' equally well; skipping embed.")
            return None
        print(f"[video] matched YouTube episode: {best[1]} ({best[2]})")
        return best[2]
    except Exception as e:
        print(f"[video] channel feed lookup failed ({e}); skipping embed.")
    return None


def render_video_embed(video_id, episode_title):
    """The responsive 16:9 embed block used on every episode page."""
    # The attribute is double-quoted, so only " needs escaping; escaping the
    # apostrophe too would render as &#x27; and differ from the other pages.
    title = htmlmod.escape(f"{episode_title} — Wellness, Actually",
                           quote=False).replace('"', '&quot;')
    return (
        "<p>Here's our discussion from the episode:</p>\n\n"
        '<div style="position: relative; padding-bottom: 56.25%; height: 0; '
        'margin: 24px 0 8px; overflow: hidden;">\n'
        '  <iframe style="position: absolute; top: 0; left: 0; width: 100%; '
        'height: 100%; border: 0;"\n'
        f'    src="https://www.youtube.com/embed/{video_id}"\n'
        f'    title="{title}"\n'
        '    loading="lazy"\n'
        '    allow="accelerometer; clipboard-write; encrypted-media; gyroscope; '
        'picture-in-picture; web-share"\n'
        '    referrerpolicy="strict-origin-when-cross-origin"\n'
        '    allowfullscreen></iframe>\n'
        '</div>\n'
    )


def insert_video_embed(article_html, video_id, episode_title):
    """Place the embed just above the model's closing 'listen below' line.

    That sentence is the last paragraph of every generated article, so the
    video lands after the body and before the podcast call to action, which
    is where it sits on the hand-edited pages.
    """
    if not video_id:
        return article_html
    if 'youtube.com/embed' in article_html:
        return article_html  # already embedded; don't double up on a re-run
    block = render_video_embed(video_id, episode_title)
    closing = re.search(r'\n*<p>[^<]*covered this in depth[^<]*</p>', article_html)
    if closing:
        return (article_html[:closing.start()] + '\n\n' + block + '\n'
                + closing.group(0).lstrip('\n') + article_html[closing.end():])
    print("[video] closing 'listen below' line not found; appending embed at the end.")
    return article_html.rstrip() + '\n\n' + block


def render_episode_jsonld(episode_title, date_iso, episode_url):
    payload = {
        "@context": "https://schema.org",
        "@type": "PodcastEpisode",
        "name": episode_title,
        "datePublished": date_iso,
        "partOfSeries": {
            "@type": "PodcastSeries",
            "name": "Wellness, Actually",
            "url": "https://fperrywilson.com/podcast/"
        }
    }
    if episode_url:
        payload["url"] = episode_url
    body = json.dumps(payload, indent=2, ensure_ascii=False)
    indented = '\n'.join('  ' + line for line in body.split('\n'))
    return f'  <script type="application/ld+json">\n{indented}\n  </script>\n'


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


def build_episode_html(data, date_iso, date_display, episode_url=None, video_id=None):
    headline = data['headline']
    slug = data['slug']
    meta_desc = data['meta_description']
    article_html = clean_article_html(data['article_html'])
    article_html = insert_video_embed(article_html, video_id, data['episode_title'])
    # The vetted study links in the body become the Article's citation list.
    citations = episode_blocks.extract_citations(article_html)
    article_jsonld_block = episode_blocks.render_article_block(
        headline, date_iso, date_iso, slug, meta_desc, citations)
    episode_title = data['episode_title']
    faqs = data.get('faqs') or []
    faq_jsonld = render_faq_jsonld(faqs)
    faq_section = render_faq_section(faqs)
    # AEO: surface the answer-shaped meta description as a visible "Short answer"
    # box, and attach an "About the author" E-E-A-T block at the foot.
    tldr_section = episode_blocks.render_tldr(meta_desc)
    author_bio_section = episode_blocks.render_author_bio()
    # Emitted empty; prerender_nav.main() (called at the end of generation)
    # fills it from the topic clusters, the same way it fills the nav below.
    related_div_open = episode_blocks.RELATED_DIV_OPEN
    episode_jsonld = render_episode_jsonld(episode_title, date_iso, episode_url)
    show_apple_url = ('https://podcasts.apple.com/us/podcast/'
                      'wellness-actually-with-emily-oster-perry-wilson-md/id1633515294')
    apple_url = episode_url or show_apple_url
    episode_title_html = (
        f'<a href="{episode_url}" target="_blank" rel="noopener noreferrer" '
        f'style="color: inherit;"><strong>"{episode_title}"</strong></a>'
        if episode_url else f'<strong>"{episode_title}"</strong>'
    )

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
{article_jsonld_block}
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
{episode_jsonld}{faq_jsonld}</head>
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

{tldr_section}
    <div style="font-size: 1.08rem; line-height: 1.85;">
      {article_html}
    </div>
{faq_section}
    <div style="margin-top: 56px; padding: 32px; background: #f3ede6; border-left: 4px solid var(--color-accent); border-radius: 0 4px 4px 0;">
      <p style="font-family: var(--font-mono); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.12em; color: var(--color-accent); margin-bottom: 8px;">Wellness, Actually Podcast</p>
      <p style="font-size: 1.05rem; margin-bottom: 20px;">{episode_title_html} — Listen to the full episode, including the week's health news and listener Q&amp;A.</p>
      <div style="display: flex; gap: 12px; flex-wrap: wrap;">
        <a href="{apple_url}" target="_blank" rel="noopener noreferrer" class="btn btn-primary">Apple Podcasts</a>
        <a href="https://open.spotify.com/show/5igTryEwHMmAJfODAFKp3W" target="_blank" rel="noopener noreferrer" class="btn btn-outline">Spotify</a>
        <a href="https://www.iheart.com/podcast/1119-wellness-actually-with-em-99325147/" target="_blank" rel="noopener noreferrer" class="btn btn-outline">iHeart</a>
      </div>
    </div>

{author_bio_section}
    {related_div_open}</div>
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
        r'      <div class="media-item"[^>]*>.*?</div>\n      </div>\n',
        re.DOTALL
    )
    matched = entry_pattern.findall(content)

    # Remove all existing entries from content; drop any stale entry for this
    # same slug so a re-run replaces rather than duplicates it
    for entry in matched:
        content = content.replace(entry, '')
    existing_entries = [e for e in matched if f'href="/podcast/{slug}.html"' not in e]

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


EPISODE_BLOCKS_PATH = Path(__file__).resolve().parent / 'episode_blocks.py'


def update_clusters(slug, topics):
    """Persist the model's topic choices so the episode lands on its hub pages.

    Adds the slug to the chosen lists in CLUSTERS, both in memory (so the
    prerender_nav/build_topic_pages calls later in this run see it) and in
    scripts/episode_blocks.py on disk (so the assignment is versioned in the
    episode PR and future runs build on it). Replace semantics on re-runs: the
    slug is removed from every cluster before being re-added to the chosen ones.
    """
    topics = topics or []
    valid = [t for t in dict.fromkeys(topics) if t in episode_blocks.CLUSTERS]
    unknown = [t for t in topics if t not in episode_blocks.CLUSTERS]
    if unknown:
        print(f"[topics] ignoring unknown topic name(s) from the model: {unknown}")
    if not valid:
        sys.exit(
            "ERROR: model returned no valid topic category. Every episode must be "
            "assigned to at least one cluster in scripts/episode_blocks.py so it "
            "appears on a topic hub and gets related-episode links."
        )

    # In-memory first: every other script reads episode_blocks.CLUSTERS via the
    # module attribute, so mutating the lists in place is enough for this run.
    for members in episode_blocks.CLUSTERS.values():
        if slug in members:
            members.remove(slug)
    for name in valid:
        episode_blocks.CLUSTERS[name].append(slug)

    # On disk: rewrite only the CLUSTERS block of episode_blocks.py.
    src = EPISODE_BLOCKS_PATH.read_text(encoding='utf-8')
    block_match = re.search(r'CLUSTERS = \{\n.*?\n\}\n', src, re.DOTALL)
    if not block_match:
        sys.exit("ERROR: could not locate the CLUSTERS block in scripts/episode_blocks.py.")
    block = block_match.group(0)
    block = re.sub(rf'^[ \t]*"{re.escape(slug)}",\n', '', block, flags=re.MULTILINE)
    for name in valid:
        entry_re = re.compile(
            r'(    "' + re.escape(name) + r'": \[\n.*?)(    \],\n)', re.DOTALL)
        block, n = entry_re.subn(
            lambda m: m.group(1) + f'        "{slug}",\n' + m.group(2), block, count=1)
        if not n:
            sys.exit(f"ERROR: could not find cluster '{name}' in the CLUSTERS block.")
    src = src[:block_match.start()] + block + src[block_match.end():]
    EPISODE_BLOCKS_PATH.write_text(src, encoding='utf-8')
    print(f"[topics] assigned '{slug}' to: {', '.join(valid)}")


def update_sitemap(slug, date_iso):
    sitemap_path = Path('sitemap.xml')
    content = sitemap_path.read_text(encoding='utf-8')
    # Bump the article-listing page's lastmod, since it changes with every episode
    content = re.sub(
        r'(<loc>https://fperrywilson\.com/podcast/</loc>\s*<lastmod>)[^<]+(</lastmod>)',
        rf'\g<1>{date_iso}\g<2>', content)
    if f'<loc>https://fperrywilson.com/podcast/{slug}.html</loc>' in content:
        print(f"[sitemap] entry for {slug} already present; not adding a duplicate.")
    else:
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

    # The transcript filename seeds the article date, sitemap entry, and RSS
    # pubDate. A wrong year here poisons all of them (it happened once:
    # 2025-05-27 instead of 2026-06-04), so sanity-check before generating.
    age_days = (datetime.now() - datetime.strptime(date_iso, '%Y-%m-%d')).days
    if (age_days > 90 or age_days < -14) and '--allow-odd-date' not in sys.argv:
        sys.exit(
            f"ERROR: article date {date_iso} (parsed from the transcript filename) is "
            f"{abs(age_days)} days in the {'past' if age_days > 0 else 'future'}. "
            "Check the year/format of the transcript filename, or pass --allow-odd-date to override."
        )

    print("Looking for vetted episode script in Drive...")
    script_text = fetch_drive_script(transcript_path.stem)
    if script_text:
        print(f"Drive script fetched ({len(script_text)} chars). Hyperlinks will be added from it.")
    else:
        print("No Drive script available. Article will ship without hyperlinks.")

    print("Calling Claude to generate article...")
    data = call_claude(transcript_text, script_text=script_text)
    if not data.get('faqs'):
        print("Model returned no FAQs; retrying once...")
        data = call_claude(transcript_text, script_text=script_text)
        if not data.get('faqs'):
            sys.exit("ERROR: model returned no FAQs after retry. Every episode page needs the "
                     "FAQ section and FAQPage schema for rich-result eligibility.")

    data = strip_em_dashes(data)
    data['article_html'] = clean_article_html(data['article_html'])
    validate_links(data['article_html'], script_text)

    desc_len = len(data['meta_description'])
    if not 130 <= desc_len <= 165:
        print(f"WARNING: meta description is {desc_len} chars (target 150-160). "
              "Consider tightening it during PR review.")

    slug = data['slug']
    headline = data['headline']
    print(f"Generated: '{headline}' → podcast/{slug}.html")

    episode_url = fetch_episode_link(date_iso, data['episode_title'])
    video_id = fetch_episode_video(data['episode_title'])

    # Write episode page
    episode_html = build_episode_html(data, date_iso, date_display,
                                      episode_url=episode_url, video_id=video_id)
    output_path = Path(f'podcast/{slug}.html')
    output_path.parent.mkdir(exist_ok=True)
    output_path.write_text(episode_html, encoding='utf-8')
    print(f"Written: {output_path}")

    # Update index, sitemap, and episodes nav
    update_podcast_index(slug, headline, date_iso, date_display, data['meta_description'])
    update_sitemap(slug, date_iso)
    update_episodes_js(slug, headline)
    print("Updated podcast/index.html, sitemap.xml, and js/episodes.js")

    # Put the episode on its topic hub(s) before the rebuild steps below, so
    # the hubs, related-episodes block, and topic sitemap entries include it.
    update_clusters(slug, data.get('topics'))

    # Keep the crawlable internal-link chain and the feed in sync. These were
    # manual checklist steps before and drifted every time they were skipped.
    prerender_nav.main()
    build_topic_pages.main()
    build_rss.main()
    build_llms_txt.main()
    build_podcast_index_schema.main()
    print("Pre-rendered episode nav on all pages and rebuilt the topic hubs, "
          "podcast/rss.xml, llms.txt, and the podcast index ItemList schema")

    set_output('slug', slug)
    set_output('headline', headline)


if __name__ == '__main__':
    main()
