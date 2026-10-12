import { v } from "convex/values";
import { internal } from "./_generated/api";
import {
  internalAction,
  internalMutation,
  internalQuery,
  mutation,
  query,
} from "./_generated/server";
import { requireUser } from "./lib/identity";

const pageChunk = v.object({
  chunkIndex: v.number(),
  text: v.string(),
  embedding: v.array(v.float64()),
});

export const list = query({
  args: { notebookId: v.id("notebooks") },
  handler: async (ctx, { notebookId }) => {
    const ownerId = await requireUser(ctx);
    const notebook = await ctx.db.get(notebookId);
    if (!notebook || notebook.ownerId !== ownerId) throw new Error("Notebook not found.");
    return ctx.db
      .query("documents")
      .withIndex("by_notebook_created", (q) => q.eq("notebookId", notebookId))
      .order("desc")
      .collect();
  },
});

export const createUpload = mutation({
  args: {
    notebookId: v.id("notebooks"),
    filename: v.string(),
    sha256: v.string(),
    sizeBytes: v.number(),
  },
  handler: async (ctx, args) => {
    const ownerId = await requireUser(ctx);
    const notebook = await ctx.db.get(args.notebookId);
    if (!notebook || notebook.ownerId !== ownerId) throw new Error("Notebook not found.");
    const filename = args.filename.replace(/[\\/\u0000-\u001f]/g, "_").trim().slice(0, 255);
    if (!filename.toLowerCase().endsWith(".pdf")) throw new Error("Choose a PDF file.");
    if (args.sizeBytes <= 0 || args.sizeBytes > 50 * 1024 * 1024) {
      throw new Error("PDFs must be smaller than 50 MB.");
    }
    if (!/^[a-f0-9]{64}$/i.test(args.sha256)) throw new Error("The PDF fingerprint is invalid.");

    const duplicate = await ctx.db
      .query("documents")
      .withIndex("by_notebook_hash", (q) =>
        q.eq("notebookId", args.notebookId).eq("sha256", args.sha256.toLowerCase()),
      )
      .first();
    if (duplicate) return { documentId: duplicate._id, duplicate: true };

    const now = Date.now();
    const documentId = await ctx.db.insert("documents", {
      ownerId,
      notebookId: args.notebookId,
      filename,
      storageKey: `${args.notebookId}/${crypto.randomUUID()}.pdf`,
      sha256: args.sha256.toLowerCase(),
      sizeBytes: args.sizeBytes,
      pageCount: 0,
      status: "uploading",
      warnings: [],
      createdAt: now,
      updatedAt: now,
    });
    return { documentId, duplicate: false };
  },
});

export const completeUpload = mutation({
  args: { documentId: v.id("documents") },
  handler: async (ctx, { documentId }) => {
    const ownerId = await requireUser(ctx);
    const document = await ctx.db.get(documentId);
    if (!document || document.ownerId !== ownerId) throw new Error("Document not found.");
    if (document.status !== "uploading") throw new Error("This upload is already being processed.");
    await ctx.db.patch(documentId, { status: "queued", updatedAt: Date.now() });
    await ctx.scheduler.runAfter(0, internal.ingestion.indexDocument, { documentId });
  },
});

export const failUpload = mutation({
  args: { documentId: v.id("documents"), message: v.string() },
  handler: async (ctx, { documentId, message }) => {
    const ownerId = await requireUser(ctx);
    const document = await ctx.db.get(documentId);
    if (!document || document.ownerId !== ownerId) return;
    await ctx.db.patch(documentId, {
      status: "failed",
      ingestionError: message.slice(0, 300),
      updatedAt: Date.now(),
    });
  },
});

export const getOwned = query({
  args: { documentId: v.id("documents") },
  handler: async (ctx, { documentId }) => {
    const ownerId = await requireUser(ctx);
    const document = await ctx.db.get(documentId);
    if (!document || document.ownerId !== ownerId) throw new Error("Document not found.");
    return document;
  },
});

export const getPage = query({
  args: { documentId: v.id("documents"), pageNumber: v.number() },
  handler: async (ctx, { documentId, pageNumber }) => {
    const ownerId = await requireUser(ctx);
    const document = await ctx.db.get(documentId);
    if (!document || document.ownerId !== ownerId) throw new Error("Document not found.");
    return ctx.db
      .query("pages")
      .withIndex("by_document_page", (q) =>
        q.eq("documentId", documentId).eq("pageNumber", pageNumber),
      )
      .first();
  },
});

export const getOwnedInternal = internalQuery({
  args: { documentId: v.id("documents"), ownerId: v.string() },
  handler: async (ctx, { documentId, ownerId }) => {
    const document = await ctx.db.get(documentId);
    if (!document || document.ownerId !== ownerId) throw new Error("Document not found.");
    return document;
  },
});

export const getForIndexing = internalQuery({
  args: { documentId: v.id("documents") },
  handler: async (ctx, { documentId }) => ctx.db.get(documentId),
});

export const setIndexing = internalMutation({
  args: { documentId: v.id("documents"), status: v.literal("processing") },
  handler: async (ctx, { documentId, status }) => {
    const document = await ctx.db.get(documentId);
    if (document) await ctx.db.patch(documentId, { status, updatedAt: Date.now() });
  },
});

export const savePageChunks = internalMutation({
  args: {
    documentId: v.id("documents"),
    pageNumber: v.number(),
    pageText: v.string(),
    chunks: v.array(pageChunk),
  },
  handler: async (ctx, { documentId, pageNumber, pageText, chunks }) => {
    const document = await ctx.db.get(documentId);
    if (!document) throw new Error("Document not found while indexing.");
    await ctx.db.insert("pages", {
      ownerId: document.ownerId,
      documentId,
      pageNumber,
      text: pageText.slice(0, 900_000),
    });
    for (const chunk of chunks) {
      await ctx.db.insert("chunks", {
        ownerId: document.ownerId,
        documentId,
        pageNumber,
        ...chunk,
      });
    }
  },
});

export const finishIndexing = internalMutation({
  args: {
    documentId: v.id("documents"),
    pageCount: v.number(),
    warnings: v.array(v.string()),
  },
  handler: async (ctx, { documentId, pageCount, warnings }) => {
    const document = await ctx.db.get(documentId);
    if (document) {
      await ctx.db.patch(documentId, {
        status: "ready",
        pageCount,
        warnings,
        ingestionError: undefined,
        updatedAt: Date.now(),
      });
    }
  },
});

export const failIndexing = internalMutation({
  args: { documentId: v.id("documents"), message: v.string() },
  handler: async (ctx, { documentId, message }) => {
    const document = await ctx.db.get(documentId);
    if (document) {
      await ctx.db.patch(documentId, {
        status: "failed",
        ingestionError: message.slice(0, 300),
        updatedAt: Date.now(),
      });
    }
  },
});

export const getPageForIndexing = internalQuery({
  args: { documentId: v.id("documents"), pageNumber: v.number() },
  handler: async (ctx, { documentId, pageNumber }) =>
    ctx.db
      .query("pages")
      .withIndex("by_document_page", (q) =>
        q.eq("documentId", documentId).eq("pageNumber", pageNumber),
      )
      .first(),
});

export const cleanupBatch = internalMutation({
  args: { documentId: v.id("documents") },
  handler: async (ctx, { documentId }) => {
    const pages = await ctx.db
      .query("pages")
      .withIndex("by_document_page", (q) => q.eq("documentId", documentId))
      .take(100);
    if (pages.length) {
      for (const page of pages) await ctx.db.delete(page._id);
      return { done: false };
    }

    const chunks = await ctx.db
      .query("chunks")
      .withIndex("by_document_chunk", (q) => q.eq("documentId", documentId))
      .take(100);
    if (chunks.length) {
      for (const chunk of chunks) await ctx.db.delete(chunk._id);
      return { done: false };
    }

    const conversation = await ctx.db
      .query("conversations")
      .withIndex("by_document_updated", (q) => q.eq("documentId", documentId))
      .first();
    if (conversation) {
      const messages = await ctx.db
        .query("messages")
        .withIndex("by_conversation_created", (q) => q.eq("conversationId", conversation._id))
        .take(100);
      for (const message of messages) await ctx.db.delete(message._id);
      if (!messages.length) await ctx.db.delete(conversation._id);
      return { done: false };
    }

    if (await ctx.db.get(documentId)) await ctx.db.delete(documentId);
    return { done: true };
  },
});

export const continueDelete = internalAction({
  args: { documentId: v.id("documents") },
  handler: async (ctx, { documentId }) => {
    let result = await ctx.runMutation(internal.documents.cleanupBatch, { documentId });
    for (let batch = 0; batch < 20 && !result.done; batch += 1) {
      result = await ctx.runMutation(internal.documents.cleanupBatch, { documentId });
    }
    if (!result.done) await ctx.scheduler.runAfter(0, internal.documents.continueDelete, { documentId });
  },
});
