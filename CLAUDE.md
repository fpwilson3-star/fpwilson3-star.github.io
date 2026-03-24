# F. Perry Wilson — Personal Website

## Overview
This is a static personal website hosted on GitHub Pages at `fpwilson3-star.github.io`. 
Previously at methodsman.com (which now redirects here).

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
