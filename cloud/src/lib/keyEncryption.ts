function decodeBase64(encoded: string): ArrayBuffer {
  const binary = atob(encoded.trim());
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return bytes.buffer;
}

function toBase64Url(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

export async function encryptGeminiKey(apiKey: string): Promise<string> {
  const publicPem = import.meta.env.VITE_GEMINI_KEY_ENCRYPTION_PUBLIC_KEY;
  if (!publicPem) throw new Error("Gemini key encryption is not configured for this site.");
  const publicKey = await crypto.subtle.importKey(
    "spki",
    decodeBase64(publicPem),
    { name: "RSA-OAEP", hash: "SHA-256" },
    false,
    ["encrypt"],
  );
  const encrypted = await crypto.subtle.encrypt(
    { name: "RSA-OAEP" },
    publicKey,
    new TextEncoder().encode(apiKey),
  );
  return toBase64Url(new Uint8Array(encrypted));
}
