"use node";

import {
  createCipheriv,
  createDecipheriv,
  createPrivateKey,
  privateDecrypt,
  randomBytes,
} from "node:crypto";
import { v } from "convex/values";
import { internal } from "./_generated/api";
import { action } from "./_generated/server";
import { requireUser } from "./lib/identity";

function encryptionKey(): Buffer {
  const encoded = process.env.GEMINI_KEY_ENCRYPTION_SECRET;
  if (!encoded) throw new Error("Gemini key encryption is not configured on the server.");
  const key = Buffer.from(encoded, "base64");
  if (key.length !== 32) throw new Error("Gemini key encryption secret must be 32 bytes, base64 encoded.");
  return key;
}

function encryptKey(plainText: string): string {
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", encryptionKey(), iv);
  const ciphertext = Buffer.concat([cipher.update(plainText, "utf8"), cipher.final()]);
  return [iv.toString("base64url"), cipher.getAuthTag().toString("base64url"), ciphertext.toString("base64url")].join(".");
}

export function decryptGeminiKey(encrypted: string): string {
  const [ivText, tagText, dataText] = encrypted.split(".");
  if (!ivText || !tagText || !dataText) throw new Error("Stored Gemini key cannot be read.");
  const decipher = createDecipheriv("aes-256-gcm", encryptionKey(), Buffer.from(ivText, "base64url"));
  decipher.setAuthTag(Buffer.from(tagText, "base64url"));
  return Buffer.concat([
    decipher.update(Buffer.from(dataText, "base64url")),
    decipher.final(),
  ]).toString("utf8");
}

export const saveGeminiKey = action({
  args: { encryptedApiKey: v.string() },
  handler: async (ctx, { encryptedApiKey }) => {
    const ownerId = await requireUser(ctx);
    const privateKeyPem = process.env.GEMINI_KEY_DECRYPTION_PRIVATE_KEY?.replace(/\\n/g, "\n");
    if (!privateKeyPem) throw new Error("Gemini key encryption is not configured on the server.");
    let cleanKey: string;
    try {
      cleanKey = privateDecrypt(
        { key: createPrivateKey(privateKeyPem), oaepHash: "sha256" },
        Buffer.from(encryptedApiKey, "base64url"),
      ).toString("utf8").trim();
    } catch {
      throw new Error("Could not read the encrypted Gemini key. Refresh the app and try again.");
    }
    if (cleanKey.length < 20 || cleanKey.length > 200) throw new Error("Enter a valid Gemini API key.");
    const model = process.env.GEMINI_MODEL || "gemini-3.8-flash";
    const response = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`, {
      method: "POST",
      headers: { "content-type": "application/json", "x-goog-api-key": cleanKey },
      body: JSON.stringify({ contents: [{ parts: [{ text: "Reply with OK." }] }] }),
    });
    if (!response.ok) throw new Error("Gemini could not validate that key. Check it in Google AI Studio and try again.");
    await response.body?.cancel();
    await ctx.runMutation(internal.settings.saveEncrypted, {
      ownerId,
      encryptedGeminiKey: encryptKey(cleanKey),
    });
    return { saved: true, model };
  },
});

export const clearGeminiKey = action({
  args: {},
  handler: async (ctx) => {
    const ownerId = await requireUser(ctx);
    await ctx.runMutation(internal.settings.clearEncrypted, { ownerId });
    return { cleared: true };
  },
});
