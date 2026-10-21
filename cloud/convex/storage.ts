import { v } from "convex/values";
import { internal } from "./_generated/api";
import { action, internalAction } from "./_generated/server";
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
  handler: async (ctx, { documentId }): Promise<{ deleted: boolean; storageCleanupPending: boolean }> => {
    const ownerId = await requireUser(ctx);
    const document = await ctx.runQuery(internal.documents.getOwnedInternal, { documentId, ownerId });
    let storageCleanupPending = false;
    try {
      await deleteSupabaseObject(document.storageKey);
    } catch {
      // A storage outage must not strand the document and its indexed content in the app.
      // Retry the object deletion in the background after the Supabase project is reachable.
      storageCleanupPending = true;
      await ctx.scheduler.runAfter(60_000, internal.storage.retryStorageDelete, {
        storageKey: document.storageKey,
        attempt: 0,
      });
    }
    let result: { done: boolean } = await ctx.runMutation(internal.documents.cleanupBatch, { documentId });
    for (let batch = 0; batch < 20 && !result.done; batch += 1) {
      result = await ctx.runMutation(internal.documents.cleanupBatch, { documentId });
    }
    if (!result.done) await ctx.scheduler.runAfter(0, internal.documents.continueDelete, { documentId });
    return { deleted: result.done, storageCleanupPending };
  },
});

const storageDeleteRetryDelays = [5 * 60_000, 30 * 60_000, 2 * 60 * 60_000, 24 * 60 * 60_000];

export const retryStorageDelete = internalAction({
  args: { storageKey: v.string(), attempt: v.number() },
  handler: async (ctx, { storageKey, attempt }) => {
    try {
      await deleteSupabaseObject(storageKey);
    } catch {
      if (attempt < storageDeleteRetryDelays.length) {
        await ctx.scheduler.runAfter(storageDeleteRetryDelays[attempt], internal.storage.retryStorageDelete, {
          storageKey,
          attempt: attempt + 1,
        });
      } else {
        console.warn("Supabase storage cleanup could not complete after retries.");
      }
    }
  },
});
