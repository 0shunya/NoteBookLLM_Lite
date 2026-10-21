const EMBEDDING_MODEL = "gemini-embedding-001";
const EMBEDDING_DIMENSIONS = 768;
const FALLBACK_GENERATION_MODEL = "gemini-3.5-flash-lite";

class GeminiApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
    this.name = "GeminiApiError";
  }
}

async function requestGemini(url: string, apiKey: string, body: unknown) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json", "x-goog-api-key": apiKey },
    body: JSON.stringify(body),
  });
  const payload = await response.json().catch(() => ({})) as {
    error?: { message?: string };
  };
  if (!response.ok) {
    const message = payload.error?.message || `Gemini returned HTTP ${response.status}.`;
    throw new GeminiApiError(message.replace(apiKey, "[hidden]").slice(0, 300), response.status);
  }
  return payload as Record<string, unknown>;
}

function isTransientGeminiError(error: unknown): boolean {
  return error instanceof TypeError || (error instanceof GeminiApiError && [408, 429, 500, 502, 503, 504].includes(error.status));
}

function isOverloadedGeminiError(error: unknown): boolean {
  return error instanceof GeminiApiError && (
    error.status === 503 || /currently experiencing high demand|temporarily overloaded|service unavailable/i.test(error.message)
  );
}

function wait(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

export async function embedText(apiKey: string, text: string, taskType: "RETRIEVAL_QUERY" | "RETRIEVAL_DOCUMENT") {
  const payload = await requestGemini(
    `https://generativelanguage.googleapis.com/v1beta/models/${EMBEDDING_MODEL}:embedContent`,
    apiKey,
    {
      content: { parts: [{ text }] },
      embedContentConfig: { taskType, outputDimensionality: EMBEDDING_DIMENSIONS },
      // Keep the legacy REST field too: batchEmbedContents may return the
      // model's 3072-dimension default when it ignores the nested config.
      outputDimensionality: EMBEDDING_DIMENSIONS,
    },
  ) as { embedding?: { values?: number[] } };
  const vector = payload.embedding?.values;
  if (!vector || vector.length !== EMBEDDING_DIMENSIONS) {
    throw new Error(
      `Gemini returned a ${vector?.length ?? 0}-value query embedding; expected ${EMBEDDING_DIMENSIONS}.`,
    );
  }
  return vector;
}

export async function embedTexts(apiKey: string, texts: string[]) {
  const payload = await requestGemini(
    `https://generativelanguage.googleapis.com/v1beta/models/${EMBEDDING_MODEL}:batchEmbedContents`,
    apiKey,
    {
      requests: texts.map((text) => ({
        model: `models/${EMBEDDING_MODEL}`,
        content: { parts: [{ text }] },
        embedContentConfig: { taskType: "RETRIEVAL_DOCUMENT", outputDimensionality: EMBEDDING_DIMENSIONS },
        outputDimensionality: EMBEDDING_DIMENSIONS,
      })),
    },
  ) as { embeddings?: Array<{ values?: number[] }> };
  const embeddings = Array.isArray(payload.embeddings) ? payload.embeddings : [];
  if (embeddings.length !== texts.length) {
    throw new Error(`Gemini returned ${embeddings.length} of ${texts.length} document embeddings.`);
  }
  const vectors = embeddings.map((embedding) => embedding.values ?? []);
  const invalidIndex = vectors.findIndex((vector) => vector.length !== EMBEDDING_DIMENSIONS);
  if (invalidIndex !== -1) {
    throw new Error(
      `Gemini returned an invalid document embedding (${vectors[invalidIndex].length} values; expected ${EMBEDDING_DIMENSIONS}).`,
    );
  }
  return vectors;
}

export async function generateAnswer(apiKey: string, systemInstruction: string, prompt: string) {
  const primaryModel = process.env.GEMINI_MODEL || "gemini-3.8-flash";

  async function requestAnswer(model: string): Promise<string> {
    const payload = await requestGemini(
      `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`,
      apiKey,
      {
        systemInstruction: { parts: [{ text: systemInstruction }] },
        contents: [{ role: "user", parts: [{ text: prompt }] }],
      },
    ) as { candidates?: Array<{ content?: { parts?: Array<{ text?: string; thought?: boolean }> } }> };
    const parts = payload.candidates?.[0]?.content?.parts ?? [];
    const answer = parts.filter((part) => !part.thought).map((part) => part.text ?? "").join("").trim();
    if (!answer) throw new Error("Gemini returned no answer text.");
    return answer;
  }

  async function withRetries(model: string, attempts: number): Promise<string> {
    for (let attempt = 0; ; attempt += 1) {
      try {
        return await requestAnswer(model);
      } catch (error) {
        if (!isTransientGeminiError(error) || attempt >= attempts - 1) throw error;
        await wait(700 * 2 ** attempt + Math.floor(Math.random() * 400));
      }
    }
  }

  try {
    return await withRetries(primaryModel, 3);
  } catch (error) {
    if (!isOverloadedGeminiError(error) || primaryModel === FALLBACK_GENERATION_MODEL) throw error;
    try {
      return await withRetries(FALLBACK_GENERATION_MODEL, 2);
    } catch (fallbackError) {
      const detail = fallbackError instanceof Error ? fallbackError.message : "Unknown error.";
      throw new Error(`Primary model is busy; fallback model also failed: ${detail}`);
    }
  }
}
