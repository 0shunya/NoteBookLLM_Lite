import { v } from "convex/values";
import { mutation, query } from "./_generated/server";
import { requireUser } from "./lib/identity";

export const list = query({
  args: {},
  handler: async (ctx) => {
    const ownerId = await requireUser(ctx);
    return ctx.db
      .query("notebooks")
      .withIndex("by_owner_created", (q) => q.eq("ownerId", ownerId))
      .order("desc")
      .collect();
  },
});

export const create = mutation({
  args: { title: v.string() },
  handler: async (ctx, { title }) => {
    const ownerId = await requireUser(ctx);
    const cleanTitle = title.trim().slice(0, 100);
    if (!cleanTitle) throw new Error("Give the notebook a name first.");
    return ctx.db.insert("notebooks", {
      ownerId,
      title: cleanTitle,
      createdAt: Date.now(),
    });
  },
});

export const getOwned = query({
  args: { notebookId: v.id("notebooks") },
  handler: async (ctx, { notebookId }) => {
    const ownerId = await requireUser(ctx);
    const notebook = await ctx.db.get(notebookId);
    if (!notebook || notebook.ownerId !== ownerId) throw new Error("Notebook not found.");
    return notebook;
  },
});
