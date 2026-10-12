# NotebookLM Lite Cloud

This is the cloud edition of NotebookLM Lite. It runs as a Vite/React site on Cloudflare Pages, with Convex for the application database and functions, Better Auth for accounts, Cloudflare R2 for private PDFs, Gemini for embeddings and grounded answers, and optional PostHog product analytics.

The existing local FastAPI/PostgreSQL app remains at the repository root. The cloud edition is a fresh deployment: local PostgreSQL rows and files are not copied automatically. Re-upload PDFs to the cloud edition after setup.

## What is implemented

- Email/password registration and sign-in through Better Auth's Convex component.
- User-owned notebooks and documents, with ownership checked in every public data function.
- Direct browser upload to a private R2 bucket using short-lived, PDF-only signed URLs.
- Text extraction by PDF page, page-aware chunks, Gemini `gemini-embedding-001` vectors (768 dimensions), and Convex vector search.
- Separate conversations and saved history for each document, with citations that open the stored source page text.
- Document deletion that removes the R2 object and cleans up its pages, chunks, and conversations in batches.
- Bring-your-own Gemini API key. The browser encrypts the key with a public key before sending it; the Convex action checks it and stores it encrypted at rest. A private server key and AES encryption secret are required.
- Optional PostHog events for product usage. Autocapture and session recordings are disabled. Events omit filenames, PDF text, questions, and answers.

PDF text is sent to Google Gemini for embeddings and answers. The R2 bucket stays private; document links are time-limited. PostHog is optional and receives no document or chat content.

## Run the cloud app locally

You need Node.js 24 for local Convex actions, a Convex account, and a Cloudflare account with an R2 bucket. The local edition still uses the root README's Python, Docker, and Ollama steps.

1. From this folder, install the packages and connect a Convex development deployment:

   ```powershell
   cd cloud
   npm install
   npx convex dev
   ```

   Sign in to Convex when prompted and create a development project. Keep `convex dev` running. It writes the development Convex URLs to `.env.local` and generates the typed files in `convex/_generated/`.

2. In a second PowerShell terminal, create a key pair for protecting users' Gemini keys:

   ```powershell
   cd cloud
   node scripts/generate-key-pair.mjs
   $privateKey = (Get-Content .\.gemini-key-encryption-private.pem -Raw).Replace("`r`n", "\n").Replace("`n", "\n")
   $publicKey = Get-Content .\.gemini-key-encryption-public.txt -Raw
   npx convex env set BETTER_AUTH_SECRET (node -e "process.stdout.write(require('node:crypto').randomBytes(32).toString('base64'))")
   npx convex env set GEMINI_KEY_DECRYPTION_PRIVATE_KEY $privateKey
   npx convex env set GEMINI_KEY_ENCRYPTION_SECRET (node -e "process.stdout.write(require('node:crypto').randomBytes(32).toString('base64'))")
   npx convex env set SITE_URL http://localhost:5173
   npx convex env set GEMINI_MODEL gemini-3.8-flash
   Add-Content .\.env.local "VITE_GEMINI_KEY_ENCRYPTION_PUBLIC_KEY=$publicKey"
   Add-Content .\.env.local "VITE_SITE_URL=http://localhost:5173"
   Add-Content .\.env.local "VITE_POSTHOG_HOST=https://us.i.posthog.com"
   ```

   Keep `.gemini-key-encryption-private.pem` private. It is ignored by Git. The public key can be exposed to the browser. If you rotate either encryption key later, first decrypt and re-encrypt every saved Gemini key, or users will need to enter their keys again.

3. Create a private R2 bucket and an R2 API token with read/write access to that bucket. Configure its CORS policy using [r2-cors.example.json](r2-cors.example.json), replacing the Pages origin with your actual site origin. For local use, keep `http://localhost:5173` in the list. Add the account ID, bucket, and token values to the Convex development deployment:

   ```powershell
   npx convex env set R2_ACCOUNT_ID your-cloudflare-account-id
   npx convex env set R2_BUCKET your-private-bucket-name
   npx convex env set R2_ACCESS_KEY_ID your-r2-access-key-id
   npx convex env set R2_SECRET_ACCESS_KEY your-r2-secret-access-key
   ```

   Use the Cloudflare **R2 S3 API** access key and secret. Do not enable public bucket access. The browser only receives short-lived signed URLs.

4. Once `convex dev` has written `VITE_CONVEX_URL` and `VITE_CONVEX_SITE_URL` to `.env.local`, run the browser app in that second terminal:

   ```powershell
   npm run dev
   ```

   Open [http://localhost:5173](http://localhost:5173), create an account, open **Settings**, and add your Gemini API key. Then create a notebook and upload a text-based PDF. Scanned PDFs need OCR, which is not included yet.

PostHog is optional. To enable it locally, add `VITE_POSTHOG_KEY` to `.env.local`. Use a PostHog **project token** (`phc_...`), never a personal API key. Analytics can be left blank.

## Deploy

### 1. Prepare production services

- Create a production Convex deployment and deploy the backend from this folder with `npx convex deploy`.
- Create a private R2 bucket and a bucket-scoped API token. Set the R2 CORS allowlist to the final `https://...pages.dev` origin and any custom domain.
- Create a separate encryption key pair for production. Do not reuse the development private key. Set the private key and a fresh 32-byte AES secret on the production Convex deployment.
- Set these Convex environment variables on production: `BETTER_AUTH_SECRET`, `SITE_URL`, `GEMINI_MODEL`, `GEMINI_KEY_DECRYPTION_PRIVATE_KEY`, `GEMINI_KEY_ENCRYPTION_SECRET`, `R2_ACCOUNT_ID`, `R2_BUCKET`, `R2_ACCESS_KEY_ID`, and `R2_SECRET_ACCESS_KEY`.
- `SITE_URL` must be the final Pages origin. Convex supplies `CONVEX_SITE_URL` to Better Auth for the auth API.

### 2. Deploy the frontend to Cloudflare Pages

Connect the GitHub repository to Cloudflare Pages and set:

| Setting | Value |
| --- | --- |
| Root directory | `cloud` |
| Build command | `npm run build` |
| Build output directory | `dist` |
| Node.js | 22.12 or newer |

Set these **build** environment variables for both production and preview deployments as appropriate: `VITE_CONVEX_URL`, `VITE_CONVEX_SITE_URL`, `VITE_SITE_URL`, and `VITE_GEMINI_KEY_ENCRYPTION_PUBLIC_KEY`. Set `VITE_POSTHOG_KEY` and `VITE_POSTHOG_HOST` only if analytics is enabled. The public-key value is the one-line contents of `.gemini-key-encryption-public.txt`.

After the first Pages deployment, add its `pages.dev` origin to the R2 CORS rules and Convex `SITE_URL`, then redeploy the Convex functions and Pages site. Verify account creation, sign-in, PDF upload/indexing, a cited answer, conversation history, and deletion before sharing the URL.

## Data and service notes

- A Convex development deployment and the production deployment have separate data and environment variables.
- Each user supplies and pays for their own Gemini API usage. The app uses the saved key for both embeddings and answer generation.
- Cloud PDFs and extracted text are stored in R2 and Convex, respectively. Deleting a PDF also deletes its chat history and indexed content.
- The current cloud edition does not import the root app's PostgreSQL database or `backend/uploads` files.
- OCR, streaming answers, email verification, billing/quotas, and automated local-to-cloud data import remain follow-up work before opening registration broadly.

## Useful commands

```powershell
npm run dev       # Vite app; run npx convex dev in another terminal
npm run build     # typecheck and create cloud/ dist/
npx convex deploy # deploy the Convex backend
```
