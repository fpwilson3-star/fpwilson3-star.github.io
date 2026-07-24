"""Replace each episode page's "Short answer" box with an actual answer.

Every existing box was a verbatim copy of the page's meta description, and
almost all of those descriptions are teasers ("Here's what the evidence
actually shows about...") rather than answers. That box is the single most
extractable thing on the page for answer engines and featured snippets, so a
teaser wastes it.

The replacements below are answer-first: verdict in the opening clause, then
the load-bearing specifics. Each one is drawn from its own article's
bottom-line section, so the box never asserts anything the page doesn't.

Also bumps each edited page's JSON-LD dateModified and its sitemap <lastmod>
to EDIT_DATE, per the sitemap freshness policy in CLAUDE.md -- this is a real
change to visible page content.

Idempotent: a page whose box already matches its entry here is left alone,
including its dates. One-time backfill; new articles get an answer-shaped box
from generate_episode_post.py's short_answer field.

Usage: python scripts/backfill_short_answers.py [--dry-run]
"""
import html as htmlmod
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import episode_blocks  # noqa: E402

EDIT_DATE = '2026-07-24'

SHORT_ANSWERS = {
    'are-full-body-scans-worth-it':
        "For healthy people, no. No major medical society recommends whole-body MRI "
        "screening, because it has never been shown in a randomized trial to save "
        "lives, and it surfaces incidental findings that trigger follow-up testing "
        "and anxiety. The screenings we do recommend, like mammography and colon "
        "cancer screening, earned their place with trials these companies haven't run.",

    'are-microplastics-actually-harming-your-health':
        "Probably not at current exposure levels. The lab evidence that plastic "
        "particles can provoke inflammation is solid, but the evidence that today's "
        "human exposures cause meaningful disease is weak and confounded, and the "
        "widely shared brain study hasn't been replicated. Cut single-use plastic for "
        "environmental reasons if you like; the health data don't justify losing sleep.",

    'are-sperm-counts-really-declining':
        "Yes, modestly, over the past 50 years, but the decline is overhyped and the "
        "usual social media culprits are not the cause. Cell phones, soy, and laptops "
        "are not driving it; obesity almost certainly is. For an individual man, sperm "
        "count matters when you're trying to conceive and not much otherwise.",

    'cold-plunges-saunas-health-benefits':
        "Saunas, plausibly. Cold plunges, no. The cardiovascular signal for sauna use "
        "is modest but real, and the quiet time is probably doing some of the work. The "
        "evidence that cold plunges deliver meaningful health benefits is thin and the "
        "safety concerns are real. Neither one detoxes you, cures a hangover, or "
        "replaces exercise.",

    'continuous-glucose-monitors-non-diabetics':
        "Not for any outcome that matters. CGMs are genuinely useful, sometimes "
        "transformative, in type 1 diabetes, type 2 diabetes, and prediabetes. In "
        "people without diabetes, mean glucose drops a little while you're watching and "
        "BMI doesn't budge. Fifty dollars for a two-week sensor out of curiosity is "
        "fine; a monthly subscription isn't buying much. A flat line at 90 is "
        "marketing, not a medical target.",

    'do-cupping-and-dry-needling-actually-work':
        "Cupping, essentially no. Dry needling, maybe. The best sham-controlled trial of "
        "cupping for low back pain found no benefit over fake cupping, and the "
        "\"toxins\" story is nonsense. Dry needling shows modest sham-controlled effects "
        "for shoulder pain and headache. Both carry real risks near the neck and upper "
        "chest, including collapsed lung.",

    'do-peptide-injections-actually-work':
        "Mostly no. FDA-approved peptide drugs like GLP-1s and insulin are real "
        "medicine, and collagen peptides have modest evidence for skin and joint pain. "
        "The injectable healing and longevity stacks sold on social media, BPC 157 "
        "included, rest on rat studies and testimonials, are often sourced illegally "
        "from overseas, and have no long-term safety data.",

    'do-psychedelics-actually-work':
        "Promising, not proven. Psilocybin for depression and MDMA or ibogaine for PTSD "
        "show genuinely encouraging results, but the trials are small, short, and hard "
        "to blind, so they don't yet overturn standard care. Microdosing doesn't appear "
        "to do much, and buying psychedelics on the street is a bad idea on several "
        "fronts.",

    'do-stem-cell-injections-actually-work':
        "No. What regenerative medicine clinics sell as \"stem cells\" is centrifuged fat "
        "or bone marrow containing effectively no stem cells, and the best randomized "
        "data show no benefit over saline. Real stem cell therapy is transformative for "
        "a small set of serious diseases like sickle cell, and it happens in hospitals "
        "under intensive supervision, not in strip-mall clinics.",

    'does-addyi-work-low-sexual-desire-women':
        "Barely. Addyi and Vyleesi produce real but small effects, often around half an "
        "extra satisfying sexual event per month, and they carry real downsides. The "
        "evidence for testosterone is at least as strong as the pink pill, with "
        "caveats. No drug fixes a relationship, and communication beats doing nothing "
        "with no side effects at all.",

    'does-bovine-colostrum-actually-work':
        "Probably not much. IGF-1 doesn't survive your gut, and the leaky gut claims "
        "don't hold up where they should matter most. Small trials hint at fewer upper "
        "respiratory infections and modest gains in elite cyclists, but they're "
        "vulnerable to publication bias. For most people, save the $50 a month, and "
        "skip the raw stuff entirely.",

    'does-creatine-actually-work':
        "Yes for muscle, no for memory. At 5 grams a day, creatine monohydrate is "
        "cheap, safe, and well studied for strength gains when paired with resistance "
        "training: expect a modestly higher bench press and a few pounds of water "
        "weight, not a transformation. The Alzheimer's and cognition claims don't hold "
        "up, and large randomized trials in Parkinson's and Huntington's were stopped "
        "for futility. It does not harm your kidneys.",

    'does-high-cortisol-cause-belly-fat':
        "No. There is no compelling evidence that a normal-range cortisol level causes "
        "belly fat, heart disease, or metabolic syndrome, and cortisol is hard to "
        "measure reliably in the first place. True cortisol excess looks distinctive: "
        "moon face, buffalo hump, purple abdominal stretch marks. Short of that, it "
        "isn't a useful wellness metric.",

    'does-hormone-replacement-therapy-actually-work':
        "Yes, for the symptoms it's meant to treat: hot flashes, night sweats, sleep "
        "disruption, vaginal dryness, and fracture risk. The Women's Health Initiative "
        "scared a generation of women and their doctors away from it, but the risks are "
        "smaller in absolute terms than the headlines suggested and depend heavily on "
        "age, route, and whether progesterone is included. For symptomatic women in "
        "their 40s and 50s it probably does more good than harm.",

    'does-methylene-blue-actually-work':
        "For a healthy adult, no. Methylene blue is a real drug with real uses in "
        "methemoglobinemia and cyanide poisoning, but the evidence that it improves "
        "energy, memory, or longevity is weak to nonexistent. Its strongest wellness "
        "claim, better mood, is a rediscovery of an antidepressant class we abandoned "
        "for good reasons, and it carries a small but real risk profile.",

    'does-red-light-therapy-actually-work':
        "Only for what sits near the surface. There is suggestive evidence for hair "
        "regrowth and possibly minor skin effects. For anything deeper than about five "
        "millimeters, including your brain, deep muscles, and hormones, the physics "
        "don't cooperate. Dosing across studies is wildly inconsistent, the placebo "
        "problem is serious, and the devices are drastically overpriced.",

    'does-testosterone-replacement-therapy-actually-work':
        "Only for a narrow group. TRT is worth considering if your testosterone is "
        "consistently below 300 ng/dL on more than one test and you have sexual "
        "symptoms that bother you; in that group the trials show real improvements in "
        "libido and erectile function. They show no meaningful gains in energy, mood, "
        "or cognition. Risks include small increases in atrial fibrillation and blood "
        "clots, plus reduced fertility.",

    'glp-1-weight-loss-evidence':
        "Yes, dramatically. GLP-1s produce weight loss at a scale medicine has never "
        "had outside bariatric surgery, and they appear to reduce obesity-driven "
        "disease. They also carry real side effects, require long-term use to maintain "
        "the benefit, and shouldn't be used to push people below a healthy weight. "
        "Treat them as serious medication, managed by someone who knows what they're "
        "doing.",

    'how-mrna-vaccines-work':
        "mRNA is a photocopied recipe your cells read and then throw away, not "
        "something to detox from. A vaccine uses it to have your own cells display one "
        "piece of a virus so your immune system learns to recognize it. The main real "
        "risk of the COVID vaccines, myocarditis in young men, is small and worth "
        "weighing against the disease. The same platform already halved recurrence in a "
        "melanoma cancer-vaccine trial.",

    'how-much-protein-do-you-actually-need':
        "Around 1.6 g/kg a day if you're lifting, older and preserving muscle, or on a "
        "GLP-1. Most people already get enough to avoid deficiency without trying. A "
        "gram per pound is overkill for a healthy person not doing serious resistance "
        "training, hitting higher targets usually takes a shake, and if you have kidney "
        "disease you should not chase them at all.",

    'how-much-sleep-do-you-need':
        "About seven hours for most adults, more if you train hard. Judge whether "
        "you're rested by how you feel during the day and whether you can wake at a "
        "normal hour when given the chance, not by a score on your wrist. If you're "
        "sleepy all day or your partner hears you stop breathing, get evaluated for "
        "sleep apnea. For months-long insomnia the strongest fix is CBT-I, not sleep "
        "hygiene and not a pill.",

    'is-moderate-drinking-actually-bad-for-you':
        "One drink a day is a modest risk, not a catastrophe. The clearest harms are "
        "blood pressure and sleep, both dose-dependent and small at low intake. The "
        "cancer signal is real but modest for moderate drinkers, with breast cancer the "
        "one to watch, and the heart-protection story is a myth built on confounding. A "
        "reasonable ceiling is two drinks a day.",

    'is-red-meat-actually-bad-for-you':
        "For unprocessed red meat, less bad than the headlines suggest. Swapping some "
        "saturated fat for unsaturated fat does lower LDL and probably nudges "
        "cardiovascular events down, but the mortality data isn't there, and the "
        "observational cancer signal is small enough that confounding can plausibly "
        "explain it. Processed red meat is the part actually worth cutting back on.",

    'pregnancy-brain-what-actually-changes':
        "Yes, measurably. Gray matter drops about 5% during pregnancy, verbal memory "
        "and processing speed dip while muscle memory and factual knowledge hold, and "
        "recognition may sharpen. Much of it recovers, but you don't get the exact same "
        "brain back. Screen for anemia and thyroid problems, and take postpartum "
        "depression and anxiety seriously rather than filing them under baby brain.",
}

_TLDR_BODY = re.compile(
    r'(' + re.escape(episode_blocks.TLDR_MARKER) +
    r'.*?<p style="font-size: 1\.1rem; line-height: 1\.6; margin: 0;">)(.*?)(</p>)', re.S)


def rewrite_page(slug, text, dry_run):
    page = Path(f'podcast/{slug}.html')
    if not page.exists():
        return 'SKIPPED: page does not exist'
    src = page.read_text(encoding='utf-8')
    m = _TLDR_BODY.search(src)
    if not m:
        return 'SKIPPED: no Short answer box found'
    want = htmlmod.escape(text.strip())
    if m.group(2) == want:
        return 'already done'
    src = src[:m.start()] + m.group(1) + want + m.group(3) + src[m.end():]
    # Visible content changed, so dateModified must move with it.
    src = re.sub(r'("dateModified": ")[\d-]{10}(")', rf'\g<1>{EDIT_DATE}\g<2>', src)
    if not dry_run:
        page.write_text(src, encoding='utf-8')
    return 'rewritten'


def bump_sitemap(slugs, dry_run):
    path = Path('sitemap.xml')
    src = path.read_text(encoding='utf-8')
    for slug in slugs:
        pat = re.compile(
            r'(<loc>https://fperrywilson\.com/podcast/' + re.escape(slug)
            + r'\.html</loc>\s*<lastmod>)[\d-]{10}(</lastmod>)')
        src, n = pat.subn(rf'\g<1>{EDIT_DATE}\g<2>', src)
        if not n:
            print(f'  WARNING: no sitemap entry for {slug}')
    if not dry_run:
        path.write_text(src, encoding='utf-8')


def main():
    dry_run = '--dry-run' in sys.argv
    changed = []
    for slug, text in sorted(SHORT_ANSWERS.items()):
        result = rewrite_page(slug, text, dry_run)
        if result == 'rewritten':
            changed.append(slug)
        print(f'  {slug}: {result}')
    if changed:
        bump_sitemap(changed, dry_run)
    print(f'\n{len(changed)} page(s) rewritten'
          f'{" (dry run, nothing written)" if dry_run else ""}.')
    missing = {p.stem for p in Path('podcast').glob('*.html')} - {'index'} - set(SHORT_ANSWERS)
    if missing:
        print(f'No short answer defined for: {", ".join(sorted(missing))}')


if __name__ == '__main__':
    main()
