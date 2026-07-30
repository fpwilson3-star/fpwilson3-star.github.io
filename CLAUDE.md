# F. Perry Wilson — Personal Website

## Overview
Static personal website hosted on GitHub Pages. Canonical domain is
`https://fperrywilson.com` (apex, no `www`). The repo's `CNAME` file controls
this. Previously at methodsman.com (which now redirects here).

## Site Structure
```
index.html          — Single-page site with all sections
css/style.css       — All styles (editorial/magazine aesthetic)
images/             — Local images (OG images, covers, headshot)
podcast/            — One SEO article per episode + index.html listing + rss.xml
podcast/topics/     — Auto-generated topic hub pages (one per CLUSTERS topic) +
                      index.html; built from episode_blocks.CLUSTERS/TOPIC_META
                      by scripts/build_topic_pages.py. Never hand-edit.
js/episodes.js      — EPISODES array (oldest-first); source of truth for episode order
transcripts/        — Episode transcripts; pushing one triggers article generation
scripts/            — generate_episode_post.py, build_rss.py, build_llms_txt.py,
                      prerender_nav.py,
                      check_site.py, episode_blocks.py (shared AEO fragments:
                      enriched author schema, "Short answer" box, author-bio
                      block, and the topic-CLUSTERS map + related-episodes logic
                      — imported by the generator, prerender_nav, and the
                      retrofits so they can't drift; also the shared Article
                      JSON-LD builder with isPartOf/mainEntityOfPage/inLanguage
                      + the body-derived citation list), retrofit_episode_links.py
                      (idempotent: adds episode-specific Apple links +
                      PodcastEpisode schema to any episode page missing them;
                      title-first matching),
                      retrofit_author_aeo.py (idempotent: adds the "Short answer"
                      / author-bio / author-@id AEO blocks to any page missing
                      them; its Short answer fallback copies the meta
                      description, so rewrite it afterwards, see below),
                      backfill_short_answers.py (one-time: the hand-written
                      answer-shaped "Short answer" text for each existing page), retrofit_page_head.py (idempotent: adds the GA4
                      snippet, the font preconnect/stylesheet links, and
                      VideoObject JSON-LD for embeds to any page missing them,
                      and repairs a meta description truncated by an unescaped
                      double quote), retrofit_article_seo.py (idempotent: rebuilds each
                      page's Article JSON-LD through the shared builder, adding
                      isPartOf/mainEntityOfPage/inLanguage + a citation list of
                      the body's study links, preserving datePublished/Modified),
                      build_podcast_index_schema.py (regenerates the podcast
                      index CollectionPage → ItemList of every article,
                      newest-first), build_topic_pages.py (generates the
                      /podcast/topics/ hub pages + index from the CLUSTERS/
                      TOPIC_META map, regenerates the "Browse by topic" strip on
                      podcast/index.html, adds topic links to each episode's
                      related block via prerender_nav, and keeps topic URLs in
                      sitemap.xml with lastmod = newest member article's date),
                      build_home_articles.py (writes the homepage's recent-article
                      cards + topic strip into the HOME-ARTICLES markers in the
                      #podcast section, and bumps the `/` sitemap lastmod only
                      when that block actually changes)
.github/workflows/  — generate-episode-post.yml (transcript → article PR),
                      update-podcast.yml (weekly latest-episode box, then
                      re-runs build_home_articles.py),
                      site-checks.yml (runs check_site.py on every push/PR)
sitemap.xml         — All pages; episode entries added by the generator
llms.txt            — Site map for LLMs/answer engines (llmstxt.org); generated
                      from the episode list by scripts/build_llms_txt.py
CLAUDE.md           — This file (Claude Code context)
```

## Sitemap freshness policy
`<lastmod>` must reflect real content changes — Google trusts the field only
when it is consistently truthful, so never bump dates artificially. Automation
keeps it honest: the episode generator stamps each new article and bumps
`/podcast/`, and update-podcast.yml bumps `/` when the weekly latest-episode
box changes. The one manual case: when substantively editing an existing
episode page, also update its sitemap `<lastmod>` and the page's JSON-LD
`dateModified` to the edit date.

## Validation — run after touching anything under /podcast/
`python scripts/check_site.py` verifies every episode page is consistently
listed in podcast/index.html, js/episodes.js, sitemap.xml, podcast/rss.xml, and
llms.txt;
that dates match everywhere and are not in the future; that every page has a
visible FAQ exactly matching its FAQPage schema; that each page carries the AEO
blocks (a "Short answer" box, an "About the author" block, an Article author
tied to the homepage Person @id, a fresh related-episodes block, and the
Article's isPartOf/mainEntityOfPage/inLanguage plus a citation list matching the
body's study links); that the podcast index CollectionPage enumerates every
article as an ItemList newest-first; that the topic hub pages, /podcast/topics/
index, "Browse by topic" strip, and topic sitemap entries match what
build_topic_pages.py would generate from CLUSTERS/TOPIC_META; that every page
site-wide carries the GA4 snippet and font links, has no meta description
truncated by an unescaped double quote, and pairs any YouTube embed with
VideoObject schema (fix with `retrofit_page_head.py`); and that the
homepage recent-articles block matches what build_home_articles.py would
generate and links no missing article; and that the
pre-rendered prev/next nav matches the chain in js/episodes.js. CI runs it on
every push to main and every PR, so a broken state fails loudly — run it locally
first.

## Sections (in order)
1. **Hero** — Name, title, photo, tagline
2. **About** (#about) — Bio, credentials, education
3. **Podcast** (#podcast) — Wellness, Actually with Emily Oster (iHeartMedia)
4. **Book** (#book) — How Medicine Works and When It Doesn't (Grand Central, 2023)
5. **Writing** (#writing) — Medium articles via RSS feed (auto-loaded from `medium.com/feed/@fperrywilson`)
6. **Media** (#media) — Selected TV/radio/podcast appearances (most recent 10)
7. **Lab** (#lab) — CTRA at Yale with link to Yale site
8. **Course** (#course) — Coursera course: "Understanding Medical Research: Your Facebook Friend Is Wrong"

## The "Short answer" box must answer
Each episode page opens with a visible "Short answer" box. It is the single most
extractable block on the page for AI answers and featured snippets, so it has
to **state the verdict**, not tease it. Originally every box was a verbatim copy
of the page's meta description, which defeated the purpose: a description is
written to earn a click ("Here's what the randomized trials actually show...")
where this box has to give the answer ("Yes for muscle, no for memory...").

The generator gets it from the model's dedicated `short_answer` field (hard-fails
if absent) and it is em-dash-stripped like the rest of the copy. Existing pages
were rewritten by `scripts/backfill_short_answers.py`, whose per-slug text is
drawn from each article's own bottom-line section — the box must never assert
something the body doesn't. `check_site.py` fails if any box is a verbatim copy
of its meta description.

## Surfacing articles on the homepage
The homepage is the site's highest-authority page and where people land after
googling the host's name, so `#podcast` carries a `HOME-ARTICLES` marker block
(written by `scripts/build_home_articles.py`) with three parts: a "Read the
evidence" link for the latest episode, cards for the newest 3 articles, and a
strip linking all 9 topic hubs. The hub strip is what keeps the older articles
linked from the homepage as the card list rotates past them.

Two things can invalidate the block independently, so **both** rebuild it: the
episode generator (a new article changes the newest 3) and update-podcast.yml (a
new episode changes which article "Read the evidence" should point at). The
block deliberately sits *outside* the `LATEST-EPISODE` markers, because
update-podcast.yml rewrites those wholesale and would clobber anything inside.

The episode→article match is on the episode title in each article's
`PodcastEpisode` JSON-LD. When there's no exact match — an episode that aired
before its article exists — the link is omitted rather than guessed, same rule
as the video embeds. `check_site.py` fails if the block is stale or links a
slug that doesn't exist.

## Analytics
GA4 (`G-8Q905DBDJR`) must be on **every** page, not just the homepage. Episode
pages, topic hubs, and the podcast index shipped without it for a while, which
made all the SEO/AEO work unmeasurable — search traffic landed on articles and
never showed up in analytics. The snippet lives once in
`episode_blocks.ANALYTICS_SNIPPET`, is emitted by the episode generator and
`build_topic_pages.py`, and `check_site.py` fails if any page lacks it.

## Design System
- **Fonts**: Playfair Display (display/headings), Source Sans 3 (body), JetBrains Mono (labels).
  Loaded by a `<link rel="stylesheet">` in each page's `<head>`
  (`episode_blocks.FONT_CSS_URL`), **not** by `@import` in style.css — an
  `@import` isn't discoverable until the stylesheet parses, serializing
  HTML → style.css → font CSS → font files. Change the URL in one place only.
- **Colors**: Warm off-white background (#faf9f6), terracotta accent (#b44a2d), dark ink (#1a1a1a)
- **CSS variables** are all defined in `:root` in style.css
- Responsive breakpoints at 900px and 640px
- Mobile hamburger nav

## Common Update Tasks

### Add a media appearance
In `index.html`, find the `<div class="media-list">` section. Add a new `.media-item` div at the TOP of the list (newest first). Remove the oldest one at the bottom to keep ~10 items. Format:
```html
<div class="media-item">
  <span class="media-date">Mon DD, YYYY</span>
  <div>
    <div class="media-outlet">Outlet Name</div>
    <p class="media-description">Brief description of the appearance.</p>
  </div>
</div>
```

### Update bio/about text
Edit the `.about-text` div in the #about section of index.html.

### Update podcast links or description
Edit the #podcast section. Podcast links: Apple, Spotify, iHeart.

### Add images locally
Put them in `images/` and reference with relative paths.

### Hosting
- GitHub Pages serves from the `main` branch root
- Push to main and changes go live automatically
- Domain: fpwilson3-star.github.io (with future CNAME for methodsman.com if desired)

## Transcript to Article Workflow

**The transcript filename sets the article date.** Name transcripts
`YYYY-MM-DD-topic.txt` using the episode air date — that date becomes the
article's published_time, JSON-LD dates, byline, sitemap lastmod, and RSS
pubDate. A wrong year once shipped an article dated 2025 instead of 2026; the
generator now refuses dates more than 90 days old or 14 days in the future
(`--allow-odd-date` overrides). Don't rename an already-merged transcript —
any push touching `transcripts/*.txt` re-triggers generation and will open a
duplicate-article PR. To re-run generation deliberately, use the workflow's
manual "Run workflow" button (workflow_dispatch) instead.

There are two paths into this workflow, and both must source hyperlinks from the same place:

- **Automated path (default).** When a transcript is pushed to `transcripts/`, the GitHub Action `.github/workflows/generate-episode-post.yml` runs `scripts/generate_episode_post.py`. That script (a) fetches the vetted episode SCRIPT doc from Google Drive via service-account credentials, (b) passes the script content into a single Anthropic API call, and (c) instructs the model to use ONLY those URLs for hyperlinks. If Drive is unavailable or no script is found, the article ships without hyperlinks rather than guessing.
- **Interactive path.** When a human asks Claude Code to write or fix an article, follow the same rule: pull the SCRIPT from Drive, use only its URLs, and never WebSearch or guess. Mislinks on a doctor's site are worse than missing links.

Steps either way:

1. **Fetch the episode SCRIPT from Google Drive** (see structure below). It has pre-sourced URLs for every study, trial, and clip discussed.
2. Identify every specific study mentioned in the transcript (by finding, paper, trial name, or author).
3. For each study, look it up in the SCRIPT. If found, link the relevant phrase inline using its URL. If not found, leave it as plain text.
4. **Never fabricate, guess, or WebSearch for URLs.** Trust on this site depends on every link being one the host vetted.

### The transcript is the only content source. The SCRIPT is a link lookup.

The transcript is what was said on air. The Drive SCRIPT is a planning doc
written *before* the episode: it lists what the hosts intended to cover, which
is not always what they said or concluded. It also contains the ad read, the
cold open, and the whole health-news roundup. **Every claim, number, framing,
and section of an article comes from the transcript. The SCRIPT supplies URLs
and nothing else.** If a study appears in the SCRIPT but not in the transcript,
it does not go in the article, not even as background.

This was violated silently for a long time. The whole SCRIPT was pasted into the
prompt under a heading about hyperlinks, with no rule saying it wasn't source
material, and it is a clean article-shaped outline sitting next to a messy
conversation. The sun episode made it visible: the generated article cited the
Nambour trial four times and described UVB hitting "tumor suppressor" genes, and
none of that is anywhere in the transcript. Emphasis was inverted too, with the
transcript saying "vitamin D" 67 times to sunscreen's 48 while the article did
the reverse, mirroring the SCRIPT's sunscreen-heavy Deep Dive.

Three things now keep the boundary, and they are load-bearing together:

- The transcript leads the prompt and is labeled the only content source; the
  SCRIPT follows as a demoted appendix with explicit "not a content source"
  rules (planning doc, transcript wins on conflict, don't import unmentioned
  studies, don't take emphasis or phrasing from it).
- `extract_link_context()` passes only the SCRIPT lines that carry a URL, so the
  importable prose is not in the prompt at all. It is **line-scoped on purpose**:
  a character window wide enough to identify the tanning-bed study also swallowed
  the UVB/UVA mechanism paragraph directly above it (at 300 chars, 76% of the doc
  survived and every leak with it). Line-scoped keeps ~30% and all URLs.
- `validate_links()` still checks hrefs against the **full** SCRIPT text, so
  trimming what the model sees never weakens link enforcement.

Note the appendix keeps each linked study's own findings on its line, since a
URL can't be matched to a study without naming it. That is intended: the guard
against importing it is that the transcript must have discussed it.

The generator script enforces the link rule mechanically: every `href` in the
generated article must appear verbatim in the Drive SCRIPT text (zero links
allowed if no script was found), or the run fails. It also hard-fails on
truncated model output and missing FAQs, strips em-dashes, warns on
off-length meta descriptions, replaces (rather than duplicates) entries on
re-runs, and looks up the episode's Apple Podcasts URL via the iTunes API
(same one update-podcast.yml uses) to link each article to its specific
episode and emit `PodcastEpisode` JSON-LD. It also has the model pick the 1-2
best-fitting topic categories (from the fixed `CLUSTERS`/`TOPIC_META` list)
and writes the new slug into `CLUSTERS` in `scripts/episode_blocks.py` itself
(replacing any prior assignment on re-runs), so the episode PR includes the
hub-page updates; a run with no valid topic hard-fails. When editing articles
by hand, honor the same rules.

### Episode video embeds

The generator also embeds the episode's YouTube discussion automatically
(`fetch_episode_video` / `insert_video_embed`), so pushing a transcript
produces a page with the video already in it. **Upload the YouTube video
before pushing the transcript** — the lookup only sees what is already on the
channel at generation time, and there is no follow-up sweep.

It reads the host's channel feed
(`youtube.com/feeds/videos.xml?channel_id=UCu4OHd94MHqjlMp_Mgks84w`, no API
key needed), keeps only uploads whose title contains "Wellness, Actually"
(the channel also posts near-daily short clips that mention the same topics),
and matches on topic-word overlap with the episode title. Two deliberate
choices:

- **Dates are ignored.** The feed reports wrong publish dates for some
  uploads (the alcohol episode comes back as 2015), so a date-proximity match
  like `fetch_episode_link`'s would pick the wrong video or none at all.
- **It skips rather than guesses.** Below 50% topic overlap, or on a tie
  between two episodes, it ships the article with no embed and says so in the
  run log. Same rule as the hyperlinks: a wrong video is worse than none.

If an embed is missing, check the `[video]` lines in the generate-run log.
The usual cause is the video not being on the channel yet when the transcript
was pushed; fix it by adding the block by hand (copy it from any other
episode page) or re-running the workflow via its "Run workflow" button.
`insert_video_embed` is idempotent, so a re-run will not double up.

### Google Drive episode scripts

Episode scripts live in a shared Google Drive folder. Drive structure:

```
14. Wellness, Actually
  └── 1. EPISODES          (folder id: 1qhx8vF3m6Gd9eYUEntLoeAtaVgZ7N-Si)
        └── [##. M.D.YY - Topic]   (e.g. "8. 4.2.26- Creatine", "14. 5.14.26 - Psychedelics")
              └── [Topic] - SCRIPT     ← inline links are here
```

To find the script for an episode:
1. Find the episode folder by searching the EPISODES folder for a name containing the date string `M.D.YY` (e.g. `5.14.26`) or the topic word.
2. Inside that folder, find the doc whose name contains `SCRIPT` (it's a Google Doc; export as `text/plain` to read URLs as-is).
3. The script also contains news-item links, social posts, and other context. Those are fine to use too, but everything else stays in the script, not in the repo.

The GitHub Action authenticates to Drive via a Google Cloud service account whose JSON key is stored in the `GOOGLE_DRIVE_CREDENTIALS` repo secret. The service account email must be granted Viewer access to the EPISODES folder.

### Episode page HTML template

Each episode page `<head>` must include the full SEO block below. Replace `{{TITLE}}`, `{{DESCRIPTION}}`, `{{SLUG}}`, and `{{DATE}}` (format: YYYY-MM-DD) for each article.

The generation call uses **Opus 5** (`claude-opus-5`) with adaptive thinking, a
32k `max_tokens` budget, and **streaming** (`client.messages.stream(...)` +
`get_final_message()`). Three coupled reasons, so don't change one in isolation:
thinking is set explicitly because the default flipped between model generations
(omitting it meant "off" on Opus 4.8 and "adaptive" on Opus 5); `max_tokens`
caps thinking *plus* output together, so it has to be larger than the old 16k;
and above roughly 16k a non-streaming request risks an SDK HTTP timeout. A
truncated response still hard-fails loudly rather than shipping half an article.

Model-written text (headline, meta description) must be escaped with
`generate_episode_post.attr()` before it goes into an HTML attribute. A raw `"`
in the text — the "Wolverine stack" peptide episode hit this — terminates the
attribute early and silently truncates the description Google reads. JSON-LD is
safe because every block is built through `json.dumps`.

The generator script also produces a visible FAQ section (collapsible `<details>`) and a matching `FAQPage` JSON-LD block, grounded in the article body. Question text in the visible section must exactly match `mainEntity[*].name` in the schema — that parity is required for Google FAQ rich-result eligibility.

```html
<title>{{TITLE}} | F. Perry Wilson, MD</title>
<meta name="description" content="{{DESCRIPTION}}">
<meta name="author" content="F. Perry Wilson">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="[FONT_CSS_URL from scripts/episode_blocks.py]">
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="apple-touch-icon" href="/images/apple-touch-icon.png">
<link rel="alternate" type="application/rss+xml" title="Wellness, Actually — Episode Articles" href="/podcast/rss.xml">
<!-- Google tag (gtag.js) — required on every page; see episode_blocks.ANALYTICS_SNIPPET -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-8Q905DBDJR"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-8Q905DBDJR');
</script>
<link rel="stylesheet" href="../css/style.css">
<link rel="canonical" href="https://fperrywilson.com/podcast/{{SLUG}}.html">
<meta property="og:title" content="{{TITLE}}">
<meta property="og:description" content="{{DESCRIPTION}}">
<meta property="og:type" content="article">
<meta property="og:url" content="https://fperrywilson.com/podcast/{{SLUG}}.html">
<meta property="og:site_name" content="F. Perry Wilson, MD">
<meta property="og:image" content="https://fperrywilson.com/images/og-podcast.jpg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="Wellness, Actually podcast — with Emily Oster and F. Perry Wilson, MD">
<meta property="article:published_time" content="{{DATE}}">
<meta property="article:author" content="https://fperrywilson.com">
<meta property="article:section" content="Health">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:site" content="@fperrywilson">
<meta name="twitter:creator" content="@fperrywilson">
<meta name="twitter:title" content="{{TITLE}}">
<meta name="twitter:description" content="{{DESCRIPTION}}">
<meta name="twitter:image" content="https://fperrywilson.com/images/og-podcast.jpg">
<meta name="twitter:image:alt" content="Wellness, Actually podcast — with Emily Oster and F. Perry Wilson, MD">
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Article",
  "headline": "{{TITLE}}",
  "datePublished": "{{DATE}}",
  "dateModified": "{{DATE}}",
  "image": "https://fperrywilson.com/images/og-podcast.jpg",
  "author": {"@type": "Person", "@id": "https://fperrywilson.com/#person", "name": "F. Perry Wilson", "honorificSuffix": "MD MSCE", "jobTitle": "Associate Professor of Medicine and Public Health", "affiliation": {"@type": "Organization", "name": "Yale University"}, "url": "https://fperrywilson.com", "sameAs": ["https://scholar.google.com/citations?user=iB9er1AAAAAJ", "https://www.ncbi.nlm.nih.gov/pubmed/?term=wilson+fp", "https://twitter.com/fperrywilson"]},
  "publisher": {"@type": "Person", "@id": "https://fperrywilson.com/#person", "name": "F. Perry Wilson", "url": "https://fperrywilson.com"},
  "description": "{{DESCRIPTION}}",
  "url": "https://fperrywilson.com/podcast/{{SLUG}}.html",
  "mainEntityOfPage": "https://fperrywilson.com/podcast/{{SLUG}}.html",
  "inLanguage": "en-US",
  "isPartOf": {"@type": "CollectionPage", "name": "Wellness, Actually — Episode Articles", "url": "https://fperrywilson.com/podcast/"},
  "citation": [{"@type": "CreativeWork", "url": "<each vetted study URL linked in the body>"}]
}
</script>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "BreadcrumbList",
  "itemListElement": [
    {"@type": "ListItem", "position": 1, "name": "Home", "item": "https://fperrywilson.com"},
    {"@type": "ListItem", "position": 2, "name": "Episode Articles", "item": "https://fperrywilson.com/podcast/"},
    {"@type": "ListItem", "position": 3, "name": "{{TITLE}}", "item": "https://fperrywilson.com/podcast/{{SLUG}}.html"}
  ]
}
</script>
```

### After publishing a new episode page

`scripts/generate_episode_post.py` does all of this automatically. When
creating or editing an episode page by hand:

1. Add it to `podcast/index.html` inside `<!-- EPISODES-START -->` (newest first, with a `data-date` attribute)
2. Add it to `sitemap.xml` with `<changefreq>yearly</changefreq>` and the correct `<lastmod>` date; bump the `/podcast/` entry's `<lastmod>` too
3. Add it to `js/episodes.js` EPISODES array (oldest-first order) — the source of truth for prev/next nav
4. Run `python scripts/prerender_nav.py` — bakes the prev/next nav into every page's `<div id="episode-nav">` and stamps the `<div id="related-episodes">` block from the topic clusters in `episode_blocks.py`, so crawlers follow the links without JS. This also updates the previously-newest page (whose nav otherwise dead-ends at "Newest article") and any related blocks whose recency tiebreak shifted. To change which episodes are "related," edit `CLUSTERS` in `scripts/episode_blocks.py` and re-run this.
5. Run `python scripts/build_rss.py` to regenerate `podcast/rss.xml`
6. Run `python scripts/build_llms_txt.py` to regenerate `llms.txt`
7. Run `python scripts/build_podcast_index_schema.py` to refresh the podcast index CollectionPage → ItemList
8. Run `python scripts/retrofit_article_seo.py` to add the Article isPartOf/mainEntityOfPage/inLanguage + citation list (the hand-written template above already includes these; the retrofit is the safety net), then `python scripts/retrofit_page_head.py` for the GA4 snippet, font links, and VideoObject schema
9. Run `python scripts/build_home_articles.py` to refresh the homepage's recent-article cards, then `python scripts/build_topic_pages.py` to regenerate the topic hub pages, the "Browse by topic" strip, and the topic sitemap entries. When hand-writing a page, first add its slug to 1-2 lists in `CLUSTERS` (`scripts/episode_blocks.py`) — the automated generator does this itself via the model's topic pick, and every episode should be in at least one cluster. Adding a whole new topic means adding a matching entry to both `CLUSTERS` and `TOPIC_META`.
10. Run `python scripts/check_site.py` — must pass before committing (CI enforces it)

The generator (`generate_episode_post.py`) runs steps 4–9 automatically after writing a new article, so a pushed transcript refreshes the hubs, index, feeds, and schema with no manual step.

## Key Links
- Medium: https://fperrywilson.medium.com/
- Medscape: https://www.medscape.com/index/list_12471_0
- CTRA: https://medicine.yale.edu/internal-medicine/ctra/
- Coursera: https://www.coursera.org/learn/medical-research
- Book: https://www.amazon.com/How-Medicine-Works-When-Doesnt/dp/1538723603
- Podcast (Apple): https://podcasts.apple.com/us/podcast/wellness-actually-with-emily-oster-perry-wilson-md/id1633515294
- Podcast (Spotify): https://open.spotify.com/show/5igTryEwHMmAJfODAFKp3W
- Twitter/X: https://twitter.com/fperrywilson
- Contact: francis.p.wilson@yale.edu
