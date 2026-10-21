import { v } from "convex/values";
import { internal } from "./_generated/api";
import { action } from "./_generated/server";
import { requireUser } from "./lib/identity";
import { createSupabaseDownloadUrl, createSupabaseUploadUrl, deleteSupabaseObject } from "./lib/supabaseStorage";

export const createUploadUrl = action({
  args: { documentId: v.id("documents") },
  handler: async (ctx, { documentId }): Promise<{ url: string; contentType: string }> => {
    const ownerId = await requireUser(ctx);
    const document = await ctx.runQuery(internal.documents.getOwnedInternal, { documentId, ownerId });
    if (document.status !== "uploading") throw new Error("This document is not awaiting an upload.");
    return { url: await createSupabaseUploadUrl(document.storageKey), contentType: "application/pdf" };
  },
});

export const documentUrl = action({
  args: { documentId: v.id("documents") },
  handler: async (ctx, { documentId }): Promise<{ url: string }> => {
    const ownerId = await requireUser(ctx);
    const document = await ctx.runQuery(internal.documents.getOwnedInternal, { documentId, ownerId });
    return { url: await createSupabaseDownloadUrl(document.storageKey, 300) };
  },
});

export const removeDocument = action({
  args: { documentId: v.id("documents") },
  handler: async (ctx, { documentId }): Promise<{ deleted: boolean }> => {
    const ownerId = await requireUser(ctx);
    const document = await ctx.runQuery(internal.documents.getOwnedInternal, { documentId, ownerId });
    await deleteSupabaseObject(document.storageKey);
    let result: { done: boolean } = await ctx.runMutation(internal.documents.cleanupBatch, { documentId });
    for (let batch = 0; batch < 20 && !result.done; batch += 1) {
      result = await ctx.runMutation(internal.documents.cleanupBatch, { documentId });
    }
    if (!result.done) await ctx.scheduler.runAfter(0, internal.documents.continueDelete, { documentId });
    return { deleted: result.done };
  },
});
