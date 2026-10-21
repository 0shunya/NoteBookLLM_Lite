import { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import {
  Authenticated,
  AuthLoading,
  Unauthenticated,
  useAction,
  useConvexAuth,
  useMutation,
  useQuery,
} from "convex/react";
import { api } from "../convex/_generated/api";
import type { Id } from "../convex/_generated/dataModel";
import { authClient } from "./lib/authClient";
import { track } from "./lib/analytics";
import { encryptGeminiKey } from "./lib/keyEncryption";

type Source = {
  marker: number;
  chunkId: Id<"chunks">;
  pageNumber: number;
  excerpt: string;
};

function AuthScreen() {
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function signInWithGoogle() {
    setBusy(true);
    setError("");
    try {
      const result = await authClient.signIn.social({
        provider: "google",
        callbackURL: window.location.origin,
      });
      if (result.error) setError(result.error.message || "Could not sign in with Google.");
    } catch {
      setError("Google sign-in could not start. Check that the Google OAuth credentials are set in Convex.");
    } finally {
      setBusy(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const email = String(form.get("email") || "").trim();
    const password = String(form.get("password") || "");
    const name = String(form.get("name") || "").trim();
    setBusy(true);
    setError("");
    try {
      const result = mode === "signup"
        ? await authClient.signUp.email({ email, password, name })
        : await authClient.signIn.email({ email, password });
      if (result.error) setError(result.error.message || "Could not sign you in.");
    } catch {
      setError("Could not reach the sign-in service. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-page">
      <div className="auth-card">
        <BrandMark />
        <p className="eyebrow">YOUR RESEARCH, GROUNDED</p>
        <h1>{mode === "signin" ? "Welcome back" : "Create your account"}</h1>
        <p className="muted">Your notebooks, conversations, and sources stay tied to your account.</p>
        <form onSubmit={submit} className="stack-form">
          {mode === "signup" && <label>Your name<input name="name" autoComplete="name" required maxLength={80} /></label>}
          <label>Email<input name="email" type="email" autoComplete="email" required /></label>
          <label>Password<input name="password" type="password" autoComplete={mode === "signin" ? "current-password" : "new-password"} minLength={8} required /></label>
          <button className="button button-primary button-full" disabled={busy}>
            {busy ? "Please wait…" : mode === "signin" ? "Sign in" : "Create account"}
          </button>
        </form>
        {error && <p className="form-error auth-error" role="alert">{error}</p>}
        <div className="auth-divider"><span>or continue with</span></div>
        <button className="button button-google button-full" type="button" onClick={() => void signInWithGoogle()} disabled={busy}>
          <span className="google-g" aria-hidden="true">G</span>
          {busy ? "Please wait…" : "Continue with Google"}
        </button>
        <p className="auth-switch">
          {mode === "signin" ? "New here?" : "Already have an account?"}{" "}
          <button className="text-button" type="button" onClick={() => { setMode(mode === "signin" ? "signup" : "signin"); setError(""); }}>
            {mode === "signin" ? "Create an account" : "Sign in"}
          </button>
        </p>
      </div>
    </main>
  );
}

function BrandMark() {
  return <div className="brand"><span className="brand-mark">▤</span><span className="brand-name">Notebook<span>LLM</span> Lite</span></div>;
}

function LoadingScreen() {
  return <main className="loading-screen"><BrandMark /><p>Connecting your workspace…</p></main>;
}

export default function App() {
  const { isLoading } = useConvexAuth();
  if (isLoading) return <LoadingScreen />;
  return <><AuthLoading><LoadingScreen /></AuthLoading><Unauthenticated><AuthScreen /></Unauthenticated><Authenticated><Workspace /></Authenticated></>;
}

function Workspace() {
  const notebooks = useQuery(api.notebooks.list, {});
  const createNotebook = useMutation(api.notebooks.create);
  const [activeNotebookId, setActiveNotebookId] = useState<Id<"notebooks"> | null>(null);
  const [activeDocumentId, setActiveDocumentId] = useState<Id<"documents"> | null>(null);
  const [conversationId, setConversationId] = useState<Id<"conversations"> | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [createNotebookOpen, setCreateNotebookOpen] = useState(false);
  const [notebookName, setNotebookName] = useState("");
  const [creatingNotebook, setCreatingNotebook] = useState(false);
  const [createNotebookError, setCreateNotebookError] = useState("");
  const [documentToDelete, setDocumentToDelete] = useState<{ id: Id<"documents">; filename: string } | null>(null);
  const [deletingDocument, setDeletingDocument] = useState(false);
  const [deleteDocumentError, setDeleteDocumentError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [notice, setNotice] = useState("");
  const [sourceToOpen, setSourceToOpen] = useState<Source | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const messagesEnd = useRef<HTMLDivElement>(null);

  const activeNotebook = notebooks?.find((item) => item._id === activeNotebookId) ?? notebooks?.[0] ?? null;
  const documents = useQuery(api.documents.list, activeNotebook ? { notebookId: activeNotebook._id } : "skip");
  const geminiStatus = useQuery(api.settings.status, {});
  const activeDocument = documents?.find((item) => item._id === activeDocumentId) ?? null;
  const conversations = useQuery(api.conversations.list, activeDocument ? { documentId: activeDocument._id } : "skip");
  const conversationData = useQuery(api.conversations.get, conversationId ? { conversationId } : "skip");
  const page = useQuery(
    api.documents.getPage,
    sourceToOpen && activeDocument ? { documentId: activeDocument._id, pageNumber: sourceToOpen.pageNumber } : "skip",
  );

  const createUpload = useMutation(api.documents.createUpload);
  const completeUpload = useMutation(api.documents.completeUpload);
  const failUpload = useMutation(api.documents.failUpload);
  const createConversation = useMutation(api.conversations.create);
  const ask = useAction(api.chat.ask);
  const removeDocument = useAction(api.storage.removeDocument);

  const history = useMemo(() => conversations ?? [], [conversations]);

  useEffect(() => {
    if (!activeNotebook && notebooks?.length === 0) {
      setActiveDocumentId(null);
      setConversationId(null);
    }
    if (activeNotebook && activeNotebook._id !== activeNotebookId) setActiveNotebookId(activeNotebook._id);
  }, [activeNotebook, activeNotebookId, notebooks]);

  useEffect(() => {
    if (!documents) return;
    if (activeDocumentId && !documents.some((document) => document._id === activeDocumentId)) {
      setActiveDocumentId(null);
      setConversationId(null);
    }
  }, [documents, activeDocumentId]);

  useEffect(() => {
    if (!activeDocument || !history.length) return;
    if (conversationId && history.some((item) => item._id === conversationId)) return;
    setConversationId(history[0]._id);
  }, [activeDocument, conversationId, history]);

  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [conversationData?.messages]);

  useEffect(() => {
    if (!createNotebookOpen && !documentToDelete) return;
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key !== "Escape" || creatingNotebook || deletingDocument) return;
      setCreateNotebookOpen(false);
      setDocumentToDelete(null);
      setCreateNotebookError("");
      setDeleteDocumentError("");
    }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [createNotebookOpen, documentToDelete, creatingNotebook, deletingDocument]);

  function openCreateNotebook() {
    setNotebookName("");
    setCreateNotebookError("");
    setCreateNotebookOpen(true);
  }

  async function submitCreateNotebook(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const title = notebookName.trim();
    if (!title) {
      setCreateNotebookError("Enter a name for this notebook.");
      return;
    }
    setCreatingNotebook(true);
    setCreateNotebookError("");
    try {
      const id = await createNotebook({ title });
      setActiveNotebookId(id);
      setActiveDocumentId(null);
      setConversationId(null);
      setCreateNotebookOpen(false);
      track("notebook_created");
    } catch (error) {
      setCreateNotebookError(error instanceof Error ? error.message : "The notebook could not be created.");
    } finally {
      setCreatingNotebook(false);
    }
  }

  async function uploadFiles(files: FileList | null) {
    if (!files?.length || !activeNotebook) return;
    if (!geminiStatus?.geminiConfigured) {
      setSettingsOpen(true);
      setNotice("Add and check your Gemini API key before uploading a PDF.");
      return;
    }
    setUploading(true);
    setNotice("");
    for (const file of Array.from(files)) {
      if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
        setNotice(`${file.name} is not a PDF.`);
        continue;
      }
      let uploadedDocumentId: Id<"documents"> | null = null;
      try {
        const hash = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
        const fingerprint = [...new Uint8Array(hash)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
        const record = await createUpload({
          notebookId: activeNotebook._id,
          filename: file.name,
          sha256: fingerprint,
          sizeBytes: file.size,
        });
        uploadedDocumentId = record.documentId;
        setActiveDocumentId(record.documentId);
        if (record.duplicate) {
          setNotice("That PDF is already in this notebook.");
          continue;
        }
        const target = await fetchUploadUrl(record.documentId);
        const response = await fetch(target.url, {
          method: "PUT",
          headers: { "content-type": target.contentType },
          body: file,
        });
        if (!response.ok) throw new Error("Cloud storage did not accept the upload.");
        await completeUpload({ documentId: record.documentId });
        track("pdf_uploaded", { file_size_bytes: file.size });
        setNotice(`${file.name} is being indexed.`);
      } catch (error) {
        if (uploadedDocumentId) {
          await failUpload({
            documentId: uploadedDocumentId,
            message: error instanceof Error ? error.message : "Upload failed.",
          });
        }
        setNotice(error instanceof Error ? error.message : "The PDF could not be uploaded.");
      }
    }
    setUploading(false);
  }

  async function fetchUploadUrl(documentId: Id<"documents">) {
    const response = await uploadUrl({ documentId });
    return response;
  }

  const uploadUrl = useAction(api.storage.createUploadUrl);

  async function startConversation() {
    if (!activeDocument || activeDocument.status !== "ready") return;
    const id = await createConversation({ documentId: activeDocument._id });
    setConversationId(id);
    track("conversation_started");
  }

  async function submitQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!conversationId || !message.trim() || sending) return;
    const question = message.trim();
    setMessage("");
    setSending(true);
    track("question_sent", { question_length: question.length });
    try {
      await ask({ conversationId, question });
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "Could not send that question.");
      setMessage(question);
    } finally {
      setSending(false);
    }
  }

  async function confirmDeleteDocument() {
    if (!documentToDelete || deletingDocument) return;
    setDeletingDocument(true);
    setDeleteDocumentError("");
    try {
      await removeDocument({ documentId: documentToDelete.id });
      setActiveDocumentId(null);
      setConversationId(null);
      setDocumentToDelete(null);
      setNotice("The PDF and its conversation history were deleted.");
    } catch (error) {
      setDeleteDocumentError(error instanceof Error ? error.message : "The PDF could not be deleted.");
    } finally {
      setDeletingDocument(false);
    }
  }

  const currentUser = useQuery(api.auth.getCurrentUser, {});

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <BrandMark />
        <div className="sidebar-heading"><span>YOUR NOTEBOOKS</span><button className="icon-button" onClick={openCreateNotebook} title="Create notebook">+</button></div>
        <nav className="notebook-list" aria-label="Notebooks">
          {notebooks?.map((notebook) => <button key={notebook._id} className={`notebook-item ${activeNotebook?._id === notebook._id ? "selected" : ""}`} onClick={() => { setActiveNotebookId(notebook._id); setActiveDocumentId(null); setConversationId(null); }}><span className="small-file">▤</span><span className="truncate">{notebook.title}</span></button>)}
        </nav>
        <div className="sidebar-bottom">
          <button className="provider-card" onClick={() => setSettingsOpen(true)}>
            <span className="status-dot" />
            <span><strong>Cloud workspace</strong><small>{import.meta.env.VITE_POSTHOG_KEY ? "Gemini · PostHog" : "Gemini · analytics off"}</small></span>
            <span aria-hidden="true">⚙</span>
          </button>
          <div className="account-row"><span className="truncate">{currentUser?.email || "Signed in"}</span><button className="text-button" onClick={() => authClient.signOut()}>Sign out</button></div>
        </div>
      </aside>

      <main className="main-panel">
        <header className="topbar">
          <div className="breadcrumb"><span>Workspace</span><span className="crumb-sep">/</span><strong title={activeDocument?.filename ?? activeNotebook?.title ?? "Choose a notebook"}>{activeDocument?.filename ?? activeNotebook?.title ?? "Choose a notebook"}</strong></div>
          <div className="topbar-actions">
            <button className="button button-soft" disabled={!activeNotebook} onClick={() => fileInput.current?.click()}>↑ <span>Add sources</span></button>
            <button className="button button-primary" disabled={!activeDocument || activeDocument.status !== "ready"} onClick={startConversation}>New conversation</button>
          </div>
        </header>

        {!activeNotebook ? (
          <section className="welcome-view"><div className="welcome-content"><p className="eyebrow">YOUR RESEARCH, GROUNDED</p><h1>A clearer way to<br /><span>work with your sources.</span></h1><p className="welcome-copy">Create a notebook, add a PDF, and start a conversation just for that document. Answers include page references you can check.</p><button className="button button-primary button-large" onClick={openCreateNotebook}>Create your first notebook <span>→</span></button></div><div className="welcome-art"><div className="paper-card"><b>research-notes.pdf</b><hr />Every claim has a source.</div></div></section>
        ) : (
          <section className="workspace-view">
            <aside className="library-panel">
              <div className="library-header"><div><p className="eyebrow">NOTEBOOK CONTENTS</p><h2>Documents</h2></div><button className="round-button" disabled={uploading} onClick={() => fileInput.current?.click()}>+</button></div>
              <button className="upload-drop" disabled={uploading} onClick={() => fileInput.current?.click()}><span className="upload-icon">↑</span><strong>{uploading ? "Uploading…" : "Add a document"}</strong><span>Choose a PDF up to 50 MB</span></button>
              <input ref={fileInput} type="file" accept="application/pdf,.pdf" multiple hidden onChange={(event) => { void uploadFiles(event.target.files); event.target.value = ""; }} />
              <div className="source-count-row"><span>{documents?.length ?? 0} {documents?.length === 1 ? "document" : "documents"}</span><span className="source-type">PDF</span></div>
              <div className="source-list">
                {documents?.map((document) => <div key={document._id} className={`source-card ${activeDocument?._id === document._id ? "source-selected" : ""}`}>
                  <button className="source-main" onClick={() => { setActiveDocumentId(document._id); setConversationId(null); }}><span className="pdf-badge">PDF</span><span className="source-info"><strong className="truncate" title={document.filename}>{document.filename}</strong><small>{document.pageCount ? `${document.pageCount} pages · ` : ""}{document.status === "ready" ? "ready" : document.status}</small></span></button>
                  <button className="delete-button" title="Delete PDF" aria-label={`Delete ${document.filename}`} onClick={() => { setDeleteDocumentError(""); setDocumentToDelete({ id: document._id, filename: document.filename }); }}>×</button>
                  {document.status === "failed" && <p className="source-error">{document.ingestionError || "Indexing failed."}</p>}
                </div>)}
              </div>
              {notice && <p className="notice" role="status">{notice}</p>}
              <p className="privacy-note">PDFs are stored in your cloud account and sent to Google Gemini for indexing and answers.</p>
            </aside>

            <section className="chat-panel">
              <div className="chat-header">
                <div className="chat-heading"><p className="eyebrow">ASK THIS DOCUMENT</p><h2 title={activeDocument?.filename ?? "Choose a document"}>{activeDocument?.filename ?? "Choose a document"}</h2></div>
                <div className="chat-controls">
                  <label className="visually-hidden" htmlFor="conversation-history">Chat history</label>
                  <select id="conversation-history" value={conversationId ?? ""} disabled={!history.length} onChange={(event) => setConversationId(event.target.value as Id<"conversations">)}>
                    {!history.length && <option value="">Chat history</option>}
                    {history.map((item) => <option key={item._id} value={item._id}>{item.title}</option>)}
                  </select>
                  <button className="icon-button" title="Start a new conversation" disabled={!activeDocument || activeDocument.status !== "ready"} onClick={startConversation}>＋</button>
                </div>
              </div>
              <div className="chat-messages">
                {!activeDocument && <div className="chat-empty"><h3>Choose a PDF to begin</h3><p>Each document keeps its own conversation history.</p></div>}
                {activeDocument && activeDocument.status !== "ready" && <div className="chat-empty"><h3>{activeDocument.status === "failed" ? "This PDF could not be indexed" : "Preparing your document…"}</h3><p>{activeDocument.ingestionError || "We are extracting pages and building the search index."}</p></div>}
                {activeDocument?.status === "ready" && !conversationId && <div className="chat-empty"><h3>Start a conversation</h3><p>Ask about this document and check the pages behind each answer.</p><button className="button button-primary" onClick={startConversation}>New conversation</button></div>}
                {conversationData?.messages.map((item) => <article key={item._id} className={`message-row ${item.role}`}>
                  {item.role === "user" ? <div className="user-bubble">{item.content}</div> : <div className={`assistant-message ${item.failed ? "failed-message" : ""}`}><div className="grounded-label">✳ <span>{item.failed ? "NOTICE" : "GROUNDED ANSWER"}</span></div><div className="answer-text">{renderAnswer(item.content, item.sources ?? [], setSourceToOpen)}</div>{Boolean(item.sources?.length) && <div className="source-chips">{item.sources?.map((source) => <button key={`${source.marker}-${source.chunkId}`} onClick={() => setSourceToOpen(source)}>[{source.marker}] Page {source.pageNumber}</button>)}</div>}</div>}
                </article>)}
                {sending && <div className="assistant-message typing">Finding the best passages…</div>}
                <div ref={messagesEnd} />
              </div>
              <form className="composer" onSubmit={(event) => void submitQuestion(event)}>
                <textarea
                  value={message}
                  onChange={(event) => setMessage(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                      event.preventDefault();
                      event.currentTarget.form?.requestSubmit();
                    }
                  }}
                  placeholder={activeDocument ? "Ask a question about this document…" : "Choose a document first…"}
                  disabled={!conversationId || sending}
                  maxLength={5000}
                  rows={2}
                />
                <div className="composer-footer"><span>Answers are grounded in this document</span><button className="send-button" disabled={!conversationId || !message.trim() || sending} aria-label="Send question">↑</button></div>
              </form>
              <p className="disclaimer">AI answers can be inaccurate. Open a citation to check the original page.</p>
            </section>
          </section>
        )}
      </main>

      {createNotebookOpen && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !creatingNotebook) setCreateNotebookOpen(false); }}><section className="app-dialog" role="dialog" aria-modal="true" aria-labelledby="create-notebook-title" aria-describedby="create-notebook-description"><button className="modal-close" type="button" onClick={() => setCreateNotebookOpen(false)} disabled={creatingNotebook} aria-label="Close">×</button><p className="eyebrow">NEW NOTEBOOK</p><h2 id="create-notebook-title">Name your notebook</h2><p className="muted dialog-description" id="create-notebook-description">Give this workspace a name that helps you find it later.</p><form className="dialog-form" onSubmit={(event) => void submitCreateNotebook(event)}><label htmlFor="notebook-name">Notebook name</label><input id="notebook-name" autoFocus value={notebookName} onChange={(event) => setNotebookName(event.target.value)} placeholder="For example, Research notes" maxLength={100} required />{createNotebookError && <p className="form-error" role="alert">{createNotebookError}</p>}<div className="dialog-actions"><button className="button button-soft" type="button" onClick={() => setCreateNotebookOpen(false)} disabled={creatingNotebook}>Cancel</button><button className="button button-primary" type="submit" disabled={creatingNotebook || !notebookName.trim()}>{creatingNotebook ? "Creating…" : "Create notebook"}</button></div></form></section></div>}
      {documentToDelete && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !deletingDocument) setDocumentToDelete(null); }}><section className="app-dialog" role="alertdialog" aria-modal="true" aria-labelledby="delete-document-title" aria-describedby="delete-document-description"><button className="modal-close" type="button" onClick={() => setDocumentToDelete(null)} disabled={deletingDocument} aria-label="Close">×</button><p className="eyebrow">DELETE DOCUMENT</p><h2 id="delete-document-title">Delete this PDF?</h2><p className="muted dialog-description" id="delete-document-description"><strong>{documentToDelete.filename}</strong> and its conversations, citations, and indexed content will be permanently removed.</p>{deleteDocumentError && <p className="form-error" role="alert">{deleteDocumentError}</p>}<div className="dialog-actions"><button className="button button-soft" type="button" onClick={() => setDocumentToDelete(null)} disabled={deletingDocument}>Cancel</button><button className="button button-danger" type="button" onClick={() => void confirmDeleteDocument()} disabled={deletingDocument}>{deletingDocument ? "Deleting…" : "Delete PDF"}</button></div></section></div>}
      {settingsOpen && <SettingsModal close={() => setSettingsOpen(false)} />}
      {sourceToOpen && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setSourceToOpen(null); }}><section className="source-modal" role="dialog" aria-modal="true" aria-labelledby="source-modal-title"><button className="modal-close" onClick={() => setSourceToOpen(null)} aria-label="Close">×</button><p className="eyebrow">SOURCE PASSAGE</p><h2 id="source-modal-title">{activeDocument?.filename} · page {sourceToOpen.pageNumber}</h2><blockquote>{sourceToOpen.excerpt}</blockquote><hr /><h3>Page text</h3><div className="page-text">{page?.text || "Loading page text…"}</div><button className="button button-soft" onClick={() => { track("citation_opened", { page_number: sourceToOpen.pageNumber }); setSourceToOpen(null); }}>Done</button></section></div>}
    </div>
  );
}

function renderAnswer(content: string, sources: Source[], open: (source: Source) => void) {
  const byMarker = new Map(sources.map((source) => [source.marker, source]));
  let inlineKey = 0;
  const renderInline = (text: string): ReactNode[] => text.split(/(\[\d+\]|\*\*[^*]+\*\*|__[^_]+__|`[^`]+`|\*(?!\s)[^*\n]+?\*|_(?!\s)[^_\n]+?_)/g).flatMap((part) => {
    const key = inlineKey++;
    const citation = /^\[(\d+)\]$/.exec(part);
    if (citation) {
      const source = byMarker.get(Number(citation[1]));
      return [source ? <button key={key} className="inline-citation" onClick={() => open(source)}>{part}</button> : <span key={key}>{part}</span>];
    }
    if ((part.startsWith("**") && part.endsWith("**")) || (part.startsWith("__") && part.endsWith("__"))) {
      return [<strong key={key}>{renderInline(part.slice(2, -2))}</strong>];
    }
    if (part.startsWith("`") && part.endsWith("`")) return [<code className="answer-inline-code" key={key}>{part.slice(1, -1)}</code>];
    if ((part.startsWith("*") && part.endsWith("*")) || (part.startsWith("_") && part.endsWith("_"))) {
      return [<em key={key}>{renderInline(part.slice(1, -1))}</em>];
    }
    return part.split("\n").flatMap((line, lineIndex) => lineIndex === 0
      ? [<span key={`${key}-${lineIndex}`}>{line}</span>]
      : [<br key={`${key}-break-${lineIndex}`} />, <span key={`${key}-${lineIndex}`}>{line}</span>]);
  });

  const lines = content.replace(/\r\n?/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let index = 0;
  const bulletPattern = /^\s*[-*+]\s+(.*)$/;
  const orderedPattern = /^\s*\d+[.)]\s+(.*)$/;
  const headingPattern = /^(#{1,6})\s+(.*)$/;
  const isBlockStart = (line: string) => headingPattern.test(line.trim()) || bulletPattern.test(line) || orderedPattern.test(line) || /^\s*```/.test(line) || /^\s*>\s?/.test(line) || /^\s*(---|\*\*\*|___)\s*$/.test(line);

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) { index += 1; continue; }

    const heading = headingPattern.exec(line.trim());
    if (heading) {
      const level = Math.min(Number(heading[1].length) + 1, 6);
      const Heading = `h${level}` as "h2" | "h3" | "h4" | "h5" | "h6";
      blocks.push(<Heading className="answer-heading" key={`heading-${index}`}>{renderInline(heading[2])}</Heading>);
      index += 1;
      continue;
    }

    if (/^\s*(---|\*\*\*|___)\s*$/.test(line)) {
      blocks.push(<hr className="answer-divider" key={`divider-${index}`} />);
      index += 1;
      continue;
    }

    if (/^\s*```/.test(line)) {
      index += 1;
      const codeLines: string[] = [];
      while (index < lines.length && !/^\s*```/.test(lines[index])) codeLines.push(lines[index++]);
      if (index < lines.length) index += 1;
      blocks.push(<pre className="answer-code" key={`code-${index}`}><code>{codeLines.join("\n")}</code></pre>);
      continue;
    }

    const bullet = bulletPattern.exec(line);
    const ordered = orderedPattern.exec(line);
    if (bullet || ordered) {
      const isOrdered = Boolean(ordered);
      const items: ReactNode[] = [];
      while (index < lines.length) {
        const match = (isOrdered ? orderedPattern : bulletPattern).exec(lines[index]);
        if (!match) break;
        items.push(<li key={`item-${index}`}>{renderInline(match[1])}</li>);
        index += 1;
      }
      blocks.push(isOrdered ? <ol className="answer-list" key={`list-${index}`}>{items}</ol> : <ul className="answer-list" key={`list-${index}`}>{items}</ul>);
      continue;
    }

    if (/^\s*>\s?/.test(line)) {
      const quoteLines: string[] = [];
      while (index < lines.length && /^\s*>\s?/.test(lines[index])) quoteLines.push(lines[index++].replace(/^\s*>\s?/, ""));
      blocks.push(<blockquote className="answer-quote" key={`quote-${index}`}>{renderInline(quoteLines.join("\n"))}</blockquote>);
      continue;
    }

    const paragraph: string[] = [];
    while (index < lines.length && lines[index].trim() && !(paragraph.length && isBlockStart(lines[index].trim()))) {
      if (!paragraph.length && isBlockStart(lines[index].trim())) break;
      paragraph.push(lines[index++]);
    }
    if (paragraph.length) blocks.push(<p className="answer-paragraph" key={`paragraph-${index}`}>{renderInline(paragraph.join("\n"))}</p>);
    else index += 1;
  }

  return blocks;
}

function SettingsModal({ close }: { close: () => void }) {
  const status = useQuery(api.settings.status, {});
  const save = useAction(api.geminiKeyActions.saveGeminiKey);
  const clear = useAction(api.geminiKeyActions.clearGeminiKey);
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");

  async function saveKey(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setNotice("");
    try {
      await save({ encryptedApiKey: await encryptGeminiKey(apiKey) });
      setApiKey("");
      setNotice("Gemini key checked and saved securely.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "The Gemini key could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  async function clearKey() {
    setBusy(true);
    try {
      await clear({});
      setNotice("Gemini key removed.");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "The Gemini key could not be removed.");
    } finally {
      setBusy(false);
    }
  }

  return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) close(); }}><section className="settings-modal" role="dialog" aria-modal="true" aria-labelledby="settings-title"><button className="modal-close" onClick={close} aria-label="Close">×</button><p className="eyebrow">ACCOUNT SETTINGS</p><h2 id="settings-title">Gemini API key</h2><p className="muted">Your key is checked and encrypted before storage. It is used by this account for document embeddings and answers.</p><form onSubmit={(event) => void saveKey(event)} className="stack-form"><label>Google AI Studio key<input type="password" autoComplete="new-password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder={status?.geminiConfigured ? "Replace your saved key" : "Paste your Gemini API key"} minLength={20} required /></label><button className="button button-primary" disabled={busy}>{busy ? "Checking…" : "Check and save key"}</button></form><p className="key-status">{status?.geminiConfigured ? "A Gemini key is saved for your account." : "No Gemini key has been saved yet."}</p>{status?.geminiConfigured && <button className="text-button danger-link" disabled={busy} onClick={() => void clearKey()}>Remove saved key</button>}{notice && <p className="notice" role="status">{notice}</p>}<p className="privacy-note">Google receives document text and questions when generating embeddings and answers. PostHog receives only basic product events; it does not receive file names, PDF text, or prompts.</p></section></div>;
}
