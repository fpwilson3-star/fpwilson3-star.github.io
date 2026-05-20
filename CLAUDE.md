# F. Perry Wilson — Personal Website

## Overview
Static personal website hosted on GitHub Pages. Canonical domain is
`https://fperrywilson.com` (apex, no `www`). The repo's `CNAME` file controls
this. Previously at methodsman.com (which now redirects here).

## Site Structure
```
index.html          — Single-page site with all sections
css/style.css       — All styles (editorial/magazine aesthetic)
images/             — Local images (if any added later)
CLAUDE.md           — This file (Claude Code context)
```

## Sections (in order)
1. **Hero** — Name, title, photo, tagline
2. **About** (#about) — Bio, credentials, education
3. **Podcast** (#podcast) — Wellness, Actually with Emily Oster (iHeartMedia)
4. **Book** (#book) — How Medicine Works and When It Doesn't (Grand Central, 2023)
5. **Writing** (#writing) — Medium articles via RSS feed (auto-loaded from `medium.com/feed/@fperrywilson`)
6. **Media** (#media) — Selected TV/radio/podcast appearances (most recent 10)
7. **Lab** (#lab) — CTRA at Yale with link to Yale site
8. **Course** (#course) — Coursera course: "Understanding Medical Research: Your Facebook Friend Is Wrong"

## Design System
- **Fonts**: Playfair Display (display/headings), Source Sans 3 (body), JetBrains Mono (labels)
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

There are two paths into this workflow, and both must source hyperlinks from the same place:

- **Automated path (default).** When a transcript is pushed to `transcripts/`, the GitHub Action `.github/workflows/generate-episode-post.yml` runs `scripts/generate_episode_post.py`. That script (a) fetches the vetted episode SCRIPT doc from Google Drive via service-account credentials, (b) passes the script content into a single Anthropic API call, and (c) instructs the model to use ONLY those URLs for hyperlinks. If Drive is unavailable or no script is found, the article ships without hyperlinks rather than guessing.
- **Interactive path.** When a human asks Claude Code to write or fix an article, follow the same rule: pull the SCRIPT from Drive, use only its URLs, and never WebSearch or guess. Mislinks on a doctor's site are worse than missing links.

Steps either way:

1. **Fetch the episode SCRIPT from Google Drive** (see structure below). It has pre-sourced URLs for every study, trial, and clip discussed.
2. Identify every specific study mentioned in the transcript (by finding, paper, trial name, or author).
3. For each study, look it up in the SCRIPT. If found, link the relevant phrase inline using its URL. If not found, leave it as plain text.
4. **Never fabricate, guess, or WebSearch for URLs.** Trust on this site depends on every link being one the host vetted.

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

The generator script also produces a visible FAQ section (collapsible `<details>`) and a matching `FAQPage` JSON-LD block, grounded in the article body. Question text in the visible section must exactly match `mainEntity[*].name` in the schema — that parity is required for Google FAQ rich-result eligibility.

```html
<title>{{TITLE}} | F. Perry Wilson, MD</title>
<meta name="description" content="{{DESCRIPTION}}">
<meta name="author" content="F. Perry Wilson">
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="apple-touch-icon" href="/images/apple-touch-icon.png">
<link rel="alternate" type="application/rss+xml" title="Wellness, Actually — Episode Articles" href="/podcast/rss.xml">
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
  "author": {"@type": "Person", "name": "F. Perry Wilson", "url": "https://fperrywilson.com"},
  "publisher": {"@type": "Person", "name": "F. Perry Wilson", "url": "https://fperrywilson.com"},
  "description": "{{DESCRIPTION}}",
  "url": "https://fperrywilson.com/podcast/{{SLUG}}.html"
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
1. Add it to `podcast/index.html` inside `<!-- EPISODES-START -->` (newest first)
2. Add it to `sitemap.xml` with `<changefreq>yearly</changefreq>` and the correct `<lastmod>` date
3. Add it to `js/episodes.js` EPISODES array (oldest-first order) — powers the prev/next nav on all episode pages
4. Run `python scripts/build_rss.py` to regenerate `podcast/rss.xml`
5. Pre-render the prev/next nav server-side inside `<div id="episode-nav">` (see existing episode pages), so crawlers follow the internal links without running JS

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
