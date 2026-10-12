"""Deterministic citation syntax and source-id validation."""

import re

from app.services.source_builder import Source


CITATION_PATTERN = re.compile(r"\[(\d+)\]")
BRACKET_PATTERN = re.compile(r"\[([^\[\]]*)\]")
REFUSAL_PATTERNS = (
    "not found in the provided sources",
    "not found in the sources",
    "not in the provided sources",
    "could not find relevant information",
    "couldn't find relevant information",
    "do not contain enough information",
    "does not contain enough information",
    "not specified in the provided sources",
    "not stated in the provided sources",
    "not mentioned in the provided sources",
    "the provided sources do not specify",
    "the provided sources do not state",
    "the provided sources do not mention",
    "the sources do not specify",
    "the sources do not state",
    "the sources do not mention",
    "cannot be determined from the sources",
    "can't be determined from the sources",
    "unable to determine from the sources",
)
SENTENCE_ABBREVIATIONS = re.compile(
    r"\b(?:[ap]\.m\.|e\.g\.|i\.e\.|mr\.|mrs\.|dr\.|vs\.)",
    flags=re.IGNORECASE,
)
PROTECTED_PERIOD = "\uE000"


def extract_citation_ids(answer: str) -> list[int]:
    return list(dict.fromkeys(int(match.group(1)) for match in CITATION_PATTERN.finditer(answer)))


def split_into_sentences(answer: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", answer).strip()
    if not normalized:
        return []
    def protect_embedded_abbreviation(match: re.Match) -> str:
        abbreviation = match.group(0)
        following_text = normalized[match.end():]
        # Keep sentence-final abbreviations as boundaries. Citation markers
        # may follow the period, so sentence splitting also handles a break
        # immediately after a marker below.
        if re.match(r"\s+(?:\[\d+\]\s+)?[A-Z]", following_text):
            if abbreviation.lower() not in {"mr.", "mrs.", "dr.", "vs."}:
                return abbreviation
        return abbreviation.replace(".", PROTECTED_PERIOD)

    protected = SENTENCE_ABBREVIATIONS.sub(protect_embedded_abbreviation, normalized)
    parts = re.split(
        r"(?<=[.!?])\s+(?!\[\d+\])|(?<=\])\s+(?=[A-Z])",
        protected,
    )
    return [part.strip().replace(PROTECTED_PERIOD, ".") for part in parts if part.strip()]


def sentence_has_citation(sentence: str) -> bool:
    return CITATION_PATTERN.search(sentence) is not None


def _malformed_citations(answer: str) -> list[str]:
    malformed = [
        match.group(0)
        for match in BRACKET_PATTERN.finditer(answer)
        if not match.group(1).isdigit()
    ]
    stripped = BRACKET_PATTERN.sub("", answer)
    if "[" in stripped or "]" in stripped:
        malformed.append("unmatched bracket")
    return list(dict.fromkeys(malformed))


def _is_explicit_refusal(sentence: str) -> bool:
    lowered = sentence.lower()
    return any(phrase in lowered for phrase in REFUSAL_PATTERNS)


def validate_citations(answer: str, sources: list[Source]) -> dict:
    valid_source_ids = {source.source_id for source in sources}
    cited_source_ids = extract_citation_ids(answer)
    invalid_source_ids = [
        source_id for source_id in cited_source_ids if source_id not in valid_source_ids
    ]
    uncited_sentences = [
        sentence
        for sentence in split_into_sentences(answer)
        if not sentence_has_citation(sentence) and not _is_explicit_refusal(sentence)
    ]
    malformed_citations = _malformed_citations(answer)

    return {
        "valid": not invalid_source_ids and not uncited_sentences and not malformed_citations,
        "cited_source_ids": cited_source_ids,
        "invalid_source_ids": invalid_source_ids,
        "uncited_sentences": uncited_sentences,
        "malformed_citations": malformed_citations,
    }
