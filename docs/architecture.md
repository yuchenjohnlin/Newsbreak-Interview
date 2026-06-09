# Architecture

Design order: **output → schema → input**. The schema is the spine.

## Pipeline overview
`intake → understand → retrieve → synthesize → validate → render`

LLM only in `understand` and `synthesize`; the rest is deterministic.

## Stages

### 1. Intake & validation (deterministic)
<!-- cheap gate: empty/whitespace, length bounds, junk chars, (language), injection scan -->
TODO

### 2. Understand (LLM)
<!-- classify event type, extract entities + time hint, decide module plan, generate search queries -->
TODO

### 3. Retrieve (deterministic)
<!-- call search API, fetch, dedupe (source diversity != source count), cache -->
TODO

### 4. Synthesize (LLM)
<!-- raw sources → structured facts + citations, conforming to the schema -->
TODO

### 5. Validate & repair (deterministic)
<!-- schema conformance, citation integrity, required-module presence, freshness; repair loop -->
TODO

### 6. Render (deterministic)
<!-- schema → HTML; pure function; empty / loading / error states -->
TODO

## Data flow
`data/raw/`  →  `data/pages/`  →  `out/*.html`
