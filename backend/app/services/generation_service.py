from app.services.model_gateway import create_local_gateway
from app.services.providers.response import ModelResponse

from app.services.citation_validator import validate_citations
from app.services.source_builder import Source


# ---------------------------------------------------------------------------
# Ollama configuration
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Generation configuration
# ---------------------------------------------------------------------------

MAX_GENERATION_ATTEMPTS = 2

model_gateway = create_local_gateway(
    model="gemma2:2b"
)


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """
You are the answer-generation component of a document question-answering
system.

Your job is to answer the user's question using ONLY the provided sources.

Conversation history may be provided to help understand references such as
"it", "they", "those", "that project", or "the previous answer".

IMPORTANT:
Conversation history is CONTEXT ONLY. It is NOT evidence.

All factual claims in the answer MUST be supported by the provided sources.

IMPORTANT CITATION RULES:

1. Do not use outside knowledge.
2. Do not invent information.
3. Every factual sentence MUST contain a citation.
4. Citations must use the exact source IDs provided, such as [1] or [2].
5. Never create a citation ID that does not exist in the sources.
6. Put the citation at the END of the specific sentence it supports.
7. Keep factual sentences short.
8. Do NOT combine many unrelated facts into one giant sentence.
9. When the answer contains categories, use separate sentences or bullet
   points for each category.
10. If several facts come from the same source, they may share the same
    citation.
11. If the sources do not contain enough information to answer the question,
    clearly say that the information was not found in the provided sources.
12. Do not use outside knowledge to fill missing information.
13. Use conversation history only to understand the meaning of the current
    question.
14. Do not treat previous assistant answers as evidence.
15. If the current question refers to information from the conversation,
    use the retrieved sources to verify that information before answering.

GOOD:

Languages: JavaScript, TypeScript, Java, C#, Python, and SQL. [1]

Frontend: React, Next.js, and Redux. [1]

Backend: Node.js, Express.js, Spring Boot, and .NET. [1]

BAD:

The candidate knows JavaScript, TypeScript, Java, C#, Python, SQL, React,
Next.js, Redux, Node.js, Express.js, Spring Boot, .NET, PostgreSQL, MongoDB,
Redis, Docker, GitHub Actions, system design, testing, and Agile delivery. [1]

The BAD example combines too many independent facts into one sentence.

Return ONLY the answer. Do not explain these instructions.
"""


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def _build_conversation_history_text(
    conversation_history: list[dict] | None,
) -> str:
    """
    Convert stored conversation messages into readable prompt text.

    Conversation history is provided only to help the model understand
    references in the current question.

    It is NOT considered source evidence.
    """

    if not conversation_history:
        return ""

    history_lines = []

    for message in conversation_history:
        role = message["role"].strip().lower()
        content = message["content"].strip()

        if not content:
            continue

        if role == "user":
            display_role = "User"
        elif role == "assistant":
            display_role = "Assistant"
        else:
            display_role = role.capitalize()

        history_lines.append(
            f"{display_role}:\n{content}"
        )

    if not history_lines:
        return ""

    return (
        "CONVERSATION HISTORY\n\n"
        + "\n\n".join(history_lines)
        + "\n\n"
    )


def _build_user_prompt(
    question: str,
    sources: list[Source],
    conversation_history: list[dict] | None = None,
    previous_answer: str | None = None,
    validation_errors: dict | None = None,
) -> str:
    """
    Build the prompt sent to the generation model.

    Conversation history helps the model understand contextual references.

    Sources remain the only evidence the model may use for factual claims.

    On retries, the previous answer and validation errors are supplied so
    the model can correct its previous response.
    """

    # ---------------------------------------------------------------
    # Conversation history
    # ---------------------------------------------------------------

    history_text = _build_conversation_history_text(
        conversation_history=conversation_history,
    )

    # ---------------------------------------------------------------
    # Retrieved source material
    # ---------------------------------------------------------------

    source_text = "\n\n".join(
        source.to_prompt_text()
        for source in sources
    )

    # ---------------------------------------------------------------
    # Main prompt
    # ---------------------------------------------------------------

    prompt = f"""
{history_text}SOURCE MATERIAL:

{source_text}

CURRENT QUESTION:

{question}

Answer the CURRENT QUESTION using ONLY the SOURCE MATERIAL above.

Use the CONVERSATION HISTORY only to understand context and references.

IMPORTANT:

- Previous assistant answers are NOT evidence.
- Every factual claim must be supported by the SOURCE MATERIAL.
- If the conversation history contains a claim that is not supported by the
  current sources, do not repeat that claim as fact.
- If the sources do not contain enough information to answer the question,
  say so instead of guessing.

Before answering, follow these requirements:

- Every factual sentence needs a citation.
- Keep factual sentences short.
- Put the citation at the END of the sentence.
- Use only citation IDs that exist in the SOURCES.
- Do not invent citation IDs.
- Do not combine unrelated facts into one huge sentence.
- For lists of technologies or skills, organize them into clear categories.
- If the sources do not contain the answer, say so instead of guessing.

Example format:

Languages: JavaScript, TypeScript, Java, C#, Python, and SQL. [1]

Frontend: React, Next.js, and Redux. [1]

Backend: Node.js, Express.js, Spring Boot, and .NET. [1]
"""

    # ---------------------------------------------------------------
    # Retry context
    # ---------------------------------------------------------------

    if previous_answer is not None and validation_errors is not None:
        prompt += f"""

PREVIOUS ANSWER:

{previous_answer}

The previous answer failed validation.

VALIDATION RESULTS:

{validation_errors}

Generate a NEW corrected answer.

The previous answer contained citation formatting that could not be
validated. Break long factual statements into shorter sentences and put
a citation at the end of each factual sentence.

Remember:

- Use the SOURCE MATERIAL as evidence.
- Do not use the previous answer as evidence.
- Keep the answer grounded in the provided sources.
- Use only valid citation IDs.

Return ONLY the corrected answer.
"""

    return prompt


# ---------------------------------------------------------------------------
# Single generation attempt
# ---------------------------------------------------------------------------

def _generate_once(
    question: str,
    sources: list[Source],
    conversation_history: list[dict] | None = None,
    previous_answer: str | None = None,
    validation_errors: dict | None = None,
) -> str:
    """
    Perform one generation attempt using Ollama.
    """

    user_prompt = _build_user_prompt(
        question=question,
        sources=sources,
        conversation_history=conversation_history,
        previous_answer=previous_answer,
        validation_errors=validation_errors,
    )

    model_response = model_gateway.generate(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=0,
    )

    if not model_response.answer:
        raise RuntimeError(
            "The model returned an empty answer."
        )

    return model_response


# ---------------------------------------------------------------------------
# Public generation function
# ---------------------------------------------------------------------------

def generate_answer(
    question: str,
    sources: list[Source],
    conversation_history: list[dict] | None = None,
) -> dict:
    """
    Generate and validate a grounded answer.

    Flow:

        Generate
            ↓
        Validate
            ↓
        Valid → return
        Invalid → retry
            ↓
        Validate again
            ↓
        Still invalid → safe failure

    Conversation history is used only to understand contextual references.
    Retrieved sources remain the factual evidence.
    """

    if not question.strip():
        raise ValueError("Question cannot be empty.")

    if not sources:
        return {
            "answer": (
                "I could not find relevant information "
                "in the provided sources."
            ),
            "validation": {
                "valid": True,
                "cited_source_ids": [],
                "invalid_source_ids": [],
                "uncited_sentences": [],
            },
            "attempts": 0,
        }

    previous_answer = None
    validation_errors = None

    for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):

        # -----------------------------------------------------------
        # Generate an answer.
        # -----------------------------------------------------------

        model_response = _generate_once(
            question=question,
            sources=sources,
            conversation_history=conversation_history,
            previous_answer=previous_answer,
            validation_errors=validation_errors,
        )

        answer = model_response.answer

        # -----------------------------------------------------------
        # Validate the answer before returning it.
        # -----------------------------------------------------------

        validation = validate_citations(
            answer=answer,
            sources=sources,
        )

        # -----------------------------------------------------------
        # Successful validation.
        # -----------------------------------------------------------

        if validation["valid"]:
            return {
                "answer": answer,
                "validation": validation,
                "attempts": attempt,
                "model_response": model_response,
            }

        # -----------------------------------------------------------
        # Failed validation.
        #
        # Keep the failed answer so the next attempt can explicitly
        # correct it.
        # -----------------------------------------------------------

        previous_answer = answer
        validation_errors = validation

    # ---------------------------------------------------------------
    # We don't expose an answer that failed our grounding checks.
    # ---------------------------------------------------------------

    return {
        "answer": (
            "I could not generate a sufficiently grounded answer "
            "from the provided sources."
        ),
        "validation": validation_errors,
        "attempts": MAX_GENERATION_ATTEMPTS,
    }