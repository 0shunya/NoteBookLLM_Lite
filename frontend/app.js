const state = {
  notebooks: [],
  activeNotebook: null,
  documents: [],
  activeDocument: null,
  conversationId: null,
  conversations: [],
  busy: false,
  pollHandle: null,
  toastHandle: null,
};

const $ = (selector) => document.querySelector(selector);
const notebookList = $("#notebook-list");
const notebookDialog = $("#notebook-dialog");
const citationDialog = $("#citation-dialog");

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("visible");
  clearTimeout(state.toastHandle);
  state.toastHandle = setTimeout(() => toast.classList.remove("visible"), 3500);
}

async function request(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch { /* The response may not contain JSON. */ }
    throw new Error(detail);
  }
  return response.status === 204 ? null : response.json();
}

function setWorkspaceVisible(visible) {
  $("#welcome").classList.toggle("hidden", visible);
  $("#workspace").classList.toggle("hidden", !visible);
  $("#upload-top").disabled = !visible;
  $("#new-chat").disabled = !visible || !state.activeDocument || state.busy;
  $("#conversation-menu").disabled = !visible || !state.activeDocument || state.busy;
}

function renderNotebooks() {
  notebookList.replaceChildren();
  for (const notebook of state.notebooks) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `notebook-item${notebook.id === state.activeNotebook?.id ? " active" : ""}`;
    button.innerHTML = `<span class="notebook-glyph" aria-hidden="true"><svg viewBox="0 0 20 20" fill="none"><path d="M5.25 3.5h6.4l3.1 3.1v9.9H5.25A1.75 1.75 0 0 1 3.5 14.75v-9.5A1.75 1.75 0 0 1 5.25 3.5Z" stroke="currentColor" stroke-width="1.3"/><path d="M11.5 3.75v3h3M6.5 10h6M6.5 12.6h4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg></span><span class="notebook-name"></span><span class="notebook-count">${notebook.document_count ?? 0}</span>`;
    button.querySelector(".notebook-name").textContent = notebook.title;
    button.addEventListener("click", () => selectNotebook(notebook.id));
    notebookList.append(button);
  }
}

function renderDocuments() {
  const container = $("#source-list");
  container.replaceChildren();
  const count = state.documents.length;
  $("#source-count").textContent = `${count} ${count === 1 ? "document" : "documents"}`;

  for (const sourceDocument of state.documents) {
    const row = document.createElement("div");
    row.className = `source-item${sourceDocument.id === state.activeDocument?.id ? " active" : ""}`;
    const select = document.createElement("button");
    select.type = "button";
    select.className = "source-select";
    select.disabled = state.busy;
    select.setAttribute("aria-label", `Open ${sourceDocument.filename} conversation`);
    const icon = document.createElement("span");
    icon.className = "file-icon";
    icon.textContent = "PDF";
    const meta = document.createElement("div");
    meta.className = "source-meta";
    const name = document.createElement("strong");
    name.textContent = sourceDocument.filename;
    name.title = sourceDocument.filename;
    const detail = document.createElement("span");
    if (sourceDocument.status === "indexed") detail.textContent = `${sourceDocument.page_count} pages · ready`;
    else if (sourceDocument.status === "failed") detail.textContent = sourceDocument.ingestion_error || "Indexing failed";
    else detail.textContent = sourceDocument.status === "queued" ? "Waiting to index…" : "Reading and indexing…";
    const badge = document.createElement("span");
    badge.className = `source-state ${sourceDocument.status}`;
    badge.textContent = sourceDocument.status === "indexed" ? "ready" : sourceDocument.status;
    meta.append(name, detail);
    select.append(icon, meta, badge);
    select.addEventListener("click", () => selectDocument(sourceDocument.id));
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "source-delete";
    remove.textContent = "×";
    remove.title = ["queued", "processing"].includes(sourceDocument.status)
      ? "Wait until indexing finishes before deleting"
      : `Delete ${sourceDocument.filename} and its chat history`;
    remove.setAttribute("aria-label", `Delete ${sourceDocument.filename}`);
    remove.disabled = state.busy || ["queued", "processing"].includes(sourceDocument.status);
    remove.addEventListener("click", () => deleteDocument(sourceDocument));
    row.append(select, remove);
    container.append(row);
  }

  const ready = state.activeDocument?.status === "indexed";
  $("#question-input").disabled = !ready || state.busy;
  $("#send-button").disabled = !ready || state.busy;
  $("#upload-drop").setAttribute("aria-label", count ? "Add more PDF sources" : "Upload PDF documents");
  if (!state.activeDocument) $("#empty-hint").textContent = "Choose a document to start a private conversation about it.";
  else if (!ready) $("#empty-hint").textContent = "This PDF is being indexed. Questions will be ready as soon as indexing finishes.";
  else $("#empty-hint").textContent = "Ask about this document. Its chat history stays separate from your other PDFs.";
}

function sourceForCitation(source, allSources) {
  const fromSearch = allSources?.find((item) => item.id === source.marker);
  return fromSearch || {
    id: source.marker,
    chunk_id: source.chunk_id,
    document_id: source.document_id,
    filename: source.filename || "Removed source",
    page_number: source.page_number,
    page_start: source.page_number,
    page_end: source.page_number,
    text: source.quote,
  };
}

function appendAnswerText(target, answer, sources) {
  const citationById = new Map(sources.map((source) => [Number(source.id), source]));
  const pattern = /\[(\d+)\]/g;
  let start = 0;
  for (const match of answer.matchAll(pattern)) {
    target.append(document.createTextNode(answer.slice(start, match.index)));
    const source = citationById.get(Number(match[1]));
    if (source) {
      const marker = document.createElement("button");
      marker.type = "button";
      marker.className = "inline-citation";
      marker.textContent = match[0];
      marker.title = `${source.filename}, page ${source.page_number}`;
      marker.dataset.sourceId = String(source.id);
      marker.addEventListener("click", () => openCitation(source));
      target.append(marker);
    } else {
      target.append(document.createTextNode(match[0]));
    }
    start = match.index + match[0].length;
  }
  target.append(document.createTextNode(answer.slice(start)));
}

function renderMessage(message, sources = []) {
  const container = $("#chat-messages");
  $("#chat-empty").classList.add("hidden");
  const row = document.createElement("article");
  row.className = `message ${message.role}`;
  if (message.role === "user") {
    const bubble = document.createElement("div");
    bubble.className = "message-bubble";
    bubble.textContent = message.content;
    row.append(bubble);
  } else {
    const label = document.createElement("div");
    label.className = "assistant-label";
    label.innerHTML = "<span aria-hidden=\"true\">✳</span> GROUNDED ANSWER";
    const answer = document.createElement("div");
    answer.className = "assistant-answer";
    appendAnswerText(answer, message.content, sources);
    row.append(label, answer);

    const referenced = new Set(Array.from(message.content.matchAll(/\[(\d+)\]/g), (item) => Number(item[1])));
    const visibleSources = sources.filter((source) => referenced.has(Number(source.id)));
    if (visibleSources.length) {
      const chips = document.createElement("div");
      chips.className = "sources-used";
      for (const source of visibleSources) {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "source-chip";
        chip.innerHTML = `<b>[${Number(source.id)}]</b><span></span><span>p. ${source.page_number}</span>`;
        chip.querySelector("span").textContent = source.filename;
        chip.addEventListener("click", () => openCitation(source));
        chips.append(chip);
      }
      row.append(chips);
    }
    if (message.trace_id) {
      const trace = document.createElement("div");
      trace.className = "answer-trace";
      const link = document.createElement("a");
      link.href = `/traces/${encodeURIComponent(message.trace_id)}`;
      link.target = "_blank";
      link.rel = "noreferrer";
      link.textContent = "View model trace ↗";
      trace.append(link);
      row.append(trace);
    }
  }
  container.append(row);
  container.scrollTop = container.scrollHeight;
  return row;
}

function openCitation(source) {
  $("#citation-title").textContent = source.filename || "Source document";
  $("#citation-page").textContent = `Page ${source.page_number} · ${source.document_id || "source"}`;
  $("#citation-quote").textContent = source.text || source.quote || "No extracted text is available for this page.";
  const pageLink = $("#citation-open-page");
  pageLink.href = `/documents/${encodeURIComponent(source.document_id)}/pages/${source.page_number}`;
  pageLink.dataset.documentId = source.document_id || "";
  pageLink.dataset.page = String(source.page_number);
  if (!citationDialog.open) citationDialog.showModal();
}

async function loadNotebookList() {
  state.notebooks = await request("/notebooks");
  renderNotebooks();
}

async function loadDocuments() {
  if (!state.activeNotebook) return;
  state.documents = await request(`/notebooks/${encodeURIComponent(state.activeNotebook.id)}/documents`);
  if (state.activeDocument) {
    state.activeDocument = state.documents.find((item) => item.id === state.activeDocument.id) || null;
  }
  renderDocuments();
  const notebook = state.notebooks.find((item) => item.id === state.activeNotebook.id);
  if (notebook) notebook.document_count = state.documents.length;
  renderNotebooks();
  if (state.documents.some((item) => ["queued", "processing"].includes(item.status))) {
    if (!state.pollHandle) {
      state.pollHandle = setInterval(() => loadDocuments().catch(() => {}), 1800);
    }
  } else if (state.pollHandle) {
    clearInterval(state.pollHandle);
    state.pollHandle = null;
  }
}

async function loadConversation(conversationId) {
  const data = await request(`/conversations/${encodeURIComponent(conversationId)}`);
  state.conversationId = data.conversation_id;
  $("#chat-title").textContent = data.title;
  $("#conversation-history").value = data.conversation_id;
  $("#chat-messages").replaceChildren();
  for (const message of data.messages) {
    const sources = message.citations.map((citation) => sourceForCitation(citation, []));
    renderMessage(message, sources);
  }
  $("#chat-empty").classList.toggle("hidden", data.messages.length > 0);
}

async function createConversation() {
  if (!state.activeNotebook || !state.activeDocument) return;
  const data = await request("/conversations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: "New conversation", document_id: state.activeDocument.id }),
  });
  state.conversationId = data.conversation_id;
  $("#chat-title").textContent = data.title;
  $("#chat-messages").replaceChildren();
  $("#chat-empty").classList.remove("hidden");
  state.conversations.unshift({
    conversation_id: data.conversation_id,
    title: data.title,
    updated_at: data.created_at,
  });
  renderConversationHistory();
}

function renderConversationHistory() {
  const select = $("#conversation-history");
  select.replaceChildren();
  if (!state.conversations.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No chat history";
    select.append(option);
    select.disabled = true;
    return;
  }
  for (const conversation of state.conversations) {
    const option = document.createElement("option");
    option.value = conversation.conversation_id;
    option.textContent = conversation.title;
    select.append(option);
  }
  select.disabled = !state.activeDocument || state.busy;
  if (state.conversationId) select.value = state.conversationId;
}

async function loadDocumentConversations() {
  if (!state.activeDocument) {
    state.conversations = [];
    state.conversationId = null;
    renderConversationHistory();
    $("#chat-title").textContent = "Choose a document";
    $("#chat-messages").replaceChildren();
    $("#chat-empty").classList.remove("hidden");
    setWorkspaceVisible(Boolean(state.activeNotebook));
    return;
  }
  state.conversations = await request(
    `/documents/${encodeURIComponent(state.activeDocument.id)}/conversations`
  );
  state.conversationId = null;
  renderConversationHistory();
  if (state.conversations.length) {
    await loadConversation(state.conversations[0].conversation_id);
  } else {
    await createConversation();
  }
}

async function selectDocument(documentId) {
  state.activeDocument = state.documents.find((item) => item.id === documentId) || null;
  $("#active-title").textContent = state.activeDocument?.filename || state.activeNotebook?.title || "Choose a document";
  setWorkspaceVisible(Boolean(state.activeNotebook));
  renderDocuments();
  try {
    await loadDocumentConversations();
  } catch (error) {
    showToast(error.message);
  }
}

async function deleteDocument(sourceDocument) {
  if (["queued", "processing"].includes(sourceDocument.status)) return;
  const confirmed = window.confirm(
    `Delete “${sourceDocument.filename}” and its chat history? This cannot be undone.`
  );
  if (!confirmed) return;
  try {
    await request(`/documents/${encodeURIComponent(sourceDocument.id)}`, { method: "DELETE" });
    const wasActive = state.activeDocument?.id === sourceDocument.id;
    if (wasActive) state.activeDocument = null;
    await loadDocuments();
    showToast(`${sourceDocument.filename} and its chat history were deleted.`);
    if (wasActive) {
      if (state.documents.length) await selectDocument(state.documents[0].id);
      else await loadDocumentConversations();
    }
  } catch (error) {
    showToast(`Could not delete ${sourceDocument.filename}: ${error.message}`);
  }
}

async function selectNotebook(notebookId) {
  try {
    const selected = state.notebooks.find((item) => item.id === notebookId);
    if (!selected) return;
    state.activeNotebook = selected;
    $("#active-title").textContent = selected.title;
    setWorkspaceVisible(true);
    renderNotebooks();
    $("#chat-messages").replaceChildren();
    $("#chat-empty").classList.remove("hidden");
    state.activeDocument = null;
    state.conversations = [];
    state.conversationId = null;
    state.documents = [];
    setWorkspaceVisible(true);
    await loadDocuments();
    $("#active-title").textContent = selected.title;
    if (state.documents.length) await selectDocument(state.documents[0].id);
    else await loadDocumentConversations();
  } catch (error) {
    showToast(error.message);
  }
}

function openNotebookDialog() {
  $("#notebook-title").value = "";
  notebookDialog.showModal();
  setTimeout(() => $("#notebook-title").focus(), 20);
}

async function createNotebook(event) {
  event.preventDefault();
  const title = $("#notebook-title").value.trim();
  if (!title) return;
  const submit = event.currentTarget.querySelector("button[type=submit]");
  submit.disabled = true;
  try {
    const notebook = await request("/notebooks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
    notebookDialog.close();
    await loadNotebookList();
    await selectNotebook(notebook.id);
    showToast("Notebook created. Add a PDF source to get started.");
  } catch (error) {
    showToast(error.message);
  } finally {
    submit.disabled = false;
  }
}

async function uploadFiles(files) {
  if (!state.activeNotebook || !files.length) return;
  const pdfs = [...files].filter((file) => file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf"));
  if (!pdfs.length) {
    showToast("Choose one or more PDF files.");
    return;
  }
  for (const file of pdfs) {
    const form = new FormData();
    form.append("file", file);
    try {
      const uploaded = await request(`/notebooks/${encodeURIComponent(state.activeNotebook.id)}/documents`, {
        method: "POST",
        body: form,
      });
      showToast(`${file.name} added. Indexing has started.`);
      await loadDocuments();
      if (state.documents.some((item) => item.id === uploaded.document_id)) {
        await selectDocument(uploaded.document_id);
      }
    } catch (error) {
      showToast(`${file.name}: ${error.message}`);
    }
  }
}

async function sendQuestion(event) {
  event.preventDefault();
  const input = $("#question-input");
  const question = input.value.trim();
  if (!question || state.busy || !state.conversationId) return;
  state.busy = true;
  setWorkspaceVisible(true);
  renderDocuments();
  $("#conversation-history").disabled = true;
  input.value = "";
  input.style.height = "auto";
  $("#send-button").disabled = true;
  $("#chat-empty").classList.add("hidden");
  renderMessage({ role: "user", content: question });
  const thinking = document.createElement("article");
  thinking.className = "message assistant thinking-message";
  thinking.innerHTML = "<div class=\"assistant-label\"><span aria-hidden=\"true\">✳</span> SEARCHING THIS DOCUMENT</div><div class=\"assistant-answer\">Reading your document…</div>";
  $("#chat-messages").append(thinking);
  try {
    const result = await request(`/conversations/${encodeURIComponent(state.conversationId)}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: question }),
    });
    thinking.remove();
    renderMessage({
      role: "assistant",
      content: result.answer,
      trace_id: result.trace_id,
    }, result.sources || []);
    if (result.status === "failure") showToast("The answer did not pass citation checks. See the trace for attempt details.");
    state.conversations = await request(
      `/documents/${encodeURIComponent(state.activeDocument.id)}/conversations`
    );
    renderConversationHistory();
    $("#conversation-history").value = state.conversationId;
    const activeConversation = state.conversations.find((item) => item.conversation_id === state.conversationId);
    if (activeConversation) $("#chat-title").textContent = activeConversation.title;
  } catch (error) {
    thinking.remove();
    renderMessage({ role: "assistant", content: `I could not answer this question. ${error.message}` });
  } finally {
    state.busy = false;
    renderDocuments();
    renderConversationHistory();
  }
}

function setupEvents() {
  $("#new-notebook").addEventListener("click", openNotebookDialog);
  $("#create-first").addEventListener("click", openNotebookDialog);
  $("#notebook-form").addEventListener("submit", createNotebook);
  $("#cancel-notebook").addEventListener("click", () => notebookDialog.close());
  $(".dialog-close").addEventListener("click", () => notebookDialog.close());
  $("#close-citation").addEventListener("click", () => citationDialog.close());
  $("#new-chat").addEventListener("click", createConversation);
  $("#conversation-menu").addEventListener("click", createConversation);
  $("#conversation-history").addEventListener("change", (event) => {
    if (event.currentTarget.value) loadConversation(event.currentTarget.value).catch((error) => showToast(error.message));
  });
  $("#upload-top").addEventListener("click", () => $("#file-input").click());
  $("#upload-library").addEventListener("click", () => $("#file-input").click());
  $("#upload-drop").addEventListener("click", () => $("#file-input").click());
  $("#upload-drop").addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") { event.preventDefault(); $("#file-input").click(); }
  });
  $("#file-input").addEventListener("change", (event) => uploadFiles(event.target.files).finally(() => { event.target.value = ""; }));
  $("#upload-drop").addEventListener("dragover", (event) => { event.preventDefault(); event.currentTarget.classList.add("drag-over"); });
  $("#upload-drop").addEventListener("dragleave", (event) => event.currentTarget.classList.remove("drag-over"));
  $("#upload-drop").addEventListener("drop", (event) => {
    event.preventDefault();
    event.currentTarget.classList.remove("drag-over");
    uploadFiles(event.dataTransfer.files);
  });
  $("#message-form").addEventListener("submit", sendQuestion);
  $("#question-input").addEventListener("input", (event) => {
    const area = event.currentTarget;
    area.style.height = "auto";
    area.style.height = `${Math.min(area.scrollHeight, 140)}px`;
  });
  $("#question-input").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); $("#message-form").requestSubmit(); }
  });
  document.querySelectorAll(".suggestion").forEach((button) => button.addEventListener("click", () => {
    if (state.activeDocument?.status !== "indexed") {
      showToast("Add and index a PDF before asking a question.");
      return;
    }
    $("#question-input").value = button.dataset.question;
    $("#message-form").requestSubmit();
  }));
  $("#citation-open-page").addEventListener("click", async (event) => {
    event.preventDefault();
    const link = event.currentTarget;
    try {
      const page = await request(`/documents/${encodeURIComponent(link.dataset.documentId)}/pages/${link.dataset.page}`);
      $("#citation-quote").textContent = page.text || "No readable text was extracted from this page.";
      $("#citation-page").textContent = `Page ${page.page_number} of ${page.page_count}`;
    } catch (error) { showToast(error.message); }
  });
}

async function initialize() {
  setupEvents();
  try {
    const health = await request("/healthz");
    $("#model-label").textContent = `${health.model_provider} · ${health.generation_model} · ${health.embedding_model}`;
    if (!health.model_ready) showToast(`Add the ${health.model_provider.toUpperCase()} API key to .env, then restart the API.`);
    else if (health.status !== "ok") showToast(`Local services: database ${health.database}, Ollama ${health.ollama}.`);
  } catch {
    $("#model-label").textContent = "Check local services";
  }
  try {
    await loadNotebookList();
    if (state.notebooks.length) await selectNotebook(state.notebooks[0].id);
  } catch (error) {
    showToast(`Could not load notebooks: ${error.message}`);
  }
}

initialize();
