"use node";

import * as pdfjs from "pdfjs-dist/legacy/build/pdf.mjs";
// pdfjs-dist does not ship a declaration for the worker entry, but it exports
// WorkerMessageHandler at runtime. Importing it statically lets Convex bundle it.
// @ts-expect-error pdfjs-dist omits types for this worker entry point.
import * as pdfjsWorker from "pdfjs-dist/legacy/build/pdf.worker.mjs";
import { v } from "convex/values";
import { internal } from "./_generated/api";
import { internalAction } from "./_generated/server";
import { splitPageIntoChunks } from "./lib/chunker";
import { embedTexts } from "./lib/gemini";
import { decryptGeminiKey } from "./geminiKeyActions";
import { downloadSupabaseObject } from "./lib/supabaseStorage";

// PDF.js disables real Web Workers in Node.js. Its fake-worker path first checks
// this global before dynamically importing the worker relative to the bundled
// module, which Convex cannot resolve at runtime.
(globalThis as typeof globalThis & { pdfjsWorker?: typeof pdfjsWorker }).pdfjsWorker = pdfjsWorker;

export const indexDocument = internalAction({
  args: { documentId: v.id("documents") },
  handler: async (ctx, { documentId }): Promise<void> => {
    try {
      const document = await ctx.runQuery(internal.documents.getForIndexing, { documentId });
      if (!document) return;
      await ctx.runMutation(internal.documents.setIndexing, { documentId, status: "processing" });

      const encryptedKey = await ctx.runQuery(internal.settings.readGeminiKey, { ownerId: document.ownerId });
      if (!encryptedKey) throw new Error("Add your Gemini API key in Settings before indexing PDFs.");
      const apiKey = decryptGeminiKey(encryptedKey);
      const bytes = await downloadSupabaseObject(document.storageKey);
      if (bytes.byteLength !== document.sizeBytes || Buffer.from(bytes.subarray(0, 5)).toString("ascii") !== "%PDF-") {
        throw new Error("The uploaded file is not a valid PDF.");
      }

      const pdf = await pdfjs.getDocument({ data: bytes, useSystemFonts: true }).promise;
      const warnings: string[] = [];
      let chunkIndex = 0;
      for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber += 1) {
        const page = await pdf.getPage(pageNumber);
        const content = await page.getTextContent();
        const pageText = content.items
          .map((item) => "str" in item ? item.str : "")
          .join(" ")
          .replace(/\s+/g, " ")
          .trim();
        const rawChunks = splitPageIntoChunks(pageText);
        if (pageText.length < 20) warnings.push(`Page ${pageNumber} has little readable text; it may be scanned.`);

        const indexedChunks = [];
        for (let offset = 0; offset < rawChunks.length; offset += 32) {
          const textBatch = rawChunks.slice(offset, offset + 32);
          const vectors = await embedTexts(apiKey, textBatch);
          for (let index = 0; index < textBatch.length; index += 1) {
            indexedChunks.push({
              chunkIndex: chunkIndex++,
              text: textBatch[index],
              embedding: vectors[index],
            });
          }
        }
        await ctx.runMutation(internal.documents.savePageChunks, {
          documentId,
          pageNumber,
          pageText,
          chunks: indexedChunks,
        });
      }
      await ctx.runMutation(internal.documents.finishIndexing, {
        documentId,
        pageCount: pdf.numPages,
        warnings: [...new Set(warnings)].slice(0, 50),
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "PDF indexing failed.";
      await ctx.runMutation(internal.documents.failIndexing, {
        documentId,
        message: message.replace(/AIza[\w-]{20,}/g, "[hidden]").slice(0, 300),
      });
    }
  },
});
