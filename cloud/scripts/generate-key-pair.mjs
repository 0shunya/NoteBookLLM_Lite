import { generateKeyPairSync } from "node:crypto";
import { writeFile } from "node:fs/promises";

const { privateKey, publicKey } = generateKeyPairSync("rsa", {
  modulusLength: 3072,
  publicKeyEncoding: { type: "spki", format: "pem" },
  privateKeyEncoding: { type: "pkcs8", format: "pem" },
});

await writeFile(".gemini-key-encryption-private.pem", privateKey, { mode: 0o600 });
const publicDerBase64 = publicKey
  .replace(/-----BEGIN PUBLIC KEY-----|-----END PUBLIC KEY-----|\s/g, "");
await writeFile(".gemini-key-encryption-public.txt", publicDerBase64, { mode: 0o644 });
process.stdout.write("Created .gemini-key-encryption-private.pem and .gemini-key-encryption-public.txt\n");
