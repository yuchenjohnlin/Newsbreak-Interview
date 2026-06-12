"""Data contracts for the topic-page pipeline.

Two schemas, one per side of the LLM synthesis call:

  EvidencePack  (input)  — what we keep from fetched source pages.
  TopicPage     (output) — what the page shows; the Jinja template renders
                           this and nothing else.

TopicPage is a shared core (headline, summary, key facts, timeline,
sources, ...) plus exactly one per-category `extras` block, discriminated
on the event category. That keeps the schema versatile across very
different event types without degenerating into a free-form dict.

Validation gates (deterministic, no LLM):
  validate_intake    — sentence sanity before any API spend
  validate_evidence  — enough usable documents to synthesize from
  TopicPage validators — citation integrity: every source_id must point
                         at a real fetched source
"""
from __future__ import annotations

from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator

SCHEMA_VERSION = "1.0"

Category = Literal["tech", "show", "sports"]


# --------------------------------------------------------------------------
# Input side: evidence handed to the LLM
# --------------------------------------------------------------------------

class Document(BaseModel):
    """One fetched + extracted source page (clipped to budget)."""
    source_id: int
    url: str
    title: Optional[str] = None
    sitename: Optional[str] = None
    author: Optional[str] = None
    date: Optional[str] = None  # publish date as extracted; unreliable for Wikipedia
    thumbnail_url: Optional[str] = None  # from the search API's result thumbnail
    text: str
    char_len: int


class EvidencePack(BaseModel):
    sentence: str
    category: Category
    canonical_name: str
    fetched_at: str
    documents: list[Document]


# --------------------------------------------------------------------------
# Intake plan: the one bounded "agent decision" (LLM call #1 output)
# --------------------------------------------------------------------------

class IntakePlan(BaseModel):
    is_real_event: bool
    reject_reason: Optional[str] = Field(
        None, description="Why the input is not a usable event description (only when is_real_event is false)."
    )
    category: Optional[Category] = None
    canonical_name: Optional[str] = Field(
        None, description="Short canonical event name, e.g. 'Eurovision Song Contest 2026'."
    )
    facet_queries: list[str] = Field(
        default_factory=list,
        description="2-3 follow-up search queries covering facets a topic page for this event type needs (schedule, results, reactions, ...).",
    )


# --------------------------------------------------------------------------
# Output side: the topic page
# --------------------------------------------------------------------------

class SourceRef(BaseModel):
    id: int
    url: str
    title: Optional[str] = None
    sitename: Optional[str] = None
    date: Optional[str] = None


class KeyFact(BaseModel):
    label: str = Field(description="Short label, e.g. 'Opening match'.")
    value: str = Field(description="The fact itself, concise.")
    source_ids: list[int] = Field(default_factory=list)


class TimelineItem(BaseModel):
    date: str = Field(description="ISO date or human-readable date of the moment.")
    label: str
    description: Optional[str] = None
    status: Literal["past", "upcoming"]
    source_ids: list[int] = Field(default_factory=list)


class Entity(BaseModel):
    name: str
    role: str = Field(description="Why this entity matters here, e.g. 'Host city', 'Defending champion'.")
    description: Optional[str] = None


class HeroImage(BaseModel):
    url: str = Field(description="MUST be exactly one of the candidate thumbnail URLs listed in the evidence. Never invent or modify an image URL.")
    caption: Optional[str] = Field(None, description="Short factual caption.")
    credit_source_id: Optional[int] = Field(None, description="source_id of the document this image came from.")


class Reaction(BaseModel):
    source: str = Field(description="Who said it (outlet or person).")
    take: str = Field(description="Their view or notable quote, paraphrased.")
    source_ids: list[int] = Field(default_factory=list)


class TechExtras(BaseModel):
    kind: Literal["tech"] = "tech"
    product: str = Field(description="Product / model / thing being launched or changed.")
    company: str
    rollout_status: str = Field(description="Who gets it, when, and on what plans/platforms.")
    benchmarks_or_specs: list[KeyFact] = Field(default_factory=list)


class ShowExtras(BaseModel):
    kind: Literal["show"] = "show"
    venue: str
    dates: str = Field(description="Human-readable run of dates, e.g. 'May 12-16, 2026'.")
    lineup_or_participants: list[str] = Field(default_factory=list)
    results: Optional[str] = Field(None, description="Winner / outcome if the show already concluded.")
    how_to_watch: Optional[str] = None


class Match(BaseModel):
    date: str
    teams: str = Field(description="e.g. 'Mexico vs South Africa'.")
    venue: Optional[str] = None
    result: Optional[str] = Field(None, description="Score/outcome if played, else null.")


class SportsExtras(BaseModel):
    kind: Literal["sports"] = "sports"
    format_summary: str = Field(description="Tournament format / rules in 1-2 sentences.")
    key_matches: list[Match] = Field(default_factory=list)
    standings_or_results: Optional[str] = Field(None, description="Current standings or results so far, if any.")
    how_to_watch: Optional[str] = None


Extras = Annotated[Union[TechExtras, ShowExtras, SportsExtras], Field(discriminator="kind")]


class TopicPage(BaseModel):
    schema_version: Literal["1.0"] = SCHEMA_VERSION
    input_sentence: str
    generated_at: str
    category: Category
    headline: str = Field(description="Page headline; punchy but factual.")
    dek: str = Field(description="One-sentence standfirst under the headline.")
    hero_image: Optional[HeroImage] = Field(
        None, description="Lead image, chosen from the candidate thumbnails in the evidence — prefer the image of the most central/most-cited source. Omit if no candidate fits."
    )
    summary: str = Field(description="2-4 sentence overview of where the event stands right now.")
    key_facts: list[KeyFact] = Field(min_length=3)
    timeline: list[TimelineItem] = Field(min_length=2)
    entities: list[Entity] = Field(default_factory=list)
    reactions: list[Reaction] = Field(
        default_factory=list,
        description="Reactions & fallout around the event: expert takes, public/fan reactions, controversies and incidents (including viral moments), notable quotes. Include incidents the evidence reports even if unflattering.",
    )
    why_it_matters: str = Field(description="The bigger picture: why a reader should care, 2-3 sentences.")
    whats_next: list[str] = Field(default_factory=list, description="Concrete upcoming things to watch for.")
    extras: Extras
    sources: list[SourceRef]
    freshness_note: Optional[str] = Field(
        None, description="Caveat about information recency, e.g. 'Sourced June 11, 2026; results may have changed since.'"
    )

    @model_validator(mode="after")
    def check_extras_match_category(self) -> "TopicPage":
        if self.extras.kind != self.category:
            raise ValueError(f"extras.kind={self.extras.kind!r} does not match category={self.category!r}")
        return self

    @model_validator(mode="after")
    def check_citations_resolve(self) -> "TopicPage":
        """Anti-hallucination gate: every cited source_id must exist."""
        known = {s.id for s in self.sources}
        bad: list[str] = []

        def check(ids: list[int], where: str) -> None:
            for i in ids:
                if i not in known:
                    bad.append(f"{where} cites unknown source_id {i}")

        for f in self.key_facts:
            check(f.source_ids, f"key_fact {f.label!r}")
        for t in self.timeline:
            check(t.source_ids, f"timeline {t.label!r}")
        if self.hero_image and self.hero_image.credit_source_id is not None:
            check([self.hero_image.credit_source_id], "hero_image credit")
        for r in self.reactions:
            check(r.source_ids, f"reaction from {r.source!r}")
        if isinstance(self.extras, TechExtras):
            for f in self.extras.benchmarks_or_specs:
                check(f.source_ids, f"benchmark {f.label!r}")
        if bad:
            raise ValueError("; ".join(bad))
        return self


# --------------------------------------------------------------------------
# Deterministic gates
# --------------------------------------------------------------------------

class GateError(Exception):
    """A validation gate failed; message is user-facing."""


def validate_intake(sentence: str) -> str:
    s = " ".join(sentence.split())
    if not s:
        raise GateError("input sentence is empty")
    if len(s) < 15:
        raise GateError(f"input too short to describe an event ({len(s)} chars): {s!r}")
    if len(s) > 500:
        raise GateError(f"input too long ({len(s)} chars); expected a one-sentence event description")
    return s


MIN_DOC_CHARS = 300
MIN_USABLE_DOCS = 3


def validate_evidence(documents: list[Document]) -> list[Document]:
    usable = [d for d in documents if d.char_len >= MIN_DOC_CHARS]
    if len(usable) < MIN_USABLE_DOCS:
        raise GateError(
            f"only {len(usable)} usable documents (need >= {MIN_USABLE_DOCS}); "
            "search/fetch did not find enough real coverage for this event"
        )
    return usable
