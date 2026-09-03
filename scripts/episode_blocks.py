"""Shared HTML / JSON-LD fragments for episode pages.

Imported by both generate_episode_post.py (new articles) and
retrofit_author_aeo.py (existing pages) so the answer-engine-optimization
blocks never drift between the two code paths. These are the AEO additions:

  1. An enriched author entity in each article's Article JSON-LD. The @id ties
     every article back to the single Person entity defined on the homepage so
     answer engines can consolidate authorship, while the inline credentials
     let each page assert the author's authority standalone (this is YMYL
     health content, where author expertise is weighted heavily).
  2. A visible "Short answer" takeaway box at the top of the article, the most
     extractable format for AI answers.
  3. A visible "About the author" E-E-A-T block at the foot of the article.

Each visible block carries a data-aeo marker so check_site.py can assert its
presence and the retrofit can stay idempotent.
"""
import html as htmlmod
import json
import re
from datetime import datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

# Stable @id for the Person entity defined once on the homepage (index.html).
PERSON_ID = "https://fperrywilson.com/#person"

# The episode-article collection every episode page belongs to.
COLLECTION_NAME = "Wellness, Actually — Episode Articles"
COLLECTION_URL = "https://fperrywilson.com/podcast/"
INLANGUAGE = "en-US"

_PROFILE_SAMEAS = [
    "https://scholar.google.com/citations?user=iB9er1AAAAAJ",
    "https://www.ncbi.nlm.nih.gov/pubmed/?term=wilson+fp",
    "https://twitter.com/fperrywilson",
]


def author_jsonld():
    """Rich author object for an article's Article JSON-LD.

    The @id points at the homepage Person; the inline fields make the page
    self-describing for engines that don't dereference @id."""
    return {
        "@type": "Person",
        "@id": PERSON_ID,
        "name": "F. Perry Wilson",
        "honorificSuffix": "MD MSCE",
        "jobTitle": "Associate Professor of Medicine and Public Health",
        "affiliation": {"@type": "Organization", "name": "Yale University"},
        "url": "https://fperrywilson.com",
        "sameAs": _PROFILE_SAMEAS,
    }


def publisher_jsonld():
    return {
        "@type": "Person",
        "@id": PERSON_ID,
        "name": "F. Perry Wilson",
        "url": "https://fperrywilson.com",
    }


# --- Shared <head> fragments ------------------------------------------------
#
# Every page on the site needs these, so they live here rather than being
# retyped per template. check_site.py asserts both are present on every page.

# GA4. Episode pages were shipping without it, which made the whole SEO effort
# unmeasurable: search traffic landed on /podcast/ articles and never appeared
# in analytics. Same measurement ID as index.html.
GA_MEASUREMENT_ID = "G-8Q905DBDJR"

ANALYTICS_SNIPPET = (
    '  <!-- Google tag (gtag.js) -->\n'
    f'  <script async src="https://www.googletagmanager.com/gtag/js?id={GA_MEASUREMENT_ID}"></script>\n'
    '  <script>\n'
    '    window.dataLayer = window.dataLayer || [];\n'
    '    function gtag(){dataLayer.push(arguments);}\n'
    "    gtag('js', new Date());\n"
    f"    gtag('config', '{GA_MEASUREMENT_ID}');\n"
    '  </script>\n'
)

# Fonts used to be pulled in by an @import inside style.css, which the browser
# can't discover until the stylesheet has downloaded and parsed -- a serialized
# HTML -> style.css -> fonts.googleapis.com -> font files chain. Requesting the
# font CSS directly from the page head removes one full round trip from that
# chain, and the preconnects warm both font hosts' DNS/TLS in parallel.
#
# If this URL changes, it must change here only: style.css no longer imports.
FONT_CSS_URL = (
    "https://fonts.googleapis.com/css2"
    "?family=Playfair+Display:ital,wght@0,400;0,600;0,700;1,400;1,600"
    "&amp;family=Source+Sans+3:ital,wght@0,300;0,400;0,500;0,600;1,400"
    "&amp;family=JetBrains+Mono:wght@400&amp;display=swap"
)

FONT_PRECONNECT = (
    '  <link rel="preconnect" href="https://fonts.googleapis.com">\n'
    '  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
    f'  <link rel="stylesheet" href="{FONT_CSS_URL}">\n'
)


def render_breadcrumb(headline, slug):
    """BreadcrumbList JSON-LD, built through json.dumps so a headline
    containing a double quote can't break the block."""
    url = f"https://fperrywilson.com/podcast/{slug}.html"
    obj = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home",
             "item": "https://fperrywilson.com"},
            {"@type": "ListItem", "position": 2, "name": "Episode Articles",
             "item": COLLECTION_URL},
            {"@type": "ListItem", "position": 3, "name": headline, "item": url},
        ],
    }
    body = json.dumps(obj, indent=2, ensure_ascii=False)
    indented = '\n'.join('  ' + line for line in body.split('\n'))
    return f'  <script type="application/ld+json">\n{indented}\n  </script>\n'


VIDEO_JSONLD_MARKER = '"@type": "VideoObject"'

# The show is produced on US Eastern time, so the air date means Eastern.
SHOW_TZ = ZoneInfo('America/New_York')


def video_upload_datetime(date_iso):
    """Episode air date as a full ISO 8601 timestamp with a UTC offset.

    Google Search Console rejects a bare "2026-06-25" on VideoObject.uploadDate
    with "Datetime property uploadDate is missing a timezone" / "Invalid
    datetime value", which suppressed the video rich result on all 15 pages
    carrying an embed. Schema.org accepts a plain date; Google does not.

    Midnight Eastern is a convention, not a claim about the real upload minute.
    We only know the air date: the YouTube feed's own publish timestamps carry
    the offset but are wrong for some uploads (the alcohol episode reports 2015,
    see CLAUDE.md), so they cannot be used. ZoneInfo picks EST or EDT per date,
    so summer episodes get -04:00 and winter ones -05:00.
    """
    return datetime.strptime(date_iso, '%Y-%m-%d').replace(tzinfo=SHOW_TZ).isoformat()


def render_video_jsonld(video_id, episode_title, date_iso, description, slug):
    """VideoObject JSON-LD for the embedded YouTube discussion.

    Without this the embed is invisible to search: an <iframe> tells crawlers
    nothing about what the video contains. uploadDate is the episode air date --
    the video is that episode's segment, and the channel feed's own dates are
    unreliable (see CLAUDE.md), so this is the trustworthy value available.
    """
    if not video_id:
        return ''
    obj = {
        "@context": "https://schema.org",
        "@type": "VideoObject",
        "name": f"{episode_title} — Wellness, Actually",
        "description": description,
        "thumbnailUrl": f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg",
        "uploadDate": video_upload_datetime(date_iso),
        "embedUrl": f"https://www.youtube.com/embed/{video_id}",
        "contentUrl": f"https://www.youtube.com/watch?v={video_id}",
        "publisher": publisher_jsonld(),
        "isPartOf": {
            "@type": "Article",
            "url": f"https://fperrywilson.com/podcast/{slug}.html",
        },
    }
    body = json.dumps(obj, indent=2, ensure_ascii=False)
    indented = '\n'.join('  ' + line for line in body.split('\n'))
    return f'  <script type="application/ld+json">\n{indented}\n  </script>\n'


def indent_json(obj, spaces):
    """json.dumps(indent=2) re-indented so it drops cleanly into a JSON-LD
    block whose keys sit at `spaces` columns (first line stays inline)."""
    body = json.dumps(obj, indent=2, ensure_ascii=False)
    return ('\n' + ' ' * spaces).join(body.split('\n'))


# --- Article JSON-LD --------------------------------------------------------
#
# The full Article structured-data block is built here (not inline in the
# generator) so new articles and the retrofit of existing pages emit identical
# markup. Beyond the basics it carries the AEO/SEO fields:
#   - isPartOf / mainEntityOfPage / inLanguage: tie each article to the episode
#     collection and declare its canonical page and language, so engines can
#     consolidate the corpus and place the page.
#   - citation: the vetted study URLs the article links, restated as machine
#     readable sources. This is the grounding signal answer engines look for on
#     YMYL health content — "these claims trace to these specific papers."

_BODY_OPEN = '<div style="font-size: 1.08rem; line-height: 1.85;">'
_FAQ_ANCHOR = '<section aria-labelledby="faq-heading"'


def body_region(page_src):
    """The article-body HTML of a rendered episode page: from the body div down
    to the FAQ section. Isolating it means citation extraction only sees the
    vetted study links in the prose, never the podcast-app / author-bio / nav
    boilerplate that lives below it."""
    start = page_src.find(_BODY_OPEN)
    if start == -1:
        return ''
    end = page_src.find(_FAQ_ANCHOR, start)
    return page_src[start:end] if end != -1 else page_src[start:]


# Hosts that occasionally appear as inline links in an article body but are NOT
# scholarly sources: social posts (often the misinformation the article rebuts)
# and embedded video/news. Citations should point at the evidence, so these are
# filtered out. This is a denylist, not an allowlist, on purpose: everything
# else — PubMed, DOI, and every journal domain — is treated as scholarly, so a
# study is never dropped just because its journal isn't on a list.
_NON_SCHOLARLY_HOSTS = (
    'instagram.com', 'youtube.com', 'youtu.be', 'twitter.com', 'x.com',
    'tiktok.com', 'facebook.com', 'fb.com', 'threads.net', 'reddit.com',
    'linkedin.com', 'nytimes.com', 'washingtonpost.com', 'statnews.com',
    'thehill.com', 'tomshardware.com', 'share.google', 'google.com',
)


def _is_scholarly(url):
    host = urlparse(url).netloc.lower()
    if host.startswith('www.'):
        host = host[4:]
    return not any(host == d or host.endswith('.' + d) for d in _NON_SCHOLARLY_HOSTS)


def extract_citations(body_html):
    """Ordered, de-duplicated scholarly links in the article body — the study
    URLs, which become the Article's citation list. Social/video/news links are
    excluded (see _NON_SCHOLARLY_HOSTS)."""
    urls = [htmlmod.unescape(u) for u in re.findall(r'href="(https?://[^"]+)"', body_html)]
    return list(dict.fromkeys(u for u in urls if _is_scholarly(u)))


def citation_jsonld(urls):
    """Render citation URLs as schema.org CreativeWork references (or [] )."""
    return [{"@type": "CreativeWork", "url": u} for u in urls]


def article_jsonld(headline, date_published, date_modified, slug, description, citation_urls=()):
    """The Article structured-data object for an episode page."""
    url = f"https://fperrywilson.com/podcast/{slug}.html"
    obj = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": headline,
        "datePublished": date_published,
        "dateModified": date_modified,
        "image": "https://fperrywilson.com/images/og-podcast.jpg",
        "author": author_jsonld(),
        "publisher": publisher_jsonld(),
        "description": description,
        "url": url,
        "mainEntityOfPage": url,
        "inLanguage": INLANGUAGE,
        "isPartOf": {"@type": "CollectionPage", "name": COLLECTION_NAME, "url": COLLECTION_URL},
    }
    cites = citation_jsonld(citation_urls)
    if cites:
        obj["citation"] = cites
    return obj


def render_article_block(headline, date_published, date_modified, slug, description, citation_urls=()):
    """The full <script type="application/ld+json"> Article block, indented to
    sit in an episode page's <head> (two-space base, matching the other blocks)."""
    obj = article_jsonld(headline, date_published, date_modified, slug, description, citation_urls)
    body = json.dumps(obj, indent=2, ensure_ascii=False)
    indented = '\n'.join('  ' + line for line in body.split('\n'))
    return f'  <script type="application/ld+json">\n{indented}\n  </script>'


TLDR_MARKER = 'data-aeo="tldr"'
AUTHOR_BIO_MARKER = 'data-aeo="author-bio"'


def render_tldr(text):
    """The 'Short answer' box, surfaced near the top where engines lift it.

    `text` must be the article's verdict, not its meta description. Those were
    the same string originally, which wasted the box: a meta description is
    written to earn a click, so it teases ("here's what the evidence shows")
    where this box has to answer. The generator gets it from the model's
    `short_answer` field; existing pages were backfilled by
    scripts/backfill_short_answers.py.
    """
    safe = htmlmod.escape(text.strip())
    return (
        f'    <div {TLDR_MARKER} style="margin-bottom: 40px; padding: 18px 24px; '
        'background: #f3ede6; border-left: 4px solid var(--color-accent); border-radius: 0 4px 4px 0;">\n'
        '      <p style="font-family: var(--font-mono); font-size: 0.72rem; text-transform: uppercase; '
        'letter-spacing: 0.12em; color: var(--color-accent); margin-bottom: 8px;">Short answer</p>\n'
        f'      <p style="font-size: 1.1rem; line-height: 1.6; margin: 0;">{safe}</p>\n'
        '    </div>\n'
    )


# --- Related episodes -------------------------------------------------------
#
# Topic clusters for the "Related episodes" block. Overlapping by design: an
# episode can sit in more than one cluster (e.g. protein is both a supplement
# and a diet topic), and "related" for a page is the union of its cluster-mates,
# ranked by how many clusters they share with it, then by recency, capped at 3.
# Slugs are the keys, so adding an episode means adding it to one or two lists.
CLUSTERS = {
    "Supplements & sports nutrition": [
        "does-creatine-actually-work",
        "how-much-protein-do-you-actually-need",
        "does-bovine-colostrum-actually-work",
        "what-does-the-sun-actually-do-to-your-health",
    ],
    "Hormones & sexual health": [
        "does-high-cortisol-cause-belly-fat",
        "does-testosterone-replacement-therapy-actually-work",
        "does-hormone-replacement-therapy-actually-work",
        "does-addyi-work-low-sexual-desire-women",
        "are-sperm-counts-really-declining",
        "pregnancy-brain-what-actually-changes",
    ],
    "Metabolic & diet": [
        "glp-1-weight-loss-evidence",
        "is-red-meat-actually-bad-for-you",
        "continuous-glucose-monitors-non-diabetics",
        "how-much-protein-do-you-actually-need",
        "is-moderate-drinking-actually-bad-for-you",
        "is-gluten-actually-bad-for-you",
        "what-your-poop-says-about-your-health",
    ],
    "Biohacking & recovery trends": [
        "cold-plunges-saunas-health-benefits",
        "does-red-light-therapy-actually-work",
        "do-cupping-and-dry-needling-actually-work",
        "does-methylene-blue-actually-work",
        "continuous-glucose-monitors-non-diabetics",
        "what-your-poop-says-about-your-health",
    ],
    "Injectable & regenerative therapies": [
        "do-peptide-injections-actually-work",
        "do-stem-cell-injections-actually-work",
        "does-testosterone-replacement-therapy-actually-work",
        "glp-1-weight-loss-evidence",
    ],
    "Brain, mood & sleep": [
        "do-psychedelics-actually-work",
        "how-much-sleep-do-you-need",
        "does-methylene-blue-actually-work",
        "pregnancy-brain-what-actually-changes",
        "is-moderate-drinking-actually-bad-for-you",
        "is-fluoride-in-water-safe-and-does-it-still-work",
    ],
    "Environmental exposures & health scares": [
        "are-microplastics-actually-harming-your-health",
        "are-sperm-counts-really-declining",
        "is-red-meat-actually-bad-for-you",
        "what-does-the-sun-actually-do-to-your-health",
        "is-fluoride-in-water-safe-and-does-it-still-work",
        "what-ticks-actually-do-to-your-body",
    ],
    "Health technology": [
        "how-mrna-vaccines-work",
    ],
    "Screening & diagnostics": [
        "are-full-body-scans-worth-it",
        "continuous-glucose-monitors-non-diabetics",
        "what-ticks-actually-do-to-your-body",
    ],
}


# Per-topic metadata for the hub pages built from CLUSTERS. Keyed by the same
# cluster names; slugs are fixed here (not derived from the name) so renaming a
# topic's display text never breaks its URL. intro is the hub's lead sentence
# and meta description. build_topic_pages.py joins this with CLUSTERS (members)
# and asserts the two dicts have identical keys, so a new cluster can't ship a
# hub page without a slug/intro or vice versa.
TOPIC_META = {
    "Supplements & sports nutrition": {
        "slug": "supplements-sports-nutrition",
        "intro": "Evidence-based deep dives on the supplements and sports-nutrition "
                 "products people actually take, and what the research says they do.",
    },
    "Hormones & sexual health": {
        "slug": "hormones-sexual-health",
        "intro": "What the evidence shows on hormone therapies and sexual health, from "
                 "testosterone and HRT to treatments for low desire.",
    },
    "Metabolic & diet": {
        "slug": "metabolic-diet",
        "intro": "Weight, blood sugar, and diet examined through the actual data on "
                 "GLP-1s, red meat, protein, and continuous glucose monitoring.",
    },
    "Biohacking & recovery trends": {
        "slug": "biohacking-recovery-trends",
        "intro": "The wellness gadgets and recovery trends filling your feed, tested "
                 "against the evidence rather than the hype.",
    },
    "Injectable & regenerative therapies": {
        "slug": "injectable-regenerative-therapies",
        "intro": "Peptides, stem cells, and other injectable therapies, and what the "
                 "clinical evidence actually supports.",
    },
    "Brain, mood & sleep": {
        "slug": "brain-mood-sleep",
        "intro": "The science of sleep, mood, and cognition, from psychedelics to how "
                 "much sleep you really need.",
    },
    "Environmental exposures & health scares": {
        "slug": "environmental-exposures-health-scares",
        "intro": "Microplastics, declining sperm counts, and other health scares, "
                 "weighed against what the evidence really shows.",
    },
    "Health technology": {
        "slug": "health-technology",
        "intro": "How emerging medical technologies actually work, and what the "
                 "evidence says they deliver, from mRNA vaccines onward.",
    },
    "Screening & diagnostics": {
        "slug": "screening-diagnostics",
        "intro": "What the evidence says about screening tests and diagnostic scans, "
                 "and when they help versus when they lead to overdiagnosis.",
    },
}

TOPICS_URL = "https://fperrywilson.com/podcast/topics/"


def topic_slug(name):
    return TOPIC_META[name]["slug"]


def topics_for_episode(episode_slug):
    """The topics an episode belongs to, as [(topic_slug, topic_name), ...] in
    CLUSTERS order. Drives the 'Topics' links in the episode's related block."""
    return [(TOPIC_META[name]["slug"], name)
            for name, members in CLUSTERS.items() if episode_slug in members]


def compute_related(slug, order, limit=3):
    """Return up to `limit` related slugs for `slug`.

    `order` is the list of all slugs newest-first; it breaks ties so the most
    recent cluster-mate wins when several share the same number of clusters.
    Pure function of the cluster map and order, so prerender_nav (which stamps
    the block) and check_site (which verifies it) always agree."""
    order_index = {s: i for i, s in enumerate(order)}
    shared = {}
    for members in CLUSTERS.values():
        if slug in members:
            for other in members:
                if other != slug:
                    shared[other] = shared.get(other, 0) + 1
    ranked = sorted(shared, key=lambda s: (-shared[s], order_index.get(s, 1 << 30)))
    return ranked[:limit]


RELATED_DIV_OPEN = ('<div id="related-episodes" style="margin-top: 48px; '
                    'padding-top: 28px; border-top: 1px solid #e0d9d0;">')


def render_related_inner(pairs, topics=()):
    """Inner HTML for the related-episodes div. `pairs` is [(slug, title), ...]
    of related episodes; `topics` is [(topic_slug, topic_name), ...] linking the
    episode's topic hub pages. Either may be empty."""
    if not pairs and not topics:
        return ''
    parts = []
    if pairs:
        items = '\n'.join(
            f'        <li><a href="/podcast/{s}.html" style="color: var(--color-accent); '
            f'text-decoration: none; font-weight: 600; font-size: 1.05rem;">{htmlmod.escape(t)}</a></li>'
            for s, t in pairs
        )
        parts.append(
            '      <p style="font-family: var(--font-mono); font-size: 0.72rem; text-transform: uppercase; '
            'letter-spacing: 0.12em; color: var(--color-muted); margin-bottom: 16px;">Related episodes</p>\n'
            '      <ul style="list-style: none; padding: 0; margin: 0; display: grid; gap: 12px;">\n'
            + items + '\n'
            '      </ul>\n'
        )
    if topics:
        chips = ' &nbsp;&middot;&nbsp; '.join(
            f'<a href="/podcast/topics/{ts}.html" style="color: var(--color-accent); '
            f'text-decoration: none;">{htmlmod.escape(name)}</a>'
            for ts, name in topics
        )
        margin = '24px 0 8px' if pairs else '0 0 8px'
        parts.append(
            '      <p style="font-family: var(--font-mono); font-size: 0.72rem; text-transform: uppercase; '
            f'letter-spacing: 0.12em; color: var(--color-muted); margin: {margin};">Topics</p>\n'
            f'      <p style="font-size: 1rem; margin: 0;">{chips}</p>\n'
        )
    return '\n' + ''.join(parts) + '    '


def render_author_bio():
    """The 'About the author' E-E-A-T block shown at the foot of every article."""
    return (
        f'    <section {AUTHOR_BIO_MARKER} aria-label="About the author" '
        'style="margin-top: 56px; padding-top: 32px; border-top: 1px solid #e0d9d0; '
        'display: flex; gap: 24px; align-items: flex-start; flex-wrap: wrap;">\n'
        '      <img src="/images/perry-wilson.webp" alt="F. Perry Wilson, MD MSCE" width="96" height="96" '
        'loading="lazy" decoding="async" style="width: 96px; height: 96px; border-radius: 50%; '
        'object-fit: cover; object-position: top; flex-shrink: 0;">\n'
        '      <div style="flex: 1; min-width: 240px;">\n'
        '        <p style="font-family: var(--font-mono); font-size: 0.72rem; text-transform: uppercase; '
        'letter-spacing: 0.12em; color: var(--color-muted); margin-bottom: 8px;">About the author</p>\n'
        '        <p style="font-size: 1rem; line-height: 1.7; margin: 0 0 12px;">'
        '<strong>F. Perry Wilson, MD MSCE</strong> is a nephrologist, clinical researcher, and Associate '
        'Professor of Medicine and Public Health at Yale University, where he directs the Clinical and '
        'Translational Research Accelerator. He hosts the <em>Wellness, Actually</em> podcast with Emily Oster, '
        'writes the weekly <em>Impact Factor</em> column on Medscape, and is the author of '
        '<em>How Medicine Works and When It Doesn&#x27;t</em> (Grand Central, 2023).</p>\n'
        '        <p style="font-size: 0.9rem; margin: 0;">'
        '<a href="/#about" style="color: var(--color-accent); text-decoration: none;">More about Dr. Wilson</a>'
        '&nbsp;&nbsp;&middot;&nbsp;&nbsp;'
        '<a href="https://scholar.google.com/citations?user=iB9er1AAAAAJ" target="_blank" rel="noopener noreferrer" '
        'style="color: var(--color-accent); text-decoration: none;">Google Scholar</a>'
        '&nbsp;&nbsp;&middot;&nbsp;&nbsp;'
        '<a href="https://www.ncbi.nlm.nih.gov/pubmed/?term=wilson+fp" target="_blank" rel="noopener noreferrer" '
        'style="color: var(--color-accent); text-decoration: none;">PubMed</a>'
        '</p>\n'
        '      </div>\n'
        '    </section>\n'
    )


# Excerpts of F. Perry Wilson's actual published prose (Medium, Medscape's
# "Impact Factor", the book), injected into the episode-generation system
# prompt by generate_episode_post.call_claude().
#
# Why this exists: the prompt used to convey voice with adjectives ("wry but
# not jokey", "confident without being arrogant"). Every model's reading of
# that converges on the same generic house style, which is how the sun
# episode's article ended up with tics like "That's a behavior problem, not a
# carcinogen." Demonstrated voice carries far more signal than described voice.
#
# Keep this to roughly 800-1200 words total, 2-3 excerpts. More than that
# starts crowding the transcript in the prompt. It lives in the system prompt,
# which is stable across runs, so it costs effectively nothing per run.
#
# Empty is a valid state: the block is omitted from the prompt entirely.
VOICE_SAMPLES = """[Sample 1 - from an article on GLP-1 weight loss drugs]

I’m really the last person to call something a miracle drug, but when it comes to
the new weight loss drugs (formally the GLP-1 receptor agonists like Ozempic) I’m
hard-pressed to think of a different term. Remember, these were designed as diabetes
drugs. They were supposed to lower blood sugar. And they do. But it turned out they
had profound effects on appetite, leading to substantial weight loss in the range of
10–20% of body weight. And I feel a bit like a late-night infomercial host here,
because whenever I talk about these drugs I’m like “and that’s not all”. Studies have
also shown that they curb other appetites. People taking them are more likely to quit
smoking, drinking, and gambling. They do less compulsive shopping even.

[Sample 2 - from an article on ultra-processed foods]

If you have any interest at all in nutrition and have been conscious over the past
five years or so, you are no doubt aware of a torrent of literature blaming a lot of
health woes on ultra-processed foods. Because in general, ultra-processed foods are
really bad for you. But maybe not entirely for the reason you think. It’s simpler
than that.

The reason ultra-processed foods are so bad for us is that they are easier to eat.
These additives? They include chemicals to keep the food fresh longer, so it stays
soft if it’s supposed to be soft, crunchy if it’s supposed to be crunchy. They add
salts, spices, and oils that are delicious. Grains that have been stripped of fiber
so that they are easier to chew and have a better mouthfeel. These are all designed
by very smart scientists to be highly delicious, and easy to eat.

[Sample 3 - from an article on one-leg stand time as a marker of biological aging]

So I was lying in bed the other night, trying to read my phone, and started
complaining to my wife about how my vision keeps getting worse, and then how stiff I
feel when I wake up in the morning, and how a recent injury is taking too long to
heal and she said “well, yeah, you’re 44. That’s when things start to head downhill.”

And I was like “44? That seems very specific. I thought 50 was what people complain
about”. And she said, “no, it’s a thing. 44 years old and 60 years old. There’s a
drop off there.”

And you know what? She was right.

This study, published in Nature Aging in August of 2024 analyzed a ton of proteins
and metabolites in people of various ages and found, when you put it all together,
that there are some big changes in body chemistry over time, and those changes peak
at age 44 and age 60. I should know better than to doubt my brilliant spouse.

But deep down, I believe the cliché that age is just a number. I don’t particularly
care about being 44, or turning 50, or 60. I care about how my body and brain are
aging. If I can be a happy, healthy, 80-year-old in full command of his faculties I
would consider that a major win no matter what the calendar says.

So I’m always interested in ways to quantify how my body is aging, independent of how
many birthdays I have passed. And, according to a new study, there is actually a
really easy way to do this.

Just stand on one leg.
"""
