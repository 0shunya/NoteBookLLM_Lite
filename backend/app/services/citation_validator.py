import re

from app.services.source_builder import Source


# Matches citations such as:
# [1]
# [2]
# [15]
CITATION_PATTERN = re.compile(r"\[(\d+)\]")


def extract_citation_ids(answer: str) -> list[int]:
    """
    Extract all citation IDs from the generated answer.

    Duplicate citations are removed while preserving their original order.
    """

    citation_ids = []

    for match in CITATION_PATTERN.finditer(answer):
        citation_id = int(match.group(1))

        if citation_id not in citation_ids:
            citation_ids.append(citation_id)

    return citation_ids


def split_into_sentences(answer: str) -> list[str]:
    """
    Split an answer into sentences while keeping citations attached
    to the sentence they support.

    Examples:

        Python is a skill. [1]
        -> "Python is a skill. [1]"

        Python is a skill [1].
        -> "Python is a skill [1]."

        Python is a skill. [1] React is also known. [2]
        -> two separate sentences
    """

    normalized = re.sub(r"\s+", " ", answer).strip()

    if not normalized:
        return []

    # The important part is the negative lookahead:
    #
    #     (?!\[\d+\])
    #
    # It means:
    #
    # "Split after punctuation ONLY when the next thing is NOT
    # a citation."
    #
    # Therefore:
    #
    #     "Python is a skill. [1]"
    #
    # stays together.
    sentences = re.split(
        r"(?<=[.!?])\s+(?!\[\d+\])",
        normalized,
    )

    return [
        sentence.strip()
        for sentence in sentences
        if sentence.strip()
    ]


def sentence_has_citation(sentence: str) -> bool:
    """
    Return True when the sentence contains at least one citation.
    """

    return CITATION_PATTERN.search(sentence) is not None


def validate_citations(
    answer: str,
    sources: list[Source],
) -> dict:
    """
    Validate citations used by the generated answer.

    Checks:

    1. Every citation ID refers to a source that was actually
       provided to the model.

    2. Every sentence contains at least one citation.

    This implements the first version of the
    "NO SOURCE, NO SENTENCE" rule.
    """

    # IDs that actually exist in the retrieved sources.
    valid_source_ids = {
        source.source_id
        for source in sources
    }

    # IDs referenced by the generated answer.
    cited_source_ids = extract_citation_ids(answer)

    # Citation IDs that do not correspond to retrieved sources.
    invalid_source_ids = [
        citation_id
        for citation_id in cited_source_ids
        if citation_id not in valid_source_ids
    ]

    # Split the answer while preserving trailing citations.
    sentences = split_into_sentences(answer)

    # Find sentences that contain no citation.
    uncited_sentences = [
        sentence
        for sentence in sentences
        if not sentence_has_citation(sentence)
    ]

    is_valid = (
        not invalid_source_ids
        and not uncited_sentences
    )

    return {
        "valid": is_valid,
        "cited_source_ids": cited_source_ids,
        "invalid_source_ids": invalid_source_ids,
        "uncited_sentences": uncited_sentences,
    }