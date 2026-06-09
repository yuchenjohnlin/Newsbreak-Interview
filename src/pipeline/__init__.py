"""Topic page generator pipeline.

Stages (see docs/architecture.md):
    intake -> understand -> retrieve -> synthesize -> validate -> render

LLM lives ONLY in `understand` and `synthesize`. Everything else is deterministic.
The LLM emits structured data (the schema); it never emits HTML.
"""
