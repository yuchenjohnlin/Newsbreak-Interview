# One-Sentence Topic Page Generator

Type one sentence describing a breaking event → get a publishable, source-cited
topic page as a single self-contained HTML file.

**Built examples (open directly in a browser, no setup):**

- [out/the-2026-fifa-world-cup-kicks-off-at-est.html](out/the-2026-fifa-world-cup-kicks-off-at-est.html) — sports
- [out/eurovision-2026-is-being-held-in-vienna-.html](out/eurovision-2026-is-being-held-in-vienna-.html) — show / culture
- [out/openai-rolled-out-gpt-5-5-instant-as-the.html](out/openai-rolled-out-gpt-5-5-instant-as-the.html) — tech

Design rationale, schemas, and failure-mode analysis: [DESIGN.md](DESIGN.md).

## Setup

Python 3.10+.

```bash
pip install -r requirements.txt
cp .env.example .env   # then fill in the two required keys
```

Required keys in `.env`:

| Variable | Used for | Where to get it |
|---|---|---|
| `BRAVE_API_KEY` | web search (retrieval) | brave.com/search/api — free tier, 2,000 queries/mo |
| `ANTHROPIC_API_KEY` | intake triage + page synthesis | console.anthropic.com |

(`TAVILY_API_KEY` / `SERPAPI_API_KEY` are optional — only used by the
provider-comparison probe, not the generator.)

## Generate a page

```bash
# one event
python generate.py --sentence "The 2026 FIFA World Cup kicks off at Estadio Azteca on June 11, 2026."

# or batch: one sentence per line in a text file
python generate.py input
```

There are two orchestrators over the same stage functions:

```bash
python generate.py ...   # deterministic: fixed stage order, predictable, cheapest
python agent.py ...      # agentic: a manager LLM drives the stages as tools and
                         # decides recovery (re-search, fetch more, reject) itself
```

Output lands in `out/{slug}.html`. Each run also writes per-stage debug
artifacts to `data/runs/{slug}/` (intake plan, clipped evidence pack, raw and
validated page JSON) so any stage can be inspected after the fact.

Useful flags: `--model` (synthesis model, default `claude-sonnet-4-6`),
`--max-docs` (evidence documents to gather, default 6), `--outdir`,
`--template` (Jinja template in `templates/`). The default is
`page.html.j2`; `page_featured.html.j2` is an alternate content-forward
layout that puts the most interesting facts in the first viewport, uses more
distinct section treatments, and keeps citations visually smaller.

Example:

```bash
python generate.py --sentence "The 2026 FIFA World Cup kicks off at Estadio Azteca on June 11, 2026." \
  --template page_featured.html.j2
```

Sourcing is live-web retrieval, not a vector database: the pipeline queries
Brave Search, fetches candidate URLs, extracts article text with trafilatura,
clips the evidence pack, and asks the model to cite source IDs from that pack.

## Repo map

| File | Role |
|---|---|
| `generate.py` | Deterministic orchestrator: intake gate → search+fetch → evidence pack → LLM synthesis → render |
| `agent.py` | Agentic orchestrator: manager LLM drives the same stages as tools, logs every decision to `data/runs/{slug}/agent_log.json` |
| `schemas.py` | The data contracts (evidence in, `TopicPage` out) + deterministic validation gates |
| `synthesize.py` | The two LLM calls (intake triage, page synthesis), schema-enforced via forced tool use |
| `render.py` + `templates/page.html.j2` | Jinja render of a validated `TopicPage` to one self-contained HTML file |
| `rerender.py` | Re-render pages from stored `data/runs/{slug}/page.json` — zero API calls; the template iteration loop |
| `fetch_content.py` | URL fetching + article extraction (trafilatura), over-fetch walk-down |
| `probe_search.py` | Exploration tool: compare Brave / SerpAPI / Tavily / Perplexity on the same queries |
| `input` | The three example event sentences |
