const api = (path, options = {}) => fetch(`/api${path}`, { headers: { "Content-Type": "application/json" }, ...options }).then(async response => {
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || "The request could not be completed.");
  return body;
});

const $ = selector => document.querySelector(selector);
const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, character => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#039;" }[character]));
const setBusy = (button, busy, label) => { button.disabled = busy; button.textContent = busy ? "Working…" : label; };
const showError = (target, error) => { target.hidden = false; target.innerHTML = `<div class="empty-state"><span class="empty-icon">!</span><h3>Something went wrong</h3><p>${escapeHtml(error.message)}</p></div>`; };

document.querySelectorAll(".tab").forEach(tab => tab.addEventListener("click", () => {
  document.querySelectorAll(".tab").forEach(item => item.classList.toggle("active", item === tab));
  document.querySelectorAll(".view").forEach(view => { const active = view.id === `view-${tab.dataset.view}`; view.hidden = !active; view.classList.toggle("active", active); });
  if (tab.dataset.view === "documents") loadDocuments();
}));

function citationHtml(citation) {
  const location = [citation.article_number ? `Article ${escapeHtml(citation.article_number)}` : null, citation.page_start ? `p. ${citation.page_start}${citation.page_end && citation.page_end !== citation.page_start ? `–${citation.page_end}` : ""}` : null].filter(Boolean).join(" · ");
  return `<div class="citation"><span class="tag">${escapeHtml(citation.document_number)}</span><span>${location || "Source passage"}</span>${citation.source_url ? `<a href="${escapeHtml(citation.source_url)}" target="_blank" rel="noreferrer">Official source ↗</a>` : ""}</div>`;
}

$("#search-form").addEventListener("submit", async event => {
  event.preventDefault(); const button = event.target.querySelector("button"); const state = $("#search-state"); const results = $("#search-results");
  setBusy(button, true, "Search"); state.hidden = true; results.hidden = false; results.innerHTML = "<div class='empty-state'><p>Searching the indexed corpus…</p></div>";
  try { const params = new URLSearchParams({ q: $("#search-input").value, mode: $("#search-mode").value, limit: $("#search-limit").value }); const hits = await api(`/search?${params}`); results.innerHTML = hits.length ? hits.map(hit => `<article class="result-card"><div class="result-top"><span class="result-number">${escapeHtml(hit.citation.document_number)}</span><span class="score">fused score ${Number(hit.fused_score).toFixed(4)}</span></div><p>${escapeHtml(hit.content)}</p>${citationHtml(hit.citation)}</article>`).join("") : "<div class='empty-state'><h3>No matching passages</h3><p>Try a broader Vietnamese or English query.</p></div>"; } catch (error) { showError(results, error); } finally { setBusy(button, false, "Search"); }
});

$("#ask-form").addEventListener("submit", async event => {
  event.preventDefault(); const button = event.target.querySelector("button"); const state = $("#ask-state"); const result = $("#ask-result");
  setBusy(button, true, "Ask question →"); state.hidden = true; result.hidden = false; result.innerHTML = "<div class='empty-state'><p>Retrieving evidence and preparing a cited response…</p></div>";
  try { const answer = await api("/questions", { method:"POST", body:JSON.stringify({ question: $("#question-input").value }) }); result.innerHTML = `<span class="answer-status">${escapeHtml(answer.status)}</span>${answer.answer ? `<div class="answer-text">${escapeHtml(answer.answer)}</div>` : `<p>${escapeHtml(answer.interpretation || "No answer was produced.")}</p>`}${answer.uncertainties?.length ? `<div class="uncertainties"><strong>Uncertainties</strong><br>${answer.uncertainties.map(escapeHtml).join("<br>")}</div>` : ""}${answer.citations?.length ? `<div class="answer-citations"><p class="eyebrow">Sources</p>${answer.citations.map(citationHtml).join("")}</div>` : ""}`; } catch (error) { showError(result, error); } finally { setBusy(button, false, "Ask question →"); }
});

$("#compare-form").addEventListener("submit", async event => {
  event.preventDefault(); const button = event.target.querySelector("button"); const state = $("#compare-state"); const result = $("#compare-result");
  setBusy(button, true, "Compare versions →"); state.hidden = true; result.hidden = false; result.innerHTML = "<div class='empty-state'><p>Comparing article structure…</p></div>";
  try { const comparison = await api("/comparisons", { method:"POST", body:JSON.stringify({ before_document_number:$("#before-input").value, after_document_number:$("#after-input").value }) }); result.innerHTML = comparison.changes.length ? comparison.changes.map(change => `<article class="change-card ${change.change_type.toLowerCase()}"><div class="change-top"><strong>${escapeHtml(change.key)}</strong><span class="change-type">${escapeHtml(change.change_type)}</span></div><div class="change-content"><div><strong>Before</strong>${escapeHtml(change.before_content || "—")}</div><div><strong>After</strong>${escapeHtml(change.after_content || "—")}</div></div></article>`).join("") : "<div class='empty-state'><h3>No article changes found</h3></div>"; } catch (error) { showError(result, error); } finally { setBusy(button, false, "Compare versions →"); }
});

let documentsLoaded = false;
async function loadDocuments() {
  if (documentsLoaded) return; const state = $("#documents-state"); const list = $("#documents-list"); state.hidden = false; list.hidden = true;
  try { const documents = await api("/documents?limit=100"); $("#document-options").innerHTML = documents.map(document => `<option value="${escapeHtml(document.document_number)}">${escapeHtml(document.title)}</option>`).join(""); list.innerHTML = documents.map(document => `<article class="document-card"><div class="doc-top"><span class="doc-number">${escapeHtml(document.document_number)}</span><span class="tag">${escapeHtml(document.document_type)}</span></div><strong>${escapeHtml(document.title)}</strong><div class="doc-meta"><span>${escapeHtml(document.issuing_agency || "Agency unavailable")}</span></div></article>`).join("") || "<div class='empty-state'><p>No documents indexed yet.</p></div>"; state.hidden = true; list.hidden = false; documentsLoaded = true; } catch (error) { showError(state, error); }
}

$("#refresh-documents").addEventListener("click", () => { documentsLoaded = false; loadDocuments(); });
