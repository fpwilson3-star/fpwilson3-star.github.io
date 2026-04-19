"""Backfill FAQ section + FAQPage JSON-LD on existing episode articles.

Reads each podcast/*.html, extracts the article body, asks Claude for
4-6 FAQ pairs grounded in the article, and inserts the visible FAQ
section and matching JSON-LD using the same helpers the generator uses.

Idempotent: skips pages that already contain an FAQPage block.
"""
import anthropic
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from generate_episode_post import render_faq_jsonld, render_faq_section  # noqa: E402

BODY_RE = re.compile(
    r'<div style="font-size: 1\.08rem; line-height: 1\.85;">\s*(.*?)\s*</div>\s*\n\s*<div style="margin-top: 56px; padding: 32px; background: #f3ede6;',
    re.DOTALL,
)
HEADLINE_RE = re.compile(
    r'<h1 style="font-family: var\(--font-display\)[^"]*">(.*?)</h1>',
    re.DOTALL,
)


def extract_article(html):
    m = BODY_RE.search(html)
    if not m:
        raise RuntimeError("Could not locate article body")
    body_html = m.group(1)
    text = re.sub(r'<[^>]+>', ' ', body_html)
    text = re.sub(r'\s+', ' ', text).strip()
    headline_m = HEADLINE_RE.search(html)
    headline = re.sub(r'\s+', ' ', headline_m.group(1)).strip() if headline_m else ''
    return headline, text


def get_faqs(headline, article_text):
    client = anthropic.Anthropic()

    system = """You are ghostwriting for Dr. F. Perry Wilson — nephrologist, Yale professor, and science communicator. Voice: direct, plain-spoken, confident without arrogance, wry but not jokey. No em-dashes. No AI filler ("it's worth noting," "delve into," "in conclusion," "navigate," "at the end of the day"). Grounded strictly in the source article."""

    user = f"""Below is a published article titled "{headline}".

Generate 4 to 6 FAQ pairs for readers searching Google about this topic:
- Questions: phrased exactly the way someone would type them into Google. Mix the highest-intent queries (safety, dosing, mechanism, common myths, practical how-to). Do not repeat the headline as a question.
- Answers: 2 to 4 sentences each, grounded strictly in the article below. Reuse the same numbers, study names, and caveats. Plain text only, no HTML tags, no em-dashes.
- Target the angles most likely to appear in Google "People Also Ask" boxes.

Call the create_faqs tool with your result.

ARTICLE:
{article_text}"""

    tools = [{
        "name": "create_faqs",
        "description": "Publish the FAQ pairs for this episode article",
        "input_schema": {
            "type": "object",
            "properties": {
                "faqs": {
                    "type": "array",
                    "minItems": 4,
                    "maxItems": 6,
                    "items": {
                        "type": "object",
                        "properties": {
                            "question": {"type": "string"},
                            "answer": {"type": "string"},
                        },
                        "required": ["question", "answer"],
                    },
                }
            },
            "required": ["faqs"],
        },
    }]

    msg = client.messages.create(
        model="claude-opus-4-7",
        max_tokens=2048,
        system=system,
        tools=tools,
        tool_choice={"type": "tool", "name": "create_faqs"},
        messages=[{"role": "user", "content": user}],
    )

    for block in msg.content:
        if block.type == "tool_use":
            return block.input["faqs"]

    raise RuntimeError("Claude did not call create_faqs tool")


def inject_faq(html, faqs):
    jsonld = render_faq_jsonld(faqs)
    section = render_faq_section(faqs)

    # After the last </script> before </head>, insert the FAQ JSON-LD
    html = re.sub(
        r'(</script>)\n(</head>)',
        lambda m: f'{m.group(1)}\n{jsonld}{m.group(2)}',
        html,
        count=1,
    )

    # Before the podcast CTA div, insert the visible FAQ section
    html = html.replace(
        '    <div style="margin-top: 56px; padding: 32px; background: #f3ede6;',
        f'{section}    <div style="margin-top: 56px; padding: 32px; background: #f3ede6;',
        1,
    )
    return html


def process(path):
    html = path.read_text(encoding='utf-8')
    if 'FAQPage' in html:
        print(f'  SKIP {path.name} (already has FAQPage)')
        return False
    headline, article_text = extract_article(html)
    print(f'  {path.name}: generating FAQs...')
    faqs = get_faqs(headline, article_text)
    new_html = inject_faq(html, faqs)
    path.write_text(new_html, encoding='utf-8')
    print(f'    wrote {len(faqs)} Q&A pairs')
    return True


def main():
    pages = sorted(Path('podcast').glob('*.html'))
    pages = [p for p in pages if p.name != 'index.html']
    count = 0
    for p in pages:
        if process(p):
            count += 1
    print(f'\nUpdated {count} page(s)')


if __name__ == '__main__':
    main()
