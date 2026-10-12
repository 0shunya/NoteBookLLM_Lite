"use node";

import { DeleteObjectCommand, PutObjectCommand, GetObjectCommand } from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";
import { v } from "convex/values";
import { internal } from "./_generated/api";
import { action } from "./_generated/server";
import { requireUser } from "./lib/identity";
import { r2Bucket, r2Client } from "./lib/r2";

export const createUploadUrl = action({
  args: { documentId: v.id("documents") },
  handler: async (ctx, { documentId }): Promise<{ url: string; contentType: string }> => {
    const ownerId = await requireUser(ctx);
    const document = await ctx.runQuery(internal.documents.getOwnedInternal, { documentId, ownerId });
    if (document.status !== "uploading") throw new Error("This document is not awaiting an upload.");
    const url = await getSignedUrl(
      r2Client(),
      new PutObjectCommand({
        Bucket: r2Bucket(),
        Key: document.storageKey,
        ContentType: "application/pdf",
      }),
      { expiresIn: 300 },
    );
    return { url, contentType: "application/pdf" };
  },
});

export const documentUrl = action({
  args: { documentId: v.id("documents") },
  handler: async (ctx, { documentId }): Promise<{ url: string }> => {
    const ownerId = await requireUser(ctx);
    const document = await ctx.runQuery(internal.documents.getOwnedInternal, { documentId, ownerId });
    const url = await getSignedUrl(
      r2Client(),
      new GetObjectCommand({ Bucket: r2Bucket(), Key: document.storageKey }),
      { expiresIn: 300 },
    );
    return { url };
  },
});

export const removeDocument = action({
  args: { documentId: v.id("documents") },
  handler: async (ctx, { documentId }): Promise<{ deleted: boolean }> => {
    const ownerId = await requireUser(ctx);
    const document = await ctx.runQuery(internal.documents.getOwnedInternal, { documentId, ownerId });
    await r2Client().send(new DeleteObjectCommand({ Bucket: r2Bucket(), Key: document.storageKey }));
    let result: { done: boolean } = await ctx.runMutation(internal.documents.cleanupBatch, { documentId });
    for (let batch = 0; batch < 20 && !result.done; batch += 1) {
      result = await ctx.runMutation(internal.documents.cleanupBatch, { documentId });
    }
    if (!result.done) await ctx.scheduler.runAfter(0, internal.documents.continueDelete, { documentId });
    return { deleted: result.done };
  },
});
