# Topic Page Generator — Claude Code context

One-sentence event description → a publishable, structured HTML **topic page**.
We are the *distribution / aggregation layer* (NewsBreak-style): we don't report,
we aggregate real, fresh web sources into something a reader can use to understand
an event fast — context, timeline, key entities, related coverage, live updates.

## Design order (important)
Work **output → schema → input**. The schema (data contract) is the spine:
everything upstream exists to fill it, everything downstream renders it.

## Architecture — 6 stages
`intake → understand → retrieve → synthesize → validate → render`
- LLM lives ONLY in `understand` and `synthesize`.
- Everything else is deterministic.
- Details: [docs/architecture.md](docs/architecture.md)

## Invariants (do not violate)
- The schema is THE contract. Never widen it to `Map<string, any>`.
- Every factual claim in page data MUST carry a citation to a real, retrieved URL.
- Renderer is pure: valid schema in → valid HTML out. No LLM in render.
- Each stage is independently runnable (file in → file out); dump every stage's output as JSON.
- Cache all search-API calls (keyed by input) so builds are cheap and reproducible.

## How to run
```
pip install -e .
python -m pipeline.cli run "<one-sentence event>"   # → out/<id>.html
```
Stages are stubs (raise NotImplementedError) until built. Each stage is also
importable on its own (`pipeline.retrieve.run(...)`) for fast iteration.

## Where things live
- Data contract / schema:   `schema/`  — see [docs/schema.md](docs/schema.md)
- Pipeline code:            `src/pipeline/`
- Raw search dumps:         `data/raw/`  ·  API cache: `data/cache/`  ·  page JSON: `data/pages/`
- Built HTML output:        `out/`  (committed — it's a deliverable)
- Design decisions (ADRs):  `docs/decisions/`
- Dev worklog:              [docs/worklog.md](docs/worklog.md)

## Doc maintenance (do this as you code)
- Change the schema or a stage's contract → update [docs/architecture.md](docs/architecture.md) / [docs/schema.md](docs/schema.md).
- Append a one-line entry to [docs/worklog.md](docs/worklog.md) each work session.
- A non-trivial design choice → add an ADR under `docs/decisions/` (copy `_template.md`).
- DESIGN.md is the graded deliverable — distill it from the ADRs at the END; don't edit it continuously.

## Tech stack
- Python (Pydantic = data contract; Jinja2 = render). Chosen for fluency; with the
  LLM emitting data (not HTML), TS's frontend edge doesn't apply. See ADR 0005.
- LLM provider: Anthropic Claude (default, swappable).
- Web search / research API: **TBD** (Tavily recommended) — blocks the retrieval spike.
- No frontend/backend: offline batch CLI → self-contained static HTML.
