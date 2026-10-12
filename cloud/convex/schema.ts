import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

export default defineSchema({
  notebooks: defineTable({
    ownerId: v.string(),
    title: v.string(),
    createdAt: v.number(),
  }).index("by_owner_created", ["ownerId", "createdAt"]),

  documents: defineTable({
    ownerId: v.string(),
    notebookId: v.id("notebooks"),
    filename: v.string(),
    storageKey: v.string(),
    sha256: v.string(),
    sizeBytes: v.number(),
    pageCount: v.number(),
    status: v.union(
      v.literal("uploading"),
      v.literal("queued"),
      v.literal("processing"),
      v.literal("ready"),
      v.literal("failed"),
    ),
    ingestionError: v.optional(v.string()),
    warnings: v.array(v.string()),
    createdAt: v.number(),
    updatedAt: v.number(),
  })
    .index("by_notebook_created", ["notebookId", "createdAt"])
    .index("by_notebook_hash", ["notebookId", "sha256"])
    .index("by_owner", ["ownerId"]),

  pages: defineTable({
    ownerId: v.string(),
    documentId: v.id("documents"),
    pageNumber: v.number(),
    text: v.string(),
  }).index("by_document_page", ["documentId", "pageNumber"]),

  chunks: defineTable({
    ownerId: v.string(),
    documentId: v.id("documents"),
    pageNumber: v.number(),
    chunkIndex: v.number(),
    text: v.string(),
    embedding: v.array(v.float64()),
  })
    .index("by_document_chunk", ["documentId", "chunkIndex"])
    .vectorIndex("by_embedding", {
      vectorField: "embedding",
      dimensions: 768,
      filterFields: ["ownerId", "documentId"],
    }),

  conversations: defineTable({
    ownerId: v.string(),
    documentId: v.id("documents"),
    title: v.string(),
    createdAt: v.number(),
    updatedAt: v.number(),
  })
    .index("by_document_updated", ["documentId", "updatedAt"])
    .index("by_owner", ["ownerId"]),

  messages: defineTable({
    ownerId: v.string(),
    conversationId: v.id("conversations"),
    role: v.union(v.literal("user"), v.literal("assistant")),
    content: v.string(),
    sources: v.optional(v.array(v.object({
      marker: v.number(),
      chunkId: v.id("chunks"),
      pageNumber: v.number(),
      excerpt: v.string(),
    }))),
    failed: v.optional(v.boolean()),
    createdAt: v.number(),
  }).index("by_conversation_created", ["conversationId", "createdAt"]),

  userSettings: defineTable({
    ownerId: v.string(),
    encryptedGeminiKey: v.string(),
    updatedAt: v.number(),
  }).index("by_owner", ["ownerId"]),
});
