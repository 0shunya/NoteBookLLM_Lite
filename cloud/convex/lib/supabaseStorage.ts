const STORAGE_BUCKET = process.env.SUPABASE_STORAGE_BUCKET || "documents";

function storageConfig() {
  const baseUrl = process.env.SUPABASE_URL?.replace(/\/+$/, "");
  const apiKey = process.env.SUPABASE_SECRET_KEY || process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!baseUrl || !apiKey) {
    throw new Error("Supabase Storage is not configured on the server (SUPABASE_URL and SUPABASE_SECRET_KEY).");
  }
  return { baseUrl, apiKey, legacyServiceRole: !apiKey.startsWith("sb_secret_") };
}

function encodeStoragePath(path: string): string {
  return path.split("/").map(encodeURIComponent).join("/");
}

async function storageRequest(path: string, init: RequestInit = {}): Promise<Response> {
  const { baseUrl, apiKey, legacyServiceRole } = storageConfig();
  const headers = new Headers(init.headers);
  headers.set("apikey", apiKey);
  if (legacyServiceRole) headers.set("authorization", `Bearer ${apiKey}`);
  const response = await fetch(`${baseUrl}/storage/v1${path}`, {
    ...init,
    headers,
  });
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new Error(`Supabase Storage request failed (${response.status})${detail ? `: ${detail.slice(0, 240)}` : "."}`);
  }
  return response;
}

export async function createSupabaseUploadUrl(path: string): Promise<string> {
  const objectPath = `${encodeURIComponent(STORAGE_BUCKET)}/${encodeStoragePath(path)}`;
  const response = await storageRequest(`/object/upload/sign/${objectPath}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: "{}",
  });
  const result = await response.json() as { url?: string };
  if (!result.url) throw new Error("Supabase did not return a signed upload URL.");
  const { baseUrl } = storageConfig();
  return new URL(`/storage/v1${result.url}`, baseUrl).toString();
}

export async function createSupabaseDownloadUrl(path: string, expiresIn: number): Promise<string> {
  const objectPath = `${encodeURIComponent(STORAGE_BUCKET)}/${encodeStoragePath(path)}`;
  const response = await storageRequest(`/object/sign/${objectPath}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ expiresIn }),
  });
  const result = await response.json() as { signedURL?: string };
  if (!result.signedURL) throw new Error("Supabase did not return a signed document URL.");
  const { baseUrl } = storageConfig();
  return new URL(`/storage/v1${result.signedURL}`, baseUrl).toString();
}

export async function downloadSupabaseObject(path: string): Promise<Uint8Array> {
  const objectPath = `${encodeURIComponent(STORAGE_BUCKET)}/${encodeStoragePath(path)}`;
  const response = await storageRequest(`/object/authenticated/${objectPath}`);
  return new Uint8Array(await response.arrayBuffer());
}

export async function deleteSupabaseObject(path: string): Promise<void> {
  const bucket = encodeURIComponent(STORAGE_BUCKET);
  try {
    await storageRequest(`/object/${bucket}`, {
      method: "DELETE",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ prefixes: [path] }),
    });
  } catch (error) {
    if (error instanceof Error && error.message.includes("(404)")) return;
    throw error;
  }
}
