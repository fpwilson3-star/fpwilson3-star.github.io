# fperrywilson.com

Personal website for F. Perry Wilson, MD MSCE — Yale physician, researcher, and
science communicator. Host of the *Wellness, Actually* podcast and author of
*How Medicine Works and When It Doesn't* (Grand Central, 2023).

Static site served from the `main` branch via GitHub Pages at the apex domain
`fperrywilson.com`. No build step; push to `main` and changes go live.

## Layout

- `index.html` — single-page site (hero, about, podcast, book, writing, media, lab, course)
- `podcast/` — standalone episode articles and their index
- `podcast/rss.xml` — RSS 2.0 feed for the episode articles
- `css/style.css` — editorial/magazine styling
- `js/episodes.js` — prev/next nav for episode pages (server-rendered, JS refresh)
- `images/` — self-hosted assets (favicon, OG images, covers, headshot)
- `scripts/` — Python utilities (see below)
- `sitemap.xml`, `robots.txt`, `CNAME` — standard SEO/hosting files
- `CLAUDE.md` — context for Claude Code when editing this repo

## Scripts

- `scripts/generate_episode_post.py` — turn a podcast transcript into a published episode page
- `scripts/build_rss.py` — regenerate `podcast/rss.xml` from the current episode list
- `scripts/upgrade_episodes_seo.py` — one-shot SEO upgrade already applied to all episode pages

## Common updates

See `CLAUDE.md` for details on adding a media appearance, updating bio copy,
or publishing a new episode article.
