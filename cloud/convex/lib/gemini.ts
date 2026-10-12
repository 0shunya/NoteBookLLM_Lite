const EMBEDDING_MODEL = "gemini-embedding-001";
const EMBEDDING_DIMENSIONS = 768;

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
    throw new Error(message.replace(apiKey, "[hidden]").slice(0, 300));
  }
  return payload as Record<string, unknown>;
}

export async function embedText(apiKey: string, text: string, taskType: "RETRIEVAL_QUERY" | "RETRIEVAL_DOCUMENT") {
  const payload = await requestGemini(
    `https://generativelanguage.googleapis.com/v1beta/models/${EMBEDDING_MODEL}:embedContent`,
    apiKey,
    {
      content: { parts: [{ text }] },
      embedContentConfig: { taskType, outputDimensionality: EMBEDDING_DIMENSIONS },
    },
  ) as { embedding?: { values?: number[] } };
  const vector = payload.embedding?.values;
  if (!vector || vector.length !== EMBEDDING_DIMENSIONS) {
    throw new Error("Gemini returned an embedding with the wrong size.");
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
      })),
    },
  ) as { embeddings?: Array<{ values?: number[] }> };
  const vectors = payload.embeddings?.map((embedding) => embedding.values ?? []);
  if (!vectors || vectors.length !== texts.length || vectors.some((vector) => vector.length !== EMBEDDING_DIMENSIONS)) {
    throw new Error("Gemini returned incomplete document embeddings.");
  }
  return vectors;
}

export async function generateAnswer(apiKey: string, systemInstruction: string, prompt: string) {
  const model = process.env.GEMINI_MODEL || "gemini-3.8-flash";
  const payload = await requestGemini(
    `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`,
    apiKey,
    {
      systemInstruction: { parts: [{ text: systemInstruction }] },
      contents: [{ role: "user", parts: [{ text: prompt }] }],
      generationConfig: { temperature: 0 },
    },
  ) as { candidates?: Array<{ content?: { parts?: Array<{ text?: string; thought?: boolean }> } }> };
  const parts = payload.candidates?.[0]?.content?.parts ?? [];
  const answer = parts.filter((part) => !part.thought).map((part) => part.text ?? "").join("").trim();
  if (!answer) throw new Error("Gemini returned no answer text.");
  return answer;
}
