(function () {
  // Add new episodes here (oldest first). Nav links update automatically on all pages.
  const EPISODES = [
    { slug: 'are-sperm-counts-really-declining',           title: 'Are sperm counts really declining?' },
    { slug: 'do-peptide-injections-actually-work',         title: 'Do peptide injections actually work?' },
    { slug: 'cold-plunges-saunas-health-benefits',         title: 'Do cold plunges and saunas work?' },
    { slug: 'glp-1-weight-loss-evidence',                  title: 'GLP-1s for weight loss' },
    { slug: 'does-red-light-therapy-actually-work',        title: 'Does red light therapy work?' },
    { slug: 'are-microplastics-actually-harming-your-health', title: 'Are microplastics harming your health?' },
    { slug: 'do-stem-cell-injections-actually-work',       title: 'Do stem cell injections work?' },
    { slug: 'does-creatine-actually-work',                 title: 'Does creatine actually work?' },
    { slug: 'how-much-protein-do-you-actually-need',       title: 'How much protein do you need?' },
    { slug: 'does-hormone-replacement-therapy-actually-work', title: 'Does hormone replacement therapy actually work? What the evidence says in 2026' },

  ];

  const linkStyle = 'font-family:var(--font-mono);font-size:0.85rem;color:var(--color-accent);text-decoration:none;';
  const mutedStyle = 'font-family:var(--font-mono);font-size:0.85rem;color:var(--color-muted);';

  document.addEventListener('DOMContentLoaded', function () {
    const nav = document.getElementById('episode-nav');
    if (!nav) return;

    const slug = location.pathname.replace(/^\/podcast\//, '').replace(/\.html$/, '');
    const idx = EPISODES.findIndex(function (e) { return e.slug === slug; });
    if (idx === -1) return;

    const prev = EPISODES[idx - 1];
    const next = EPISODES[idx + 1];

    const prevHTML = prev
      ? '<a href="/podcast/' + prev.slug + '.html" style="' + linkStyle + '">← ' + prev.title + '</a>'
      : '<span style="' + mutedStyle + '">Oldest article</span>';

    const nextHTML = next
      ? '<a href="/podcast/' + next.slug + '.html" style="' + linkStyle + '">' + next.title + ' →</a>'
      : '<span style="' + mutedStyle + '">Newest article</span>';

    nav.innerHTML = prevHTML
      + '<a href="/podcast/" style="' + mutedStyle + '">All articles</a>'
      + nextHTML;
  });
})();
