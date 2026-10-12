import { v } from "convex/values";
import {
  internalMutation,
  internalQuery,
  mutation,
  query,
} from "./_generated/server";
import { requireUser } from "./lib/identity";

export const list = query({
  args: { documentId: v.id("documents") },
  handler: async (ctx, { documentId }) => {
    const ownerId = await requireUser(ctx);
    const document = await ctx.db.get(documentId);
    if (!document || document.ownerId !== ownerId) throw new Error("Document not found.");
    return ctx.db
      .query("conversations")
      .withIndex("by_document_updated", (q) => q.eq("documentId", documentId))
      .order("desc")
      .collect();
  },
});

export const create = mutation({
  args: { documentId: v.id("documents") },
  handler: async (ctx, { documentId }) => {
    const ownerId = await requireUser(ctx);
    const document = await ctx.db.get(documentId);
    if (!document || document.ownerId !== ownerId) throw new Error("Document not found.");
    if (document.status !== "ready") throw new Error("Wait until the document is ready before chatting.");
    const now = Date.now();
    return ctx.db.insert("conversations", {
      ownerId,
      documentId,
      title: "New conversation",
      createdAt: now,
      updatedAt: now,
    });
  },
});

export const get = query({
  args: { conversationId: v.id("conversations") },
  handler: async (ctx, { conversationId }) => {
    const ownerId = await requireUser(ctx);
    const conversation = await ctx.db.get(conversationId);
    if (!conversation || conversation.ownerId !== ownerId) throw new Error("Conversation not found.");
    const messages = await ctx.db
      .query("messages")
      .withIndex("by_conversation_created", (q) => q.eq("conversationId", conversationId))
      .order("asc")
      .collect();
    return { conversation, messages };
  },
});

export const getContext = internalQuery({
  args: { conversationId: v.id("conversations"), ownerId: v.string() },
  handler: async (ctx, { conversationId, ownerId }) => {
    const conversation = await ctx.db.get(conversationId);
    if (!conversation || conversation.ownerId !== ownerId) throw new Error("Conversation not found.");
    const document = await ctx.db.get(conversation.documentId);
    if (!document || document.ownerId !== ownerId) throw new Error("Document not found.");
    if (document.status !== "ready") throw new Error("This document is still being indexed.");
    const messages = await ctx.db
      .query("messages")
      .withIndex("by_conversation_created", (q) => q.eq("conversationId", conversationId))
      .order("desc")
      .take(8);
    return { conversation, document, messages: messages.reverse() };
  },
});

export const getChunks = internalQuery({
  args: { chunkIds: v.array(v.id("chunks")) },
  handler: async (ctx, { chunkIds }) => {
    const chunks = [];
    for (const id of chunkIds) {
      const chunk = await ctx.db.get(id);
      if (chunk) chunks.push(chunk);
    }
    return chunks;
  },
});

export const addUserMessage = internalMutation({
  args: { conversationId: v.id("conversations"), ownerId: v.string(), content: v.string() },
  handler: async (ctx, { conversationId, ownerId, content }) => {
    const conversation = await ctx.db.get(conversationId);
    if (!conversation || conversation.ownerId !== ownerId) throw new Error("Conversation not found.");
    const now = Date.now();
    await ctx.db.insert("messages", {
      ownerId,
      conversationId,
      role: "user",
      content,
      createdAt: now,
    });
    const patch: { updatedAt: number; title?: string } = { updatedAt: now };
    if (conversation.title === "New conversation") {
      patch.title = content.slice(0, 95).trim() || "New conversation";
    }
    await ctx.db.patch(conversationId, patch);
  },
});

export const addAssistantMessage = internalMutation({
  args: {
    conversationId: v.id("conversations"),
    ownerId: v.string(),
    content: v.string(),
    failed: v.optional(v.boolean()),
    sources: v.optional(v.array(v.object({
      marker: v.number(),
      chunkId: v.id("chunks"),
      pageNumber: v.number(),
      excerpt: v.string(),
    }))),
  },
  handler: async (ctx, args) => {
    const conversation = await ctx.db.get(args.conversationId);
    if (!conversation || conversation.ownerId !== args.ownerId) throw new Error("Conversation not found.");
    const now = Date.now();
    await ctx.db.insert("messages", {
      ownerId: args.ownerId,
      conversationId: args.conversationId,
      role: "assistant",
      content: args.content,
      sources: args.sources,
      failed: args.failed,
      createdAt: now,
    });
    await ctx.db.patch(args.conversationId, { updatedAt: now });
  },
});
