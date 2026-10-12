import { v } from "convex/values";
import { internalMutation, internalQuery, query } from "./_generated/server";
import { requireUser } from "./lib/identity";

export const status = query({
  args: {},
  handler: async (ctx) => {
    const ownerId = await requireUser(ctx);
    const record = await ctx.db
      .query("userSettings")
      .withIndex("by_owner", (q) => q.eq("ownerId", ownerId))
      .first();
    return { geminiConfigured: Boolean(record?.encryptedGeminiKey) };
  },
});

export const getEncrypted = internalQuery({
  args: { ownerId: v.string() },
  handler: async (ctx, { ownerId }) =>
    ctx.db
      .query("userSettings")
      .withIndex("by_owner", (q) => q.eq("ownerId", ownerId))
      .first(),
});

export const saveEncrypted = internalMutation({
  args: { ownerId: v.string(), encryptedGeminiKey: v.string() },
  handler: async (ctx, args) => {
    const record = await ctx.db
      .query("userSettings")
      .withIndex("by_owner", (q) => q.eq("ownerId", args.ownerId))
      .first();
    if (record) {
      await ctx.db.patch(record._id, {
        encryptedGeminiKey: args.encryptedGeminiKey,
        updatedAt: Date.now(),
      });
    } else {
      await ctx.db.insert("userSettings", { ...args, updatedAt: Date.now() });
    }
  },
});

export const clearEncrypted = internalMutation({
  args: { ownerId: v.string() },
  handler: async (ctx, { ownerId }) => {
    const record = await ctx.db
      .query("userSettings")
      .withIndex("by_owner", (q) => q.eq("ownerId", ownerId))
      .first();
    if (record) await ctx.db.delete(record._id);
  },
});

export const readGeminiKey = internalQuery({
  args: { ownerId: v.string() },
  handler: async (ctx, { ownerId }) => {
    const record = await ctx.db
      .query("userSettings")
      .withIndex("by_owner", (q) => q.eq("ownerId", ownerId))
      .first();
    return record?.encryptedGeminiKey ?? null;
  },
});
