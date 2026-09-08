"""
Entity resolution: deduplicates and canonicalizes entities across documents.
Uses fuzzy string matching to identify entity aliases.
Builds an in-memory alias table populated from extraction — not a hard-coded ontology.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ResolvedEntity:
    canonical_name: str
    entity_type: str
    aliases: list[str]
    confidence: float


def _normalize_name(name: str) -> str:
    """Lowercase, strip punctuation, normalize unicode for fuzzy matching."""
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9\s]", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def _token_overlap(a: str, b: str) -> float:
    """Token-level Jaccard similarity between two normalized strings."""
    tokens_a = set(a.split())
    tokens_b = set(b.split())
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


class EntityResolver:
    """
    Incremental entity resolver. Entities are added as they are extracted.
    On lookup, returns the canonical entity ID for a given name.
    Can be persisted to DB and reloaded.
    """

    def __init__(self, similarity_threshold: float = 0.7) -> None:
        self._threshold = similarity_threshold
        # canonical_name -> ResolvedEntity
        self._entities: dict[str, ResolvedEntity] = {}

    def resolve(
        self, name: str, entity_type: str = "UNKNOWN"
    ) -> ResolvedEntity:
        """
        Resolve a name to a canonical entity.
        If no match found, creates a new canonical entity.
        """
        norm = _normalize_name(name)
        if not norm:
            return ResolvedEntity(
                canonical_name=name,
                entity_type=entity_type,
                aliases=[name],
                confidence=0.5,
            )

        # Exact match first
        if norm in self._entities:
            ent = self._entities[norm]
            if name not in ent.aliases:
                ent.aliases.append(name)
            return ent

        # Fuzzy match
        best_score = 0.0
        best_key: Optional[str] = None
        for key, ent in self._entities.items():
            score = _token_overlap(norm, key)
            if score >= self._threshold and score > best_score:
                best_score = score
                best_key = key

        if best_key:
            ent = self._entities[best_key]
            if name not in ent.aliases:
                ent.aliases.append(name)
            return ResolvedEntity(
                canonical_name=ent.canonical_name,
                entity_type=ent.entity_type,
                aliases=ent.aliases,
                confidence=best_score,
            )

        # New entity
        new_ent = ResolvedEntity(
            canonical_name=name,
            entity_type=entity_type,
            aliases=[name],
            confidence=1.0,
        )
        self._entities[norm] = new_ent
        return new_ent

    def all_entities(self) -> list[ResolvedEntity]:
        return list(self._entities.values())
