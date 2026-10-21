# NotebookLLM Lite Cloud

This is the cloud edition of NotebookLLM Lite. The React site can be hosted as a Render Static Site. Convex provides the application database and functions, Better Auth handles accounts, and a private Supabase Storage bucket stores PDFs. Gemini provides embeddings and grounded answers. PostHog analytics are optional.

The existing local FastAPI/PostgreSQL app remains at the repository root. The cloud edition starts with a fresh account and does not copy local database rows or files. Re-upload PDFs after setup.

## What is implemented

- Email/password registration and sign-in through Better Auth's Convex component.
- Optional Google sign-in through Better Auth.
- User-owned notebooks and documents, with ownership checked in every public data function.
- Direct browser PDF uploads through short-lived signed URLs to a private Supabase Storage bucket.
- Text extraction by PDF page, page-aware chunks, Gemini `gemini-embedding-001` vectors (768 dimensions), and Convex vector search.
- Separate conversations and saved history for each document, with citations that open the stored source page text.
- Document deletion that removes the Supabase Storage object and cleans up its pages, chunks, and conversations in batches.
- Bring-your-own Gemini API key. The browser encrypts the key with a public key before sending it; the Convex action checks it and stores it encrypted at rest. A private server key and AES encryption secret are required.
- Optional PostHog events for product usage. Autocapture and session recordings are disabled. Events omit filenames, PDF text, questions, and answers.

PDF text is sent to Google Gemini for embeddings and answers. The Supabase bucket stays private; document links are time-limited. PostHog is optional and receives no document or chat content.

## Run the cloud app locally

You need Node.js 24 for local Convex actions, a Convex account, and a Supabase project with a private Storage bucket. The local edition still uses the root README's Python, Docker, and Ollama steps.

1. Create a Supabase project. In **Storage**, create a private bucket named `documents`, allow only `application/pdf`, and set its file-size limit to 50 MB. Copy the project URL and a server-only **Secret key** (`sb_secret_...`) from the project's API settings. If your project only shows the older `service_role` key, that also works. This privileged key must never go in `.env.local`, a `VITE_` variable, or source control.

2. From this folder, install packages and start a Convex development deployment:

   ```powershell
   cd cloud
   npm install
   npx convex dev
   ```

   Sign in to Convex when prompted and create a development project. Keep `convex dev` running. It writes the development Convex URLs to `.env.local` and generates the typed files in `convex/_generated/`.

3. In a second PowerShell terminal, create a key pair for protecting users' Gemini keys and configure the Convex development deployment. For the private PEM, use `--from-file`; passing a multiline PEM as a command argument does not work in PowerShell.

   ```powershell
   cd cloud
   node scripts/generate-key-pair.mjs
   $publicKey = Get-Content .\.gemini-key-encryption-public.txt -Raw
   npx convex env set BETTER_AUTH_SECRET (node -e "process.stdout.write(require('node:crypto').randomBytes(32).toString('base64'))")
   npx convex env set GEMINI_KEY_DECRYPTION_PRIVATE_KEY --from-file .gemini-key-encryption-private.pem
   npx convex env set GEMINI_KEY_ENCRYPTION_SECRET (node -e "process.stdout.write(require('node:crypto').randomBytes(32).toString('base64'))")
   npx convex env set SITE_URL http://localhost:5173
   npx convex env set GEMINI_MODEL gemini-3.8-flash
   npx convex env set SUPABASE_URL https://YOUR-PROJECT-REF.supabase.co
   npx convex env set SUPABASE_SECRET_KEY YOUR-SUPABASE-SECRET-KEY
   npx convex env set SUPABASE_STORAGE_BUCKET documents
   $envLines = @(Get-Content .\.env.local -ErrorAction SilentlyContinue | Where-Object { $_ -notmatch '^(VITE_GEMINI_KEY_ENCRYPTION_PUBLIC_KEY|VITE_SITE_URL|VITE_POSTHOG_HOST)=' })
   $envLines += "VITE_GEMINI_KEY_ENCRYPTION_PUBLIC_KEY=$publicKey"
   $envLines += "VITE_SITE_URL=http://localhost:5173"
   $envLines += "VITE_POSTHOG_HOST=https://us.i.posthog.com"
   Set-Content -LiteralPath .\.env.local -Value $envLines
   ```

   Replace the Supabase examples with your project values. Keep `.gemini-key-encryption-private.pem` private; it is ignored by Git. The public key can be exposed to the browser. If you rotate either encryption key later, users will need to enter their Gemini keys again unless you decrypt and re-encrypt the saved keys first.

   For local Google sign-in, the Google OAuth Web client needs your Vite origin (`http://localhost:5173`, or `http://localhost:5174` if Vite selected that port) and the redirect URI `http://127.0.0.1:3211/api/auth/callback/google`. Set Convex `SITE_URL` to the same Vite origin you open in the browser. Keep `GOOGLE_CLIENT_SECRET` in Convex only; do not put it in `.env.local` or a `VITE_` variable.

### Enable Google sign-in locally

Copy the Google **Client ID** in Google Cloud, then run these commands from `cloud` in PowerShell:

```powershell
$googleValue = (Get-Clipboard -Raw).Trim()
npx convex env set GOOGLE_CLIENT_ID $googleValue
Remove-Variable googleValue
```

Next, copy the Google **Client secret** in Google Cloud and run the same commands with `GOOGLE_CLIENT_SECRET`:

```powershell
$googleValue = (Get-Clipboard -Raw).Trim()
npx convex env set GOOGLE_CLIENT_SECRET $googleValue
Remove-Variable googleValue
```

If Vite is running at `http://localhost:5174`, also set `npx convex env set SITE_URL http://localhost:5174`. Keep `npx convex dev` running while you add the variables so they are saved to the development deployment you are using.

4. Once `convex dev` has written `VITE_CONVEX_URL` and `VITE_CONVEX_SITE_URL` to `.env.local`, run the browser app in the second terminal:

   ```powershell
   npm run dev
   ```

   Open [http://localhost:5173](http://localhost:5173), create an account, open **Settings**, and add your Gemini API key. Then create a notebook and upload a text-based PDF. Scanned PDFs need OCR, which is not included yet.

PostHog is optional. To enable it locally, add `VITE_POSTHOG_KEY` to `.env.local`. Use a PostHog **project token** (`phc_...`), never a personal API key. Analytics can be left blank.

## Deploy

### 1. Prepare production services

- Create a production Convex deployment and deploy the backend from this folder with `npx convex deploy`.
- Create a separate private Supabase Storage bucket named `documents`, restrict it to PDF files, and set a 50 MB limit. Set the production Convex environment variables `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, and `SUPABASE_STORAGE_BUCKET`. Keep the secret key only in Convex's server environment.
- Create a separate Gemini-key encryption pair for production. Do not reuse the development private key. Set the private key and a fresh 32-byte AES secret on the production Convex deployment.
- Set `BETTER_AUTH_SECRET`, `SITE_URL`, `GEMINI_MODEL`, `GEMINI_KEY_DECRYPTION_PRIVATE_KEY`, and `GEMINI_KEY_ENCRYPTION_SECRET` on the production Convex deployment. `SITE_URL` must match the final Render URL. Convex supplies `CONVEX_SITE_URL` to Better Auth for the auth API.
- Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` on the production Convex deployment, and register the production Convex auth callback with the production Google OAuth client.

### 2. Deploy the frontend to Render

Create a **Static Site** in Render from the GitHub repository and set:

| Setting | Value |
| --- | --- |
| Root directory | `cloud` |
| Build command | `npm install && npm run build` |
| Publish directory | `dist` |

Add these frontend build environment variables in Render: `VITE_CONVEX_URL`, `VITE_CONVEX_SITE_URL`, `VITE_SITE_URL`, and `VITE_GEMINI_KEY_ENCRYPTION_PUBLIC_KEY`. Set `VITE_POSTHOG_KEY` and `VITE_POSTHOG_HOST` only if analytics is enabled. The public-key value is the one-line contents of `.gemini-key-encryption-public.txt`.

After Render creates the site URL, set that URL as Convex's `SITE_URL` and `VITE_SITE_URL`, then redeploy the Convex functions and Render site. Verify account creation, sign-in, PDF upload/indexing, a cited answer, conversation history, and deletion before sharing the URL.

## Data and service notes

- A Convex development deployment and the production deployment have separate data and environment variables.
- Supabase is used for PDF object storage only in this version; Convex still handles sign-in, the app database, and functions.
- The Supabase secret key is used only by Convex to create temporary signed upload/download URLs, read files for indexing, and delete objects. It is never sent to the browser.
- Each user supplies and pays for their own Gemini API usage. The app uses the saved key for both embeddings and answer generation.
- Cloud PDFs are stored in Supabase Storage and extracted text is stored in Convex. Deleting a PDF also deletes its chat history and indexed content.
- The current cloud edition does not import the root app's PostgreSQL database or `backend/uploads` files.
- OCR, streaming answers, email verification, billing/quotas, and automated local-to-cloud data import remain follow-up work before opening registration broadly.

## Useful commands

```powershell
npm run dev       # Vite app; run npx convex dev in another terminal
npm run build     # typecheck and create cloud/dist/
npx convex deploy # deploy the Convex backend
```
