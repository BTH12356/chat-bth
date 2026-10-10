"use strict";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const state = {
  view: "chat", projects: [], conversations: [], project: null, conversation: null, messages: [],
  models: [], defaultModel: "", modelsReady: false, busy: false, loading: false, modelSaving: false,
  reading: false, files: [], drafts: new Map(), health: null, providers: [], connecting: false, token: "", revision: 0,
  buildFiles: [], buildFilePath: null, buildFileContent: "", buildBusy: false, buildAssistantBusy: false, buildPreviewUrl: null,
  buildChats: new Map(), buildStorageDisabled: new Set(), buildStorageWarned: false,
  guidedBuild: false, createSpec: null, guidedConversation: null, guidedPayload: null,
  previewSelection: null, previewEditMode: false, previewNode: null, previewAssistantProposal: null, chatGuidedConversation: null,
  buildDiagnostics: [], buildFileRevision: 0,
  chatSearchQuery: "", chatSearchResults: null, chatSearchRevision: 0,
};
const UI_THEME_KEY = "chat-bth-ui-theme";
function applyUiTheme(theme) {
  const selected = ["light", "neon", "macos", "cyberpunk", "synthwave", "blueprint", "dracula", "matrix", "win98", "eink"].includes(theme) ? theme : "windows-xp";
  document.documentElement.dataset.uiTheme = selected;
  localStorage.setItem(UI_THEME_KEY, selected);
  const picker = $("#ui-theme-select");
  if (picker) picker.value = selected;
}
applyUiTheme(localStorage.getItem(UI_THEME_KEY) || "windows-xp");
const el = (tag, className = "", text = "") => {
  const node = document.createElement(tag);
  node.className = className;
  node.textContent = text;
  return node;
};
function icon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS(svg.namespaceURI, "use");
  use.setAttribute("href", "#i-" + name);
  svg.append(use);
  return svg;
}
function button(label, className, handler, iconName) {
  const node = el("button", className);
  node.type = "button";
  if (iconName) node.append(icon(iconName));
  node.append(el("span", "", label));
  if (handler) node.addEventListener("click", handler);
  return node;
}
function iconButton(label, iconName, handler, extraClass = "") {
  const node = button("", "icon-button inline-edit " + extraClass, handler, iconName);
  node.setAttribute("aria-label", label);
  node.title = label;
  return node;
}
let toastTimer;
function toast(message, error = false) {
  $("#toast").textContent = message;
  $("#toast").className = "toast show" + (error ? " error" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $("#toast").classList.remove("show"), 4500);
}
function errorMessage(error) {
  if (error.name === "AbortError") return "การเชื่อมต่อใช้เวลานานเกินไป ข้อความยังอยู่ กรุณาตรวจสอบบทสนทนาก่อนส่งซ้ำ";
  if (error instanceof TypeError) return "ติดต่อเซิร์ฟเวอร์ไม่ได้ ตรวจสอบการเชื่อมต่อแล้วลองใหม่";
  return error.message || "ดำเนินการไม่สำเร็จ กรุณาลองใหม่";
}
function formError(form, text = "") {
  const node = $(".form-error", form);
  node.textContent = text;
  node.hidden = !text;
}
function composerError(text = "") {
  $("#composer-error").textContent = text;
  $("#composer-error").hidden = !text;
}
function banner(text = "", auth = false) {
  $("#connection-banner").hidden = !text;
  $("#connection-message").textContent = text;
  $("#auth-open").hidden = !auth;
}
async function api(path, options = {}) {
  const { timeout = 20000, blob = false, ...settings } = options;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetch(path, {
      ...settings, signal: controller.signal,
      headers: { "Content-Type": "application/json", ...(state.token ? { "x-hermes-token": state.token } : {}), ...settings.headers },
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      const detail = Array.isArray(data.detail)
        ? data.detail.map(item => item.msg).join(" · ")
        : data.detail;
      const oldProviderServer = response.status === 405 && path === "/api/providers";
      const detailText = detail && typeof detail === "object" ? (detail.reason || detail.status || JSON.stringify(detail)) : detail;
      const error = new Error(response.status === 401
        ? "กรุณาใส่รหัสเข้าใช้งานของเซิร์ฟเวอร์"
        : oldProviderServer
          ? "Web server ยังใช้โค้ดเวอร์ชันเก่า กรุณาหยุดแล้วเปิด web_app.py ใหม่"
          : (detailText || "คำขอล้มเหลว (" + response.status + ")"));
      error.status = response.status;
      if (response.status === 401) banner(error.message, true);
      throw error;
    }
    return blob ? response.blob() : response.json();
  } finally { clearTimeout(timer); }
}
const mutation = (method, value) => ({ method, body: JSON.stringify(value) });
const locked = () => state.busy || state.loading || state.modelSaving || state.reading || state.buildBusy || state.buildAssistantBusy;
function guardNavigation() {
  if (!locked()) return false;
  toast("รอให้งานปัจจุบันเสร็จก่อนเปลี่ยนบทสนทนา");
  return true;
}
function formatDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? (value || "") : date.toLocaleDateString("th-TH", { day: "numeric", month: "short" });
}
function fullMessage(message, files) {
  return message.trim() + files.map(file => "\n\n[ไฟล์แนบ: " + file.name + "]\n" + file.content + "\n[/ไฟล์แนบ]").join("");
}
function requestText() { return $("#message").value.trim() || (state.files.length ? "ช่วยวิเคราะห์ไฟล์แนบนี้" : ""); }
function syncComposer() {
  const length = fullMessage(requestText(), state.files).length;
  const modelKnown = $("#model").value === "auto" || state.models.some(model => model.id === $("#model").value);
  const guidedActive = !!state.chatGuidedConversation;
  $("#composer-count").textContent = length.toLocaleString("en-US") + " / 12,000";
  $("#composer-count").style.color = length > 12000 ? "var(--danger)" : "";
  $("#send").disabled = locked() || !requestText() || length > 12000 || !state.conversation || (!guidedActive && (!state.modelsReady || !modelKnown));
  $("#send").setAttribute("aria-label", state.busy ? "กำลังรอคำตอบ" : "ส่งข้อความ");
  $("#composer").setAttribute("aria-busy", String(state.busy || state.reading));
  $("#message").disabled = state.busy || state.loading;
  $("#attach-file").disabled = locked() || guidedActive;
  $("#search").disabled = state.busy || guidedActive;
  $("#model").disabled = locked() || !state.modelsReady || guidedActive;
  $("#new-chat").disabled = locked();
  $("#new-project").disabled = locked();
  $("#rename-chat").disabled = locked() || !state.conversation;
}
function resizeInput() {
  $("#message").style.height = "auto";
  $("#message").style.height = Math.min($("#message").scrollHeight, 180) + "px";
}
function setHeading() {
  const titles = { build: state.project?.name || "เลือกโปรเจกต์เพื่อเริ่ม Build", notebook: "Notebook", workers: "Worker Compute" };
  $("#project-name").textContent = ["chat", "build"].includes(state.view) ? (state.project?.name || "PERSONAL WORKSPACE") : "PERSONAL WORKSPACE";
  $("#conversation-title").textContent = state.view === "chat" ? (state.conversation?.title || "เริ่มบทสนทนาใหม่") : titles[state.view];
  $("#conversation-title").title = $("#conversation-title").textContent;
  $$(".chat-only").forEach(node => node.hidden = state.view !== "chat");
}
function renderProjects() {
  const list = $("#projects");
  list.replaceChildren();
  const searching = !!state.chatSearchQuery;
  const results = state.chatSearchResults;
  const conversationMatches = new Map();
  if (searching && results) {
    results.conversations.forEach(conversation => {
      const items = conversationMatches.get(conversation.project_id) || [];
      items.push(conversation);
      conversationMatches.set(conversation.project_id, items);
    });
  }
  const matchingIds = searching && results
    ? new Set([...results.projects.map(project => project.id), ...results.conversations.map(conversation => conversation.project_id)])
    : null;
  const visibleProjects = matchingIds ? state.projects.filter(project => matchingIds.has(project.id)) : state.projects;
  if (!state.projects.length) list.append(el("p", "side-note", "สร้างโปรเจกต์เพื่อจัดเก็บบทสนทนาของคุณ"));
  else if (searching && results && !visibleProjects.length) list.append(el("p", "side-note", `ไม่พบผลลัพธ์สำหรับ “${state.chatSearchQuery}”`));
  visibleProjects.forEach(project => {
    const group = el("div", "project-group");
    const row = el("div", "project-row");
    const select = button(project.name, "project-item", () => selectProject(project.id, searching), "folder");
    select.setAttribute("aria-expanded", String(searching || project.id === state.project?.id));
    const childrenId = "conversations-" + project.id;
    select.setAttribute("aria-controls", childrenId);
    select.title = project.name;
    row.append(
      select,
      iconButton("แก้ไขชื่อโปรเจกต์ " + project.name, "edit", () => renameProject(project)),
      iconButton("ลบโปรเจกต์ " + project.name, "trash", () => deleteProject(project), "danger-icon"),
    );
    group.append(row);
    const children = el("div", "conversation-list");
    children.id = childrenId;
    children.hidden = !searching && project.id !== state.project?.id;
    if (!children.hidden) {
      const conversations = searching ? (conversationMatches.get(project.id) || []) : state.conversations;
      if (!searching && !conversations.length) children.append(el("p", "side-note", "ยังไม่มีแชท"));
      conversations.forEach(conversation => {
        const item = el("div", "conversation-row" + (conversation.id === state.conversation?.id ? " active" : ""));
        const selectChat = button("", "conversation-item", () => selectConversation(conversation.id, conversation.project_id));
        selectChat.replaceChildren(el("span", "conversation-title", conversation.title), el("span", "conversation-meta", formatDate(conversation.updated_at)));
        selectChat.title = conversation.title;
        if (conversation.id === state.conversation?.id) selectChat.setAttribute("aria-current", "page");
        item.append(
          selectChat,
          iconButton("แก้ไขชื่อแชท " + conversation.title, "edit", () => renameConversation(conversation)),
          iconButton("ลบแชท " + conversation.title, "trash", () => deleteConversation(conversation), "danger-icon"),
        );
        children.append(item);
      });
    }
    group.append(children);
    list.append(group);
  });
  renderBuildProjects();
}

let chatSearchTimer;
function clearChatSearch() {
  clearTimeout(chatSearchTimer);
  state.chatSearchQuery = "";
  state.chatSearchResults = null;
  state.chatSearchRevision++;
  $("#chat-sidebar-search").value = "";
  $("#chat-search-status").hidden = true;
}
async function runChatSearch() {
  const query = $("#chat-sidebar-search").value.trim();
  state.chatSearchQuery = query;
  state.chatSearchResults = null;
  const status = $("#chat-search-status");
  if (!query) {
    status.hidden = true;
    state.chatSearchRevision++;
    renderProjects();
    return;
  }
  const revision = ++state.chatSearchRevision;
  status.textContent = "กำลังค้นหา…";
  status.hidden = false;
  try {
    const results = await api("/api/search?q=" + encodeURIComponent(query));
    if (revision !== state.chatSearchRevision || query !== state.chatSearchQuery) return;
    state.chatSearchResults = results;
    const projectCount = new Set([
      ...results.projects.map(project => project.id),
      ...results.conversations.map(conversation => conversation.project_id),
    ]).size;
    const chatCount = results.conversations.length;
    status.textContent = `พบ ${projectCount} โปรเจกต์ · ${chatCount} แชท`;
    renderProjects();
  } catch (error) {
    if (revision !== state.chatSearchRevision) return;
    status.textContent = "ค้นหาไม่สำเร็จ";
    toast(errorMessage(error), true);
  }
}
function scheduleChatSearch() {
  clearTimeout(chatSearchTimer);
  const query = $("#chat-sidebar-search").value.trim();
  state.chatSearchQuery = query;
  if (!query) return runChatSearch();
  $("#chat-search-status").textContent = "กำลังค้นหา…";
  $("#chat-search-status").hidden = false;
  chatSearchTimer = setTimeout(runChatSearch, 220);
}

function buildDirty() {
  return !!state.buildFilePath && $("#build-editor").value !== state.buildFileContent;
}
function renderBuildDiagnostics() {
  const node = $("#build-diagnostics");
  if (!node) return;
  node.textContent = state.buildDiagnostics.length
    ? state.buildDiagnostics.map(item => `บรรทัด ${item.line}:${item.column} · ${item.message}`).join("\n")
    : (state.buildFilePath ? "ตรวจ syntax แล้ว · ไม่พบข้อผิดพลาด" : "");
  node.classList.toggle("valid", !state.buildDiagnostics.length && !!state.buildFilePath);
}
let diagnosticsTimer;
async function checkBuildDiagnostics(content = null) {
  if (!state.project || !state.buildFilePath) return;
  clearTimeout(diagnosticsTimer);
  diagnosticsTimer = setTimeout(async () => {
    try {
      const result = await api("/api/projects/" + encodeURIComponent(state.project.id) + "/workspace/diagnostics" + (content === null ? "?path=" + encodeURIComponent(state.buildFilePath) : ""), content === null
        ? { method: "GET" }
        : { ...mutation("POST", { path: state.buildFilePath, content }) });
      state.buildDiagnostics = result.issues || []; renderBuildDiagnostics();
    } catch { /* save endpoint remains the final guard */ }
  }, content === null ? 0 : 350);
}
function renderBuildProjects() {
  const list = $("#build-projects");
  list.replaceChildren();
  if (!state.projects.length) list.append(el("p", "side-note", "สร้างโปรเจกต์แรกเพื่อเริ่มเขียนโค้ด"));
  state.projects.forEach(project => {
    const item = button(project.name, "project-item" + (project.id === state.project?.id ? " active" : ""), () => selectBuildProject(project.id), "folder");
    if (project.id === state.project?.id) item.setAttribute("aria-current", "page");
    list.append(item);
  });
}
function syncBuild() {
  ensureHistoryControls();
  const hasProject = !!state.project;
  const hasFile = !!state.buildFilePath;
  $("#new-build-file").disabled = !hasProject || state.buildBusy;
  $("#refresh-build-files").disabled = !hasProject || state.buildBusy;
  $("#build-editor").disabled = !hasFile || state.buildBusy;
  $("#save-build-file").disabled = !hasFile || state.buildBusy || !buildDirty();
  $("#delete-build-file").disabled = !hasFile || state.buildBusy;
  $("#preview-build").disabled = !state.buildPreviewUrl || state.buildBusy;
  $("#run-command").disabled = !hasProject || state.buildBusy;
  $("#run-command-button").disabled = !hasProject || state.buildBusy;
  const assistantLocked = state.buildBusy || state.buildAssistantBusy;
  $("#build-agent-instruction").disabled = !hasProject || assistantLocked;
  $("#build-model").disabled = !hasProject || assistantLocked || !state.modelsReady;
  $("#build-chat-send").disabled = !hasProject || assistantLocked || !state.modelsReady || !$("#build-agent-instruction").value.trim();
  $("#build-agent-button").disabled = !hasProject || assistantLocked || !state.modelsReady || !buildActionInstruction();
  $("#clear-build-chat").disabled = !hasProject || assistantLocked || !getBuildChat().length;
  $("#build-chat-form").setAttribute("aria-busy", String(state.buildAssistantBusy));
  syncGuidedBuild();
}
function ensureHistoryControls() {
  const heading = $(".build-editor-pane > .build-pane-heading");
  if (!heading || $("#build-history-controls")) return;
  const controls = el("div", "history-controls"); controls.id = "build-history-controls";
  controls.append(button("ส่งออก ZIP", "text-button", exportWebsite), button("ตรวจความปลอดภัย", "text-button", runSecurityAudit), button("Undo", "text-button", () => workspaceHistoryAction("undo")), button("Redo", "text-button", () => workspaceHistoryAction("redo")));
  heading.append(controls);
}
async function exportWebsite() {
  if (!state.project || state.buildBusy) return;
  try {
    state.buildBusy = true; syncBuild();
    const blob = await api(`/api/projects/${encodeURIComponent(state.project.id)}/workspace/export`, { blob: true, timeout: 60000 });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url; link.download = "hermes-website.zip"; link.hidden = true;
    document.body.append(link); link.click(); link.remove(); URL.revokeObjectURL(url);
    toast("ส่งออกเว็บไซต์เป็น ZIP แล้ว");
  } catch (error) { toast(errorMessage(error), true); }
  finally { state.buildBusy = false; syncBuild(); }
}
async function runSecurityAudit() {
  if (!state.project || state.buildBusy) return;
  try {
    state.buildBusy = true; syncBuild();
    const report = await api(`/api/projects/${encodeURIComponent(state.project.id)}/workspace/security-audit`);
    const errors = (report.issues || []).filter(item => item.severity === "error").length;
    const warnings = (report.issues || []).filter(item => item.severity === "warning").length;
    toast(report.status === "passed" ? `ตรวจผ่าน · คำเตือน ${warnings} รายการ` : `ไม่ผ่าน · พบข้อผิดพลาด ${errors} รายการ`, report.status !== "passed");
    state.buildDiagnostics = (report.issues || []).map(item => ({ line: item.line, column: 1, message: `[${item.code}] ${item.message}` }));
    renderBuildDiagnostics();
  } catch (error) { toast(errorMessage(error), true); }
  finally { state.buildBusy = false; syncBuild(); }
}
async function workspaceHistoryAction(action) {
  if (!state.project || state.buildBusy) return;
  try {
    state.buildBusy = true; syncBuild();
    await api(`/api/projects/${encodeURIComponent(state.project.id)}/workspace/history/${action}`, { method: "POST" });
    const path = state.buildFilePath;
    state.buildFilePath = null;
    await loadBuildFiles();
    if (path && state.buildFiles.some(file => file.path === path)) await openBuildFile(path);
    toast(action === "undo" ? "ย้อนกลับแล้ว" : "ทำซ้ำแล้ว");
  } catch (error) { toast(errorMessage(error), true); }
  finally { state.buildBusy = false; syncBuild(); }
}
function checkedValues(name) {
  return $$(`input[name="${name}"]:checked`).map(node => node.value);
}
function isCatalogBlueprint(blueprintId) { return blueprintId.startsWith("catalog."); }
function isWebsiteBlueprint(blueprintId) { return blueprintId.startsWith("website.") || isCatalogBlueprint(blueprintId); }
const pageTypeChoices = [
  ["home", "หน้าหลัก"], ["about", "เกี่ยวกับองค์กร"], ["policy", "นโยบาย"],
  ["document_library", "กฎระเบียบ / เอกสาร"], ["knowledge_library", "คลังความรู้"],
  ["product_catalog", "สินค้า"], ["service", "บริการ"], ["news", "ข่าวสาร"],
  ["contact", "ติดต่อ"], ["standard", "เนื้อหาทั่วไป"],
];
function createPageTypeSelect(selected = "standard") {
  const select = el("select", "create-page-type");
  select.setAttribute("aria-label", "รูปแบบหน้า");
  pageTypeChoices.forEach(([value, label]) => {
    const option = el("option", "", label);
    option.value = value;
    option.selected = value === selected;
    select.append(option);
  });
  return select;
}
function createPayload() {
  if (state.guidedPayload) return state.guidedPayload;
  const blueprintId = $("#create-blueprint").value;
  const website = isWebsiteBlueprint(blueprintId);
  const pages = $$(".create-tab-row").map(row => ({
    name: $(".create-tab-name", row).value.trim(),
    pageType: $(".create-page-type", row).value,
  })).filter(page => page.name);
  if (website) return { values: {
    project_name: $("#create-project-name").value.trim(),
    blueprint_id: blueprintId,
    tabs: pages.map(page => page.name),
    page_types: pages.map(page => page.pageType),
    color_tone: $("#create-color-tone").value,
    network_scope: $("#create-network").value,
    auth_enabled: $("#create-auth").checked,
    density: $("#create-density").value,
    language: checkedValues("create-language"),
  }};
  const modules = checkedValues("create-module");
  const aiEnabled = modules.includes("ai_assistant");
  return { values: {
    project_name: $("#create-project-name").value.trim(),
    project_type: "internal_dashboard",
    modules,
    network_scope: $("#create-network").value,
    auth_enabled: $("#create-auth").checked,
    ai_assistant: aiEnabled,
    ai_capabilities: aiEnabled ? checkedValues("create-ai-capability") : [],
    ai_autonomy: aiEnabled ? $("#create-ai-autonomy").value : "approval_required",
    theme: "windows_xp.v1",
    density: $("#create-density").value,
    language: checkedValues("create-language"),
  }};
}
function guidedFormId() { return isWebsiteBlueprint($("#create-blueprint").value) ? "website_standard.v1" : "internal_dashboard.v1"; }
function guidedValueLabel(value) { return Array.isArray(value) ? value.join(", ") : (value === true ? "ใช่" : value === false ? "ไม่ใช่" : String(value ?? "")); }
function renderGuidedConversation() {
  const conversation = state.guidedConversation;
  const questionBox = $("#guided-question");
  const answerBox = $("#guided-answer");
  const summaryBox = $("#guided-summary");
  if (!conversation) return;
  $("#guided-reason").textContent = conversation.question?.reason || (conversation.status === "review" ? "ตรวจข้อมูลทั้งหมดให้ถูกต้องก่อนเริ่มสร้างเว็บไซต์" : "");
  questionBox.replaceChildren(); answerBox.replaceChildren(); summaryBox.replaceChildren();
  summaryBox.hidden = conversation.status !== "review";
  answerBox.hidden = conversation.status !== "collecting";
  if (conversation.question) questionBox.append(el("p", "", conversation.question.prompt));
  if (conversation.clarification) questionBox.append(el("p", "form-error", conversation.clarification));
  if (conversation.status === "collecting" && conversation.question) {
    const q = conversation.question;
    if (q.kind === "select") {
      const select = el("select"); select.id = "guided-value";
      q.options.forEach(value => { const option = el("option", "", value); option.value = value; option.selected = value === q.suggested; select.append(option); });
      answerBox.append(select);
    } else if (q.kind === "multi_select") {
      const options = el("div", "guided-options");
      q.options.forEach(value => { const label = el("label"); const input = document.createElement("input"); input.type = "checkbox"; input.value = value; input.checked = Array.isArray(q.suggested) && q.suggested.includes(value); label.append(input, el("span", "", value)); options.append(label); });
      answerBox.append(options);
      if (!q.options.length) { const custom = el("input"); custom.type = "text"; custom.id = "guided-custom"; custom.value = Array.isArray(q.suggested) ? q.suggested.join(", ") : ""; custom.placeholder = "พิมพ์รายการคั่นด้วย ,"; answerBox.append(custom); }
    } else if (q.kind === "boolean") {
      const label = el("label"); const input = document.createElement("input"); input.type = "checkbox"; input.id = "guided-value"; input.checked = q.suggested === true; label.append(input, el("span", "", "ใช่")); answerBox.append(label);
    } else {
      const input = el("input"); input.type = "text"; input.id = "guided-value"; input.value = typeof q.suggested === "string" ? q.suggested : ""; input.placeholder = "พิมพ์คำตอบของคุณ"; answerBox.append(input);
    }
    const send = button("ตอบคำถามนี้", "primary", sendGuidedAnswer);
    answerBox.append(send);
  }
  if (conversation.status === "review") {
    const lines = el("div", "guided-summary-lines");
    conversation.summary.forEach(item => { const row = el("div", "guided-summary-row"); row.append(el("span", "", `${item.label}: ${guidedValueLabel(item.value)}`), button("แก้", "text-button", () => reviseGuidedConversation(item.field_id))); lines.append(row); });
    summaryBox.append(lines);
    const confirm = button("ยืนยันข้อมูลและเริ่ม Build", "primary", confirmGuidedConversation);
    summaryBox.append(document.createElement("br"), confirm);
  }
  if (conversation.status === "confirmed") summaryBox.append(el("p", "", "ยืนยันแล้ว กำลังส่งข้อมูลไปยัง Build…"));
}
async function startGuidedConversation() {
  if (!state.project || state.buildBusy) return;
  try {
    state.buildBusy = true; syncBuild();
    state.guidedConversation = await api(`/api/projects/${encodeURIComponent(state.project.id)}/bth-create/conversation/start`, { ...mutation("POST", { form_id: guidedFormId(), initial_values: { project_name: $("#create-project-name").value.trim() || state.project.name } }) });
    renderGuidedConversation();
  } catch (error) { toast(errorMessage(error), true); }
  finally { state.buildBusy = false; syncBuild(); }
}
async function sendGuidedAnswer() {
  const conversation = state.guidedConversation; const q = conversation?.question;
  if (!q || state.buildBusy) return;
  let value;
  if (q.kind === "multi_select") { value = $$("input[type=checkbox]", $("#guided-answer")).map(input => input.checked ? input.value : null).filter(Boolean); const custom = $("#guided-custom")?.value.trim(); if (custom) value.push(...custom.split(",").map(item => item.trim()).filter(Boolean)); }
  else if (q.kind === "boolean") value = $("#guided-value").checked;
  else value = $("#guided-value").value;
  try {
    state.buildBusy = true; syncBuild();
    state.guidedConversation = await api(`/api/projects/${encodeURIComponent(state.project.id)}/bth-create/conversation/answer`, { ...mutation("POST", { conversation, answer: { field_id: q.field_id, value } }) });
    renderGuidedConversation();
  } catch (error) { toast(errorMessage(error), true); }
  finally { state.buildBusy = false; syncBuild(); }
}
async function reviseGuidedConversation(fieldId) {
  if (!state.guidedConversation || state.buildBusy) return;
  try {
    state.buildBusy = true; syncBuild();
    state.guidedConversation = await api(`/api/projects/${encodeURIComponent(state.project.id)}/bth-create/conversation/revise`, { ...mutation("POST", { conversation: state.guidedConversation, field_id: fieldId }) });
    renderGuidedConversation();
  } catch (error) { toast(errorMessage(error), true); }
  finally { state.buildBusy = false; syncBuild(); }
}
async function confirmGuidedConversation() {
  if (!state.guidedConversation || state.buildBusy) return;
  let handedOff = false;
  try {
    state.buildBusy = true; syncBuild();
    const confirmed = await api(`/api/projects/${encodeURIComponent(state.project.id)}/bth-create/conversation/confirm`, { ...mutation("POST", { conversation: state.guidedConversation }) });
    state.guidedConversation = confirmed; state.guidedPayload = { values: confirmed.values };
    $("#create-project-name").value = confirmed.values.project_name || state.project.name;
    renderGuidedConversation();
    state.buildBusy = false; syncBuild();
    handedOff = true;
    $("#bth-create-form").requestSubmit();
  } catch (error) { toast(errorMessage(error), true); }
  finally { if (!handedOff) { state.buildBusy = false; syncBuild(); } }
}
function syncGuidedBuild() {
  const pane = $(".build-editor-pane");
  pane.classList.toggle("build-guided", state.guidedBuild);
  $("#bth-create-form").hidden = !state.guidedBuild;
  $("#toggle-guided-build").textContent = state.guidedBuild ? "Direct Build" : "Guided Build";
  if (state.guidedBuild && state.project && $("#create-project-name").dataset.projectId !== state.project.id) {
    $("#create-project-name").value = state.project.name;
    $("#create-project-name").dataset.projectId = state.project.id;
    state.createSpec = null;
  }
  const blueprintId = $("#create-blueprint").value;
  const website = isWebsiteBlueprint(blueprintId);
  const catalog = isCatalogBlueprint(blueprintId);
  $("#create-form-title").textContent = website ? "สร้าง " + $("#create-blueprint").selectedOptions[0].text : "สร้าง Internal Dashboard";
  $("#create-dashboard-options").hidden = website;
  $("#create-website-options").hidden = !website;
  $("#create-navigation-legend").textContent = catalog ? "หัวข้อ / หมวดหมู่" : "หน้าเว็บไซต์และรูปแบบของแต่ละหน้า";
  const aiEnabled = !website && checkedValues("create-module").includes("ai_assistant");
  $("#create-ai-options").hidden = !aiEnabled;
  $("#create-theme-summary").textContent = website
    ? (catalog ? "Catalog Website · " : "Standard Website · ") + $("#create-blueprint").selectedOptions[0].text + " · " + $("#create-color-tone").selectedOptions[0].text
    : "Windows XP · Blueprint dashboard.internal.v1";
  const disabled = !state.project || state.buildBusy;
  $$("input, select, button", $("#bth-create-form")).forEach(node => node.disabled = disabled);
  const tabRows = $$(".create-tab-row");
  tabRows.forEach(row => $(".remove-create-tab", row).disabled = disabled || tabRows.length <= 1);
  $("#add-create-tab").disabled = disabled || tabRows.length >= 12;
  $("#build-file-name").textContent = state.guidedBuild ? (catalog ? "BTH Create · Catalog Website" : website ? "BTH Create · Standard Website" : "BTH Create · Internal Dashboard") : (state.buildFilePath || "ยังไม่ได้เปิดไฟล์");
}
function renderBuildFiles() {
  const list = $("#build-file-list");
  list.replaceChildren();
  if (!state.project) list.append(el("p", "side-note", "เลือกหรือสร้างโปรเจกต์ก่อน"));
  else if (!state.buildFiles.length) list.append(el("p", "side-note", "ยังไม่มีไฟล์ กด + เพื่อสร้างไฟล์แรก"));
  state.buildFiles.forEach(file => {
    const item = button(file.path, "build-file-item" + (file.path === state.buildFilePath ? " active" : ""), () => openBuildFile(file.path), "file");
    item.title = file.path + " · " + file.size.toLocaleString() + " bytes";
    list.append(item);
  });
  const previewEntry = ["index.html", "dist/index.html", "build/index.html", "public/index.html"].find(path => state.buildFiles.some(file => file.path === path));
  state.buildPreviewUrl = state.project && previewEntry
    ? "/api/projects/" + encodeURIComponent(state.project.id) + "/workspace/preview/"
    : null;
  $("#build-file-name").textContent = state.buildFilePath || "ยังไม่ได้เปิดไฟล์";
  syncBuild();
}

const buildChatKey = () => "hermes-build-chat-" + (state.project?.id || "none");
function getBuildChat() {
  if (!state.project) return [];
  const key = buildChatKey();
  if (state.buildChats.has(key)) return state.buildChats.get(key);
  try {
    const messages = readStore(key, item => item && ["user", "assistant"].includes(item.role) && typeof item.content === "string").slice(-30);
    state.buildChats.set(key, messages);
    return messages;
  } catch {
    state.buildStorageDisabled.add(key);
    state.buildChats.set(key, []);
    if (!state.buildStorageWarned) {
      state.buildStorageWarned = true;
      toast("ใช้ประวัติ Build Assistant ชั่วคราวในแท็บนี้ เนื่องจากอ่านพื้นที่เก็บข้อมูลของเบราว์เซอร์ไม่ได้", true);
    }
    return [];
  }
}
function saveBuildChat(messages) {
  if (!state.project) return;
  const key = buildChatKey(), saved = messages.slice(-30);
  state.buildChats.set(key, saved);
  if (state.buildStorageDisabled.has(key)) return;
  try { saveStore(key, saved); }
  catch {
    state.buildStorageDisabled.add(key);
    if (!state.buildStorageWarned) {
      state.buildStorageWarned = true;
      toast("บทสนทนายังใช้ต่อได้ แต่จะไม่ถูกเก็บหลังปิดแท็บ เพราะพื้นที่เบราว์เซอร์ไม่พร้อม", true);
    }
  }
}
function buildActionInstruction() {
  const messages = [...getBuildChat()];
  const draft = $("#build-agent-instruction")?.value.trim() || "";
  if (draft && (messages.at(-1)?.role !== "user" || messages.at(-1)?.content !== draft)) {
    messages.push({ role: "user", content: draft });
  }
  const selected = [];
  let used = 0;
  for (const message of messages.slice(-16).reverse()) {
    const line = (message.role === "user" ? "ผู้ใช้: " : "Build Assistant: ") + message.content.trim();
    const available = 3700 - used;
    if (!line.trim() || available <= 0) break;
    const clipped = line.slice(0, available);
    selected.unshift(clipped);
    used += clipped.length;
    if (clipped.length < line.length) break;
  }
  return selected.length ? "สร้างหรือปรับปรุงโปรเจกต์ตาม requirement จากบทสนทนานี้:\n" + selected.join("\n") : "";
}
function buildChatMessage(message, pending = false) {
  const node = el("article", "build-chat-message " + message.role + (pending ? " pending" : ""));
  const label = el("span", "build-chat-label", message.role === "user" ? "คุณ" : "AI");
  if (message.role === "assistant") label.prepend(icon("chat"));
  node.append(label, el("div", "build-chat-content", message.content));
  return node;
}
function renderBuildChat(pending = false) {
  const chat = $("#build-chat");
  chat.replaceChildren();
  if (!state.project) {
    const empty = el("div", "build-chat-empty");
    empty.append(el("strong", "", "เลือกโปรเจกต์เพื่อเริ่มคุย"), el("span", "", "AI จะอ่านไฟล์และช่วยพัฒนาไอเดียไปกับคุณ"));
    chat.append(empty);
  } else {
    const messages = getBuildChat();
    if (!messages.length) {
      const welcome = el("div", "build-chat-empty");
      welcome.append(el("strong", "", "เริ่มจากไอเดียของคุณ"), el("span", "", "เล่าเป้าหมายคร่าว ๆ แล้ว AI จะช่วยถามให้ requirement ชัดขึ้น"));
      chat.append(welcome);
    }
    messages.forEach(message => chat.append(buildChatMessage(message)));
    if (pending) chat.append(buildChatMessage({ role: "assistant", content: "กำลังคิด…" }, true));
  }
  $("#build-chat-suggestions").hidden = !state.project || getBuildChat().length > 0;
  requestAnimationFrame(() => chat.scrollTop = chat.scrollHeight);
  syncBuild();
}
function showBuildPreview(url = state.buildPreviewUrl) {
  if (!url) return;
  state.buildPreviewUrl = url;
  const frame = $("#build-preview-frame");
  frame.src = url + (url.includes("?") ? "&" : "?") + "editor=1&refresh=" + Date.now();
  frame.onload = () => frame.contentWindow?.postMessage({ type: "hermes:edit-mode", enabled: state.previewEditMode }, "*");
  setPreviewViewport();
  if (!$("#build-preview-dialog").open) $("#build-preview-dialog").showModal();
  syncBuild();
}
function setPreviewViewport() {
  const viewport = $("#preview-viewport").value;
  const frame = $("#build-preview-frame");
  frame.classList.toggle("viewport-tablet", viewport === "tablet");
  frame.classList.toggle("viewport-mobile", viewport === "mobile");
}
function setPreviewEditMode(enabled) {
  state.previewEditMode = enabled;
  $("#preview-edit-mode").textContent = enabled ? "ปิดการเลือก" : "เลือก Element";
  $("#preview-edit-mode").classList.toggle("primary", enabled);
  $("#build-preview-frame").contentWindow?.postMessage({ type: "hermes:edit-mode", enabled }, "*");
}
async function loadPreviewProperties(nodeId) {
  if (!state.project || !nodeId) return;
  try {
    const node = await api(`/api/projects/${encodeURIComponent(state.project.id)}/workspace/preview/node/${encodeURIComponent(nodeId)}`);
    state.previewNode = node;
    ensurePreviewAssistantPanel();
    $("#preview-properties-empty").hidden = true;
    $("#preview-properties-form").hidden = false;
    $("#preview-node-meta").textContent = `${node.tag} · ${node.node_id} · ${node.path}:${node.line}`;
    $("#preview-prop-text").value = node.text || "";
    $("#preview-prop-href").value = node.href || "";
    $("#preview-prop-src").value = node.src || "";
    ["color", "background_color", "font_size", "margin", "padding"].forEach(name => $("#preview-prop-" + name).value = node.styles?.[name.replace("_", "-")] || "");
    $("#preview-prop-text_align").value = node.styles?.["text-align"] || "";
  } catch (error) { toast(errorMessage(error), true); }
}
function ensurePreviewAssistantPanel() {
  if ($("#preview-assistant-panel")) return;
  const panel = el("section", "preview-assistant-panel"); panel.id = "preview-assistant-panel";
  panel.append(el("h3", "", "ขอให้ Hermes ช่วยแก้"), el("p", "", "ต้องเลือก Element ก่อน และจะแสดง patch ให้ตรวจสอบก่อน Apply"));
  const instruction = el("textarea"); instruction.id = "preview-assistant-instruction"; instruction.rows = 3; instruction.placeholder = "เช่น เปลี่ยนหัวข้อนี้ให้กระชับขึ้น"; panel.append(instruction);
  const actions = el("div", "preview-assistant-actions");
  actions.append(button("เสนอ Patch", "secondary-button", proposePreviewPatch), button("Regenerate", "text-button", regeneratePreviewPatch), button("Reject", "text-button", rejectPreviewPatch)); panel.append(actions);
  const diff = el("pre", "preview-patch-diff"); diff.id = "preview-patch-diff"; panel.append(diff);
  const apply = button("Apply Patch", "primary", applyPreviewPatch); apply.id = "preview-apply-patch"; apply.disabled = true; panel.append(apply);
  $("#preview-properties").append(panel);
}
async function proposePreviewPatch() {
  const instruction = $("#preview-assistant-instruction")?.value.trim();
  if (!state.project || !state.previewNode || !instruction || state.buildBusy) return;
  try {
    state.buildBusy = true; syncBuild();
    state.previewAssistantProposal = await api(`/api/projects/${encodeURIComponent(state.project.id)}/workspace/assistant/propose-patch`, { ...mutation("POST", { node_id: state.previewNode.node_id, instruction, model: $("#build-model").value }), timeout: 180000 });
    $("#preview-patch-diff").textContent = JSON.stringify(state.previewAssistantProposal.patch, null, 2) + "\n\n" + state.previewAssistantProposal.message;
    $("#preview-apply-patch").disabled = false;
  } catch (error) { toast(errorMessage(error), true); }
  finally { state.buildBusy = false; syncBuild(); }
}
async function rejectPreviewPatch() {
  if (!state.project || !state.previewAssistantProposal?.patch) return;
  try {
    await api(`/api/projects/${encodeURIComponent(state.project.id)}/workspace/assistant/reject-patch`, mutation("POST", { patch_id: state.previewAssistantProposal.patch.patch_id, reason: "User rejected proposal" }));
    state.previewAssistantProposal = null; $("#preview-patch-diff").textContent = ""; $("#preview-apply-patch").disabled = true;
    toast("ปฏิเสธ Patch แล้ว");
  } catch (error) { toast(errorMessage(error), true); }
}
async function regeneratePreviewPatch() {
  if (state.previewAssistantProposal?.patch) await rejectPreviewPatch();
  return proposePreviewPatch();
}
async function applyPreviewPatch() {
  if (!state.project || !state.previewAssistantProposal?.patch || state.buildBusy) return;
  try {
    state.buildBusy = true; syncBuild();
    await api(`/api/projects/${encodeURIComponent(state.project.id)}/workspace/assistant/apply-patch`, { ...mutation("POST", { patch: state.previewAssistantProposal.patch }) });
    state.previewAssistantProposal = null; $("#preview-patch-diff").textContent = ""; $("#preview-apply-patch").disabled = true;
    toast("Apply Patch สำเร็จ"); await loadBuildFiles(); showBuildPreview();
  } catch (error) { toast(errorMessage(error), true); }
  finally { state.buildBusy = false; syncBuild(); }
}
async function applyPreviewProperties() {
  if (!state.project || !state.previewNode || state.buildBusy) return;
  const nodeId = state.previewNode.node_id;
  const updates = [
    ["text", $("#preview-prop-text").value], ["href", $("#preview-prop-href").value], ["src", $("#preview-prop-src").value],
    ["color", $("#preview-prop-color").value], ["background_color", $("#preview-prop-background_color").value], ["font_size", $("#preview-prop-font_size").value],
    ["margin", $("#preview-prop-margin").value], ["padding", $("#preview-prop-padding").value], ["text_align", $("#preview-prop-text_align").value],
  ].filter(([, value]) => value.trim());
  if (!updates.length) return;
  try {
    state.buildBusy = true; syncBuild();
    for (const [property, value] of updates) await api(`/api/projects/${encodeURIComponent(state.project.id)}/workspace/preview/update-property`, { ...mutation("POST", { node_id: nodeId, property, value }) });
    toast("บันทึก Properties แล้ว");
    await loadBuildFiles(); showBuildPreview();
  } catch (error) { toast(errorMessage(error), true); }
  finally { state.buildBusy = false; syncBuild(); }
}
async function loadBuildFiles() {
  renderBuildChat();
  if (!state.project) { state.buildFiles = []; state.buildFilePath = null; state.buildFileContent = ""; state.buildFileRevision = 0; state.buildDiagnostics = []; $("#build-editor").value = ""; renderBuildDiagnostics(); renderBuildFiles(); return; }
  state.buildBusy = true; syncBuild();
  try {
    const data = await api("/api/projects/" + encodeURIComponent(state.project.id) + "/workspace/files");
    state.buildFiles = data.files;
    if (state.buildFilePath && !state.buildFiles.some(file => file.path === state.buildFilePath)) {
      state.buildFilePath = null; state.buildFileContent = ""; state.buildFileRevision = 0; state.buildDiagnostics = []; $("#build-editor").value = ""; renderBuildDiagnostics();
    }
    renderBuildFiles();
  } catch (error) { toast(errorMessage(error), true); }
  finally { state.buildBusy = false; syncBuild(); }
}
async function selectBuildProject(id) {
  if (buildDirty() && !await confirmAction("ละทิ้งการแก้ไข?", "ไฟล์ปัจจุบันยังไม่ได้บันทึก", "ละทิ้ง")) return;
  await selectProject(id);
  switchView("build");
}
async function openBuildFile(path) {
  if (state.buildBusy || !state.project || path === state.buildFilePath) return;
  if (buildDirty() && !await confirmAction("ละทิ้งการแก้ไข?", "ไฟล์ปัจจุบันยังไม่ได้บันทึก", "ละทิ้ง")) return;
  state.buildBusy = true; syncBuild();
  try {
    const data = await api("/api/projects/" + encodeURIComponent(state.project.id) + "/workspace/file?path=" + encodeURIComponent(path));
    state.buildFilePath = data.path; state.buildFileContent = data.content; state.buildFileRevision = data.revision || 0; state.buildDiagnostics = []; $("#build-editor").value = data.content; renderBuildDiagnostics(); checkBuildDiagnostics();
    renderBuildFiles();
  } catch (error) { toast(errorMessage(error), true); }
  finally { state.buildBusy = false; syncBuild(); }
}
function saveDraft() {
  if (!state.conversation) return;
  const draft = composerDraft();
  if (draft.text.trim() || draft.files.length) state.drafts.set(state.conversation.id, draft);
  else state.drafts.delete(state.conversation.id);
}
function composerDraft() {
  return { text: $("#message").value, files: state.files.map(file => ({ ...file })), search: $("#search").checked };
}
function restoreComposerDraft(draft) {
  $("#message").value = draft?.text || "";
  state.files = draft?.files?.map(file => ({ ...file })) || [];
  $("#search").checked = !!draft?.search;
  renderAttachments();
  resizeInput();
}
function applyConversation(data) {
  state.conversation = data?.conversation || null;
  state.messages = data?.messages || [];
  loadChatGuided();
  const draft = state.drafts.get(state.conversation?.id);
  $("#message").value = draft?.text || "";
  state.files = draft?.files || [];
  $("#search").checked = !!draft?.search;
  setModelSelection(state.conversation?.model || "auto");
  composerError();
  renderAttachments();
  renderMessages();
  renderProjects();
  setHeading();
  resizeInput();
}
async function selectProject(id, clearSearch = false) {
  if (guardNavigation()) return;
  saveDraft();
  const revision = ++state.revision;
  state.loading = true;
  syncComposer();
  try {
    const data = await api("/api/projects/" + id + "/conversations");
    const detail = data.conversations.length ? await api("/api/conversations/" + data.conversations[0].id) : null;
    if (revision !== state.revision) return;
    state.project = state.projects.find(project => project.id === id);
    state.conversations = data.conversations;
    if (clearSearch) clearChatSearch();
    applyConversation(detail);
    closeDrawer();
  } catch (error) { toast(errorMessage(error), true); }
  finally { if (revision === state.revision) { state.loading = false; syncComposer(); } }
}
async function selectConversation(id, projectId = state.project?.id) {
  if (guardNavigation()) return;
  saveDraft();
  const revision = ++state.revision;
  state.loading = true;
  syncComposer();
  try {
    const [detail, projectData] = await Promise.all([
      api("/api/conversations/" + id),
      projectId && projectId !== state.project?.id
        ? api("/api/projects/" + encodeURIComponent(projectId) + "/conversations")
        : Promise.resolve(null),
    ]);
    if (revision !== state.revision) return;
    if (projectData) {
      state.project = state.projects.find(project => project.id === projectId) || state.project;
      state.conversations = projectData.conversations;
    }
    if (state.chatSearchQuery) clearChatSearch();
    applyConversation(detail); closeDrawer();
  }
  catch (error) { toast(errorMessage(error), true); }
  finally { if (revision === state.revision) { state.loading = false; syncComposer(); } }
}
async function reloadProjects() {
  const data = await api("/api/projects");
  state.projects = data.projects;
  if (state.project) state.project = data.projects.find(project => project.id === state.project.id) || null;
  renderProjects();
}
async function recoverMissingConversation(missingId, draft) {
  const revision = ++state.revision;
  state.drafts.delete(missingId);
  state.loading = true;
  state.conversation = null;
  state.messages = [];
  syncComposer();
  try {
    await reloadProjects();
    if (revision !== state.revision) return;
    if (state.project) {
      const data = await api("/api/projects/" + state.project.id + "/conversations");
      if (revision !== state.revision) return;
      state.conversations = data.conversations;
      const next = data.conversations[0] ? await api("/api/conversations/" + data.conversations[0].id) : null;
      if (revision !== state.revision) return;
      applyConversation(next);
    } else {
      state.conversations = [];
      applyConversation(null);
    }
    restoreComposerDraft(draft);
    toast("แชทเดิมถูกลบแล้ว เลือกหรือสร้างแชทใหม่ก่อนส่งข้อความ", true);
  } catch (recoveryError) {
    toast("ไม่พบแชทเดิม และไม่สามารถโหลดรายการล่าสุดได้: " + errorMessage(recoveryError), true);
  } finally {
    if (revision === state.revision) {
      state.loading = false;
      syncComposer();
      composerError("แชทนี้ถูกลบแล้ว โปรดเลือกหรือสร้างแชทก่อนส่งข้อความ");
    }
  }
}
async function newChat() {
  if (guardNavigation()) return;
  if (!state.project) { newProject(); return; }
  saveDraft();
  const revision = ++state.revision;
  state.loading = true;
  syncComposer();
  try {
    const conversation = await api("/api/projects/" + state.project.id + "/conversations", mutation("POST", { title: "แชทใหม่", model: $("#model").value }));
    if (revision !== state.revision) return;
    state.conversations.unshift(conversation);
    if (state.chatSearchQuery) clearChatSearch();
    applyConversation({ conversation, messages: [] });
    closeDrawer();
    switchView("chat");
    toast("สร้างแชทแล้ว");
  } catch (error) { toast(errorMessage(error), true); }
  finally { if (revision === state.revision) { state.loading = false; syncComposer(); $("#message").focus(); } }
}
let nameAction;
function openName(title, value, limit, action) {
  if (guardNavigation()) return;
  closeDrawer();
  $("#name-dialog-title").textContent = title;
  $("#name-input-label").textContent = title;
  $("#name-input").value = value;
  $("#name-input").maxLength = limit;
  nameAction = action;
  formError($("#name-form"));
  $("#name-dialog").showModal();
  $("#name-input").focus();
  $("#name-input").select();
}
function newProject() {
  const destination = state.view === "build" ? "build" : "chat";
  openName("สร้างโปรเจกต์", "", 120, async name => {
    const project = await api("/api/projects", mutation("POST", { name }));
    state.projects.unshift(project);
    if (state.chatSearchQuery) clearChatSearch();
    saveDraft();
    state.project = project;
    state.conversations = [];
    applyConversation(null);
    switchView(destination);
    if (destination === "build") await loadBuildFiles();
  });
}
function renameProject(project) {
  openName("แก้ไขชื่อโปรเจกต์", project.name, 120, async name => {
    const updated = await api("/api/projects/" + project.id, mutation("PATCH", { name }));
    Object.assign(project, updated);
    renderProjects();
    setHeading();
  });
}
function renameConversation(conversation) {
  openName("แก้ไขชื่อแชท", conversation.title, 160, async title => {
    const updated = await api("/api/conversations/" + conversation.id, mutation("PATCH", { title }));
    Object.assign(conversation, updated);
    const cached = state.conversations.find(item => item.id === updated.id);
    if (cached) Object.assign(cached, updated);
    if (state.conversation?.id === conversation.id) Object.assign(state.conversation, updated);
    renderProjects();
    setHeading();
  });
}
async function deleteProject(project) {
  if (guardNavigation()) return;
  const confirmed = await confirmAction(
    "ลบโปรเจกต์นี้หรือไม่?",
    `โปรเจกต์ “${project.name}” รวมทั้งแชทและไฟล์ Build ทั้งหมดจะถูกลบถาวร การดำเนินการนี้ย้อนกลับไม่ได้`,
    "ลบโปรเจกต์",
  );
  if (!confirmed) return;
  const revision = ++state.revision;
  state.loading = true;
  syncComposer();
  try {
    await api("/api/projects/" + encodeURIComponent(project.id), { method: "DELETE" });
    if (revision !== state.revision) return;
    const buildKey = "hermes-build-chat-" + project.id;
    state.buildChats.delete(buildKey);
    state.buildStorageDisabled.delete(buildKey);
    try { localStorage.removeItem(buildKey); } catch { /* Server data was deleted successfully. */ }
    const wasCurrent = state.project?.id === project.id;
    state.projects = state.projects.filter(item => item.id !== project.id);
    if (wasCurrent) {
      state.project = null;
      state.conversations = [];
      state.conversation = null;
      state.messages = [];
      state.buildFiles = [];
      state.buildFilePath = null;
      state.buildFileContent = "";
      $("#build-editor").value = "";
      applyConversation(null);
    }
    renderProjects();
    setHeading();
    renderBuildFiles();
    renderBuildChat();
    toast("ลบโปรเจกต์ แชท และไฟล์ภายในแล้ว");
  } catch (error) { toast(errorMessage(error), true); }
  finally { if (revision === state.revision) { state.loading = false; syncComposer(); } }
}
async function deleteConversation(conversation) {
  if (guardNavigation()) return;
  const confirmed = await confirmAction(
    "ลบแชทนี้หรือไม่?",
    `แชท “${conversation.title}” และประวัติข้อความทั้งหมดจะถูกลบถาวร การดำเนินการนี้ย้อนกลับไม่ได้`,
    "ลบแชท",
  );
  if (!confirmed) return;
  const revision = ++state.revision;
  state.loading = true;
  syncComposer();
  try {
    await api("/api/conversations/" + encodeURIComponent(conversation.id), { method: "DELETE" });
    if (revision !== state.revision) return;
    const wasCurrent = state.conversation?.id === conversation.id;
    state.conversations = state.conversations.filter(item => item.id !== conversation.id);
    if (state.chatSearchResults) {
      state.chatSearchResults.conversations = state.chatSearchResults.conversations.filter(item => item.id !== conversation.id);
    }
    state.drafts.delete(conversation.id);
    if (wasCurrent) {
      state.conversation = null;
      state.messages = [];
      applyConversation(null);
    }
    renderProjects();
    setHeading();
    toast("ลบแชทแล้ว");
  } catch (error) { toast(errorMessage(error), true); }
  finally { if (revision === state.revision) { state.loading = false; syncComposer(); } }
}
$("#name-form").addEventListener("submit", async event => {
  event.preventDefault();
  const value = $("#name-input").value.trim();
  if (!value) return formError(event.currentTarget, "กรุณาระบุชื่อ");
  const form = event.currentTarget;
  if (form.dataset.saving) return;
  form.dataset.saving = "true";
  $$("button", form).forEach(node => node.disabled = true);
  try { await nameAction(value); $("#name-dialog").close(); toast("บันทึกชื่อแล้ว"); }
  catch (error) { formError(form, errorMessage(error)); }
  finally { delete form.dataset.saving; $$("button", form).forEach(node => node.disabled = false); syncComposer(); }
});
function setModelSelection(id) {
  const select = $("#model");
  $$("option[data-unavailable]", select).forEach(node => node.remove());
  if (![...select.options].some(option => option.value === id)) {
    const option = new Option(id + " · ไม่พร้อมใช้งาน", id);
    option.dataset.unavailable = "true";
    select.add(option);
  }
  select.value = id;
  modelInfo();
}
function modelInfo() {
  const id = $("#model").value === "auto" ? state.defaultModel : $("#model").value;
  const model = state.models.find(item => item.id === id || item.id === id + ":latest");
  $("#model-name").textContent = model?.label || id || "ค่าเริ่มต้นของระบบ";
  $("#model-capabilities").textContent = model?.description || "ยังไม่มีข้อมูลโมเดลนี้ กรุณาตรวจสอบการเชื่อมต่อหรือเลือกโมเดลที่พร้อมใช้งาน";
  $("#model-tags").replaceChildren(...(model?.capabilities || []).map(value => el("span", "tag", value)));
  $("#model-provider").textContent = model ? (model.provider === "ollama" ? "Ollama · ประมวลผลบนเซิร์ฟเวอร์นี้" : "ผู้ให้บริการภายนอก · " + model.provider) : "ยังไม่พร้อมใช้งาน";
}
function applyModelCatalog(data) {
  const previousBuildModel = $("#build-model").value;
  state.models = data.models || [];
  state.providers = data.providers || [];
  state.defaultModel = data.default;
  state.modelsReady = state.models.length > 0;
  $("#model").replaceChildren(new Option("ค่าเริ่มต้น · " + data.default, "auto"), ...state.models.map(model => new Option(model.label, model.id)));
  $("#build-model").replaceChildren(
    new Option("ค่าเริ่มต้น · " + data.default, "auto"),
    ...state.models.map(model => new Option(model.label + (model.id === "deepseek-r1:7b" ? " · แนะนำสำหรับ Build" : ""), model.id)),
  );
  if (state.models.some(model => model.id === previousBuildModel)) $("#build-model").value = previousBuildModel;
  else if (state.models.some(model => model.id === "deepseek-r1:7b")) $("#build-model").value = "deepseek-r1:7b";
  setModelSelection(state.conversation?.model || "auto");
  renderWorkers();
  syncBuild();
  syncComposer();
}
$("#model").addEventListener("change", async () => {
  const value = $("#model").value;
  const previous = state.conversation?.model || "auto";
  modelInfo();
  if (!state.conversation) return syncComposer();
  state.modelSaving = true;
  syncComposer();
  try {
    const updated = await api("/api/conversations/" + state.conversation.id, mutation("PATCH", { model: value }));
    Object.assign(state.conversation, updated);
    const cached = state.conversations.find(item => item.id === updated.id);
    if (cached) Object.assign(cached, updated);
    toast("เปลี่ยนโมเดลสำหรับแชทนี้แล้ว");
  } catch (error) {
    if (error.status === 404) await recoverMissingConversation(state.conversation?.id, composerDraft());
    else { setModelSelection(previous); toast(errorMessage(error), true); }
  }
  finally { state.modelSaving = false; syncComposer(); }
});
function renderMessages() {
  const chat = $("#chat");
  chat.replaceChildren();
  if (!state.messages.length) {
    const empty = el("div", "empty-state");
    const logo = el("span", "empty-logo", "H");
    logo.setAttribute("aria-hidden", "true");
    empty.append(logo, el("h2", "", "เริ่มจากความคิดของคุณ"), el("p", "", "ถาม วางแผน หรือแนบสิ่งที่กำลังทำอยู่\nให้ Chat-BTH ช่วยคิดไปด้วยกัน"));
    if (state.conversation) {
      const suggestions = el("div", "suggestions");
      ["ช่วยวางแผนงานวันนี้", "อธิบายเรื่องยากให้ง่าย", "ช่วยตรวจและปรับปรุงโค้ด"].forEach(text => {
        suggestions.append(button(text, "", () => { $("#message").value = text; resizeInput(); syncComposer(); $("#message").focus(); }));
      });
      empty.append(suggestions);
    } else {
      if (state.project) {
        empty.append(button("เริ่มแชทแรก", "primary", newChat, "plus"));
        empty.append(button("เริ่ม Guided Build ในแชทนี้", "secondary-button", () => startChatGuidedBuild("website_standard.v1"), "code"));
      } else empty.append(button("สร้างโปรเจกต์แรก", "primary", newChat, "plus"));
    }
    chat.append(empty);
  }
  state.messages.forEach(message => chat.append(messageNode(message)));
  if (!state.chatGuidedConversation && state.conversation && state.messages.length) {
    const launch = el("div", "chat-guided-launch");
    launch.append(el("span", "", "ต้องการสร้างเว็บไซต์แบบคุยทีละเรื่องไหม?"), button("เริ่ม Guided Build", "secondary-button", () => startChatGuidedBuild("website_standard.v1"), "code"));
    chat.append(launch);
  }
  requestAnimationFrame(() => chat.scrollTop = chat.scrollHeight);
}

function guidedChatKey() { return state.project ? "hermes-guided-chat:" + state.project.id : null; }
function saveChatGuided() {
  const key = guidedChatKey();
  if (!key) return;
  try { if (state.chatGuidedConversation) localStorage.setItem(key, JSON.stringify(state.chatGuidedConversation)); else localStorage.removeItem(key); } catch { /* best effort */ }
}
function loadChatGuided() {
  const key = guidedChatKey();
  state.chatGuidedConversation = null;
  if (!key) return;
  try { const value = JSON.parse(localStorage.getItem(key) || "null"); if (value?.schema === "hermes.guided-conversation/v1") state.chatGuidedConversation = value; } catch { /* ignore stale local state */ }
  if (state.chatGuidedConversation) $("#message").placeholder = "ตอบคำถามของ Hermes ได้ที่นี่";
}
function guidedAssistantText(conversation) {
  if (conversation.status === "review") {
    const summary = conversation.summary.map(item => `• ${item.label}: ${guidedValueLabel(item.value)}`).join("\n");
    return `Hermes Guided Build\n\nสรุปข้อมูลที่ได้:\n${summary}\n\nหากถูกต้อง พิมพ์ “ยืนยัน” เพื่อสร้างเว็บไซต์ หากต้องการแก้ไข พิมพ์ “แก้ <ชื่อข้อมูล>” เช่น “แก้ tabs”`;
  }
  const q = conversation.question;
  if (!q) return "Hermes Guided Build กำลังเตรียมคำถามถัดไป";
  const hints = {
    blueprint_id: "อธิบายความต้องการได้ตามปกติ Hermes จะเลือกโครงสร้างที่เหมาะสมให้",
    tabs: "พิมพ์เป็นรายการคั่นด้วยเครื่องหมายจุลภาค เช่น หน้าหลัก, เกี่ยวกับเรา, ติดต่อ",
    color_tone: "บอกอารมณ์ที่อยากได้ เช่น น่าเชื่อถือ อบอุ่น ธรรมชาติ หรือเรียบง่าย",
    network_scope: "ตอบว่า ใช้ภายในองค์กร, ให้คนทั่วไปเข้าถึง หรือทั้งสองแบบ",
    auth_enabled: "ตอบ ใช่ หรือ ไม่",
    density: "ตอบว่า กะทัดรัด หรือ โปร่งอ่านง่าย",
    language: "ตอบว่า ไทย, อังกฤษ หรือ ไทยและอังกฤษ",
  };
  const hint = hints[q.field_id] || (q.kind === "boolean" ? "ตอบ ใช่ หรือ ไม่" : "");
  return `Hermes Guided Build\n\n${q.prompt}\nเหตุผล: ${q.reason}${hint ? `\n${hint}` : ""}${conversation.clarification ? `\n\n${conversation.clarification}` : ""}`;
}
async function appendGuidedTranscript(role, content) {
  const result = await api(`/api/conversations/${encodeURIComponent(state.conversation.id)}/guided-transcript`, mutation("POST", { role, content }));
  state.messages.push(result.message);
  return result.message;
}
function chatGuidedCard(conversation) {
  const card = el("section", "chat-guided-card");
  const heading = el("div", "chat-guided-heading");
  heading.append(el("strong", "", "Hermes Guided Build"), el("span", "", conversation.status === "review" ? "ตรวจสรุปก่อนสร้าง" : conversation.status === "confirmed" ? "สร้างไฟล์ในโปรเจกต์แล้ว" : "ถามทีละเรื่อง"));
  card.append(heading);
  if (conversation.status === "confirmed") { card.append(el("p", "", "เว็บไซต์ถูกสร้างไว้ในโปรเจกต์นี้แล้ว เปิดแท็บ Build เพื่อดูไฟล์และ Preview")); return card; }
  if (conversation.status === "review") {
    card.append(el("p", "", "สรุปข้อมูลที่ได้จากการสนทนา:"));
    const summary = el("div", "chat-guided-summary");
    conversation.summary.forEach(item => { const row = el("div", "guided-summary-row"); row.append(el("span", "", `${item.label}: ${guidedValueLabel(item.value)}`), button("แก้", "text-button", () => reviseChatGuided(item.field_id))); summary.append(row); });
    card.append(summary, button("ยืนยันและสร้างเว็บในโปรเจกต์นี้", "primary", confirmChatGuidedBuild), button("เริ่ม Guided Build ใหม่", "text-button", () => startChatGuidedBuild("website_standard.v1")));
    return card;
  }
  const q = conversation.question;
  if (!q) return card;
  card.append(el("p", "chat-guided-topic", q.topic), el("p", "", q.prompt), el("small", "", "เหตุผล: " + q.reason));
  const answer = el("div", "chat-guided-answer");
  if (q.kind === "select") {
    const select = el("select"); select.id = "chat-guided-value";
    q.options.forEach(value => { const option = el("option", "", value); option.value = value; option.selected = value === q.suggested; select.append(option); }); answer.append(select);
  } else if (q.kind === "multi_select") {
    const options = el("div", "guided-options");
    q.options.forEach(value => { const label = el("label"); const input = document.createElement("input"); input.type = "checkbox"; input.value = value; input.checked = Array.isArray(q.suggested) && q.suggested.includes(value); label.append(input, el("span", "", value)); options.append(label); }); answer.append(options);
    if (!q.options.length) { const custom = el("input"); custom.type = "text"; custom.id = "chat-guided-custom"; custom.value = Array.isArray(q.suggested) ? q.suggested.join(", ") : ""; custom.placeholder = "พิมพ์รายการคั่นด้วย ,"; answer.append(custom); }
  } else if (q.kind === "boolean") {
    const label = el("label"); const input = document.createElement("input"); input.type = "checkbox"; input.id = "chat-guided-value"; input.checked = q.suggested === true; label.append(input, el("span", "", "ใช่")); answer.append(label);
  } else { const input = el("input"); input.type = "text"; input.id = "chat-guided-value"; input.value = typeof q.suggested === "string" ? q.suggested : ""; input.placeholder = "พิมพ์คำตอบ"; answer.append(input); }
  answer.append(button("ตอบ", "primary", answerChatGuided)); card.append(answer);
  if (conversation.clarification) card.append(el("p", "form-error", conversation.clarification));
  return card;
}
async function startChatGuidedBuild(formId) {
  if (!state.project || state.busy || state.buildBusy) return;
  try {
    state.busy = true; syncComposer();
    if (!state.conversation) {
      const conversation = await api(`/api/projects/${encodeURIComponent(state.project.id)}/conversations`, mutation("POST", { title: "Guided Build", model: $("#model").value }));
      state.conversations.unshift(conversation);
      applyConversation({ conversation, messages: [] });
    }
    state.chatGuidedConversation = await api(`/api/projects/${encodeURIComponent(state.project.id)}/bth-create/conversation/start`, { ...mutation("POST", { form_id: formId, initial_values: { project_name: state.project.name } }) });
    saveChatGuided(); $("#message").placeholder = "ตอบคำถามของ Hermes ได้ที่นี่"; await appendGuidedTranscript("assistant", guidedAssistantText(state.chatGuidedConversation)); renderMessages();
  } catch (error) { toast(errorMessage(error), true); }
  finally { state.busy = false; syncComposer(); }
}
function guidedRevisionField(text, conversation) {
  const lowered = text.trim().toLowerCase();
  if (!/^แก้|^เปลี่ยน|^ปรับ/.test(lowered)) return null;
  const names = {
    project_name: ["ชื่อ", "project_name"], blueprint_id: ["เป้าหมาย", "blueprint", "รูปแบบ"], tabs: ["หน้า", "เมนู", "tabs"],
    color_tone: ["สี", "โทน", "color"], network_scope: ["การเข้าถึง", "network"], auth_enabled: ["เข้าสู่ระบบ", "auth"],
    density: ["ความหนาแน่น", "layout"], language: ["ภาษา", "language"],
  };
  return Object.entries(names).find(([, terms]) => terms.some(term => lowered.includes(term)))?.[0]
    || conversation.summary.find(item => lowered.includes(item.field_id.toLowerCase()) || lowered.includes(item.label.toLowerCase()))?.field_id
    || null;
}
async function submitChatGuidedComposer() {
  const conversation = state.chatGuidedConversation;
  const message = requestText();
  if (!conversation || !message || state.files.length) {
    if (state.files.length) composerError("Guided Build รับคำตอบเป็นข้อความ בלבד");
    return;
  }
  const id = state.conversation.id;
  try {
    state.busy = true; syncComposer(); composerError();
    await appendGuidedTranscript("user", message);
    if (conversation.status === "collecting") {
      state.chatGuidedConversation = await api(`/api/projects/${encodeURIComponent(state.project.id)}/bth-create/conversation/answer-text`, { ...mutation("POST", { conversation, text: message }) });
      saveChatGuided();
      await appendGuidedTranscript("assistant", guidedAssistantText(state.chatGuidedConversation));
    } else if (conversation.status === "review" && /^(ยืนยัน|ตกลง|สร้างเว็บ|สร้างเว็บไซต์|confirm)$/i.test(message.trim())) {
      const confirmed = await api(`/api/projects/${encodeURIComponent(state.project.id)}/bth-create/conversation/confirm`, { ...mutation("POST", { conversation }) });
      await appendGuidedTranscript("assistant", "ข้อมูลครบแล้ว กำลังสร้างเว็บไซต์ในโปรเจกต์นี้ครับ");
      const result = await api(`/api/projects/${encodeURIComponent(state.project.id)}/bth-create/build`, { ...mutation("POST", { values: confirmed.values }), timeout: 180000 });
      state.buildPreviewUrl = result.preview_url;
      state.chatGuidedConversation = null; saveChatGuided(); $("#message").placeholder = "วันนี้อยากทำอะไรให้สำเร็จ?";
      await appendGuidedTranscript("assistant", "สร้างเว็บไซต์เสร็จแล้ว ไฟล์และ Preview อยู่ในแท็บ Build ครับ");
      await loadBuildFiles(); if (result.preview_url) showBuildPreview(result.preview_url);
    } else if (conversation.status === "review") {
      const fieldId = guidedRevisionField(message, conversation);
      if (!fieldId) await appendGuidedTranscript("assistant", "หากข้อมูลถูกต้อง พิมพ์ “ยืนยัน” เพื่อสร้างเว็บไซต์ หรือพิมพ์ “แก้ <ชื่อข้อมูล>” เช่น “แก้ หน้า” ครับ");
      else {
        state.chatGuidedConversation = await api(`/api/projects/${encodeURIComponent(state.project.id)}/bth-create/conversation/revise`, { ...mutation("POST", { conversation, field_id: fieldId }) });
        saveChatGuided(); await appendGuidedTranscript("assistant", guidedAssistantText(state.chatGuidedConversation));
      }
    }
    $("#message").value = ""; state.drafts.delete(id); renderMessages();
  } catch (error) {
    composerError(errorMessage(error));
  } finally {
    state.busy = false; syncComposer(); resizeInput();
    if (state.view === "chat" && !drawer) $("#message").focus();
  }
}
async function answerChatGuided() {
  const conversation = state.chatGuidedConversation; const q = conversation?.question;
  if (!q || state.busy) return;
  let value;
  if (q.kind === "multi_select") {
    value = $$("input[type=checkbox]", $(".chat-guided-answer")).map(input => input.checked ? input.value : null).filter(Boolean);
    const custom = $("#chat-guided-custom")?.value.trim(); if (custom) value.push(...custom.split(",").map(item => item.trim()).filter(Boolean));
  } else if (q.kind === "boolean") value = $("#chat-guided-value").checked;
  else value = $("#chat-guided-value").value;
  try {
    state.busy = true; syncComposer();
    state.chatGuidedConversation = await api(`/api/projects/${encodeURIComponent(state.project.id)}/bth-create/conversation/answer`, { ...mutation("POST", { conversation, answer: { field_id: q.field_id, value } }) });
    saveChatGuided(); renderMessages();
  } catch (error) { toast(errorMessage(error), true); }
  finally { state.busy = false; syncComposer(); }
}
async function reviseChatGuided(fieldId) {
  if (!state.project || !state.chatGuidedConversation || state.busy) return;
  try {
    state.busy = true; syncComposer();
    state.chatGuidedConversation = await api(`/api/projects/${encodeURIComponent(state.project.id)}/bth-create/conversation/revise`, { ...mutation("POST", { conversation: state.chatGuidedConversation, field_id: fieldId }) });
    saveChatGuided(); renderMessages();
  } catch (error) { toast(errorMessage(error), true); }
  finally { state.busy = false; syncComposer(); }
}
async function confirmChatGuidedBuild() {
  if (!state.chatGuidedConversation || state.busy) return;
  try {
    state.busy = true; syncComposer();
    const confirmed = await api(`/api/projects/${encodeURIComponent(state.project.id)}/bth-create/conversation/confirm`, { ...mutation("POST", { conversation: state.chatGuidedConversation }) });
    const result = await api(`/api/projects/${encodeURIComponent(state.project.id)}/bth-create/build`, { ...mutation("POST", { values: confirmed.values }), timeout: 180000 });
    state.chatGuidedConversation = { ...confirmed, status: "confirmed" }; saveChatGuided();
    state.buildPreviewUrl = result.preview_url; renderMessages(); await loadBuildFiles();
    toast("สร้างเว็บไซต์และบันทึกไฟล์ลงในโปรเจกต์แล้ว");
    if (result.preview_url) showBuildPreview(result.preview_url);
  } catch (error) { toast(errorMessage(error), true); }
  finally { state.busy = false; syncComposer(); }
}
function messageNode(message) {
  const node = el("article", "message " + (message.role === "user" ? "user" : "assistant") + (message.pending ? " pending" : ""));
  const label = el("div", "message-label");
  if (message.role !== "user") label.append(icon("chat"));
  label.append(document.createTextNode(message.role === "user" ? "คุณ" : ("Chat-BTH" + (message.model ? " · " + message.model : ""))));
  if (message.used_web) label.append(el("span", "tag", "ใช้ข้อมูลเว็บ"));
  node.append(label);
  // Text is intentionally not interpreted as HTML, including model output and files.
  const content = message.content || "";
  const marker = content.indexOf("\n\n[ไฟล์แนบ: ");
  if (message.role === "user" && marker >= 0) {
    node.append(el("div", "message-content", content.slice(0, marker)));
    const details = el("details");
    details.append(el("summary", "", "ดูเนื้อหาไฟล์แนบ"), el("pre", "", content.slice(marker).trim()));
    node.append(details);
  } else node.append(el("div", "message-content", content));
  if (message.role === "assistant" && !message.pending) {
    const actions = el("div", "message-actions");
    actions.append(button("คัดลอก", "", async () => {
      try { await navigator.clipboard.writeText(content); toast("คัดลอกคำตอบแล้ว"); }
      catch { toast("เบราว์เซอร์ไม่อนุญาตให้คัดลอก กรุณาเลือกข้อความแล้วคัดลอก", true); }
    }, "copy"));
    const speak = button("ฟังคำตอบ", "", async () => {
      if (!await confirmAction("Create Voice ?", "สร้างเสียงด้วย Local TTS บนเครื่อง โดยไม่มีการส่งข้อความออกอินเทอร์เน็ตหรือไม่?", "สร้างเสียง", { centered: true })) return;
      speak.disabled = true;
      try {
        const audio = el("audio");
        const audioBlob = await api("/api/audio", { ...mutation("POST", { text: content, language: "th" }), blob: true, timeout: 60000 });
        const url = URL.createObjectURL(audioBlob);
        audio.src = url; audio.controls = true;
        audio.addEventListener("ended", () => audio.pause());
        actions.append(audio);
        speak.remove();
        audio.addEventListener("loadeddata", () => URL.revokeObjectURL(url), { once: true });
        await audio.play().catch(() => {});
      } catch (error) { toast(errorMessage(error), true); speak.disabled = false; }
    }, "audio");
    actions.append(speak);
    node.append(actions);
  }
  return node;
}
function renderAttachments() {
  $("#attachment-list").replaceChildren(...state.files.map((file, index) => {
    const chip = el("div", "attachment-chip");
    const remove = iconButton("นำไฟล์ " + file.name + " ออก", "close", () => {
      if (locked()) return;
      state.files.splice(index, 1); renderAttachments(); syncComposer(); composerError();
    });
    remove.disabled = state.busy || state.reading;
    chip.append(icon("file"), el("span", "", file.name + " · " + file.content.length.toLocaleString() + " อักษร"), remove);
    return chip;
  }));
}
$("#file-input").addEventListener("change", async event => {
  const selected = [...event.target.files];
  event.target.value = "";
  if (locked() || !selected.length) return;
  state.reading = true; syncComposer(); composerError();
  try {
    const next = [...state.files];
    for (const file of selected) {
      if (next.some(existing => existing.name === file.name)) throw new Error("มีไฟล์ชื่อนี้แล้ว: " + file.name);
      if (next.length >= 5) throw new Error("แนบได้ไม่เกิน 5 ไฟล์ต่อข้อความ");
      if (!/\.(txt|md|csv|json|py|js|ts|html|css|log)$/i.test(file.name)) throw new Error("รองรับไฟล์ข้อความ: TXT, MD, CSV, JSON และไฟล์โค้ด ไม่รองรับ PDF หรือรูปภาพ");
      if (file.size > 500000) throw new Error("ไฟล์ " + file.name + " มีขนาดเกิน 500 KB");
      if (file.name.length > 255 || /[\r\n]/.test(file.name)) throw new Error("ชื่อไฟล์ยาวเกินไปหรือมีอักขระที่ไม่รองรับ");
      let content;
      try { content = new TextDecoder("utf-8", { fatal: true }).decode(await file.arrayBuffer()); }
      catch { throw new Error("กรุณาบันทึกไฟล์ " + file.name + " ด้วยรหัสอักขระ UTF-8"); }
      if (content.includes("\u0000")) throw new Error("ไฟล์ " + file.name + " ไม่ใช่ไฟล์ข้อความ");
      next.push({ name: file.name, content });
    }
    if (fullMessage($("#message").value.trim() || "ช่วยวิเคราะห์ไฟล์แนบนี้", next).length > 12000) throw new Error("ข้อความและไฟล์แนบรวมกันเกิน 12,000 ตัวอักษร กรุณาลดขนาดเนื้อหา ไม่มีการตัดไฟล์อัตโนมัติ");
    state.files = next;
  } catch (error) { composerError(errorMessage(error)); }
  finally { state.reading = false; renderAttachments(); syncComposer(); }
});
$("#composer").addEventListener("submit", async event => {
  event.preventDefault();
  if ($("#send").disabled || locked()) return;
  if (state.chatGuidedConversation) {
    await submitChatGuidedComposer();
    return;
  }
  const id = state.conversation.id;
  const model = $("#model").value;
  const message = requestText();
  const files = state.files.map(file => ({ ...file }));
  state.busy = true; syncComposer(); renderAttachments(); composerError();
  const chat = $("#chat");
  $(".empty-state", chat)?.remove();
  const userNode = messageNode({ role: "user", content: fullMessage(message, files) });
  const pending = messageNode({ role: "assistant", content: "กำลังเรียบเรียงคำตอบ…", pending: true });
  chat.append(userNode, pending);
  chat.scrollTop = chat.scrollHeight;
  try {
    const result = await api("/api/conversations/" + id + "/messages", {
      ...mutation("POST", { message, model, search_web: $("#search").checked, attachments: files }), timeout: 360000,
    });
    state.messages.push({ role: "user", content: fullMessage(message, files) }, { role: "assistant", content: result.reply, model: result.model, used_web: result.used_web });
    pending.replaceWith(messageNode(state.messages.at(-1)));
    $("#message").value = ""; state.files = []; state.drafts.delete(id);
    if (state.conversation.title === "แชทใหม่") state.conversation.title = message.slice(0, 60);
    const cached = state.conversations.find(item => item.id === id);
    if (cached) Object.assign(cached, state.conversation);
    renderProjects(); setHeading();
    chat.scrollTop = chat.scrollHeight;
  } catch (error) {
    userNode.remove(); pending.remove();
    if (!state.messages.length) renderMessages();
    if (error.status === 404) await recoverMissingConversation(id, { text: $("#message").value, files, search: $("#search").checked });
    else {
      composerError(errorMessage(error));
      saveDraft();
    }
  } finally {
    state.busy = false; renderAttachments(); syncComposer(); resizeInput();
    if (state.view === "chat" && !drawer) $("#message").focus();
  }
});
$("#message").addEventListener("input", () => { composerError(); resizeInput(); syncComposer(); });
$("#message").addEventListener("keydown", event => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing && !matchMedia("(pointer: coarse)").matches) {
    event.preventDefault(); $("#composer").requestSubmit();
  }
});
$("#attach-file").addEventListener("click", () => $("#file-input").click());

// Native dialogs provide focus containment; destructive changes require confirmation.
function confirmAction(title, message, action = "ยืนยัน", { centered = false } = {}) {
  const dialog = $("#confirm-dialog");
  if (dialog.open) return Promise.resolve(false);
  dialog.classList.toggle("centered-confirm", centered);
  $("#confirm-title").textContent = title; $("#confirm-message").textContent = message; $("#confirm-action").textContent = action;
  dialog.returnValue = "";
  dialog.showModal();
  $("button[value=cancel]", dialog).focus();
  return new Promise(resolve => dialog.addEventListener("close", () => resolve(dialog.returnValue === "confirm"), { once: true }));
}
async function closeDialog(dialog) {
  if ($("form", dialog)?.dataset.saving) return;
  if (dialog.id === "notebook-dialog" && notebookDirty() && !await confirmAction("ละทิ้งการแก้ไข?", "เนื้อหาที่ยังไม่บันทึกจะหายไป", "ละทิ้ง")) return;
  dialog.close();
}
$$("dialog:not(#confirm-dialog)").forEach(dialog => {
  $$("[data-close]", dialog).forEach(node => node.addEventListener("click", () => closeDialog(dialog)));
  dialog.addEventListener("cancel", event => { event.preventDefault(); closeDialog(dialog); });
});
function readStore(key, validator) {
  let value;
  try { value = JSON.parse(localStorage.getItem(key) || "[]"); }
  catch { throw new Error("อ่านข้อมูลในเบราว์เซอร์ไม่ได้ ข้อมูลเดิมยังไม่ถูกเปลี่ยน"); }
  if (!Array.isArray(value) || !value.every(validator)) throw new Error("รูปแบบข้อมูลเดิมไม่ถูกต้อง จึงระงับการบันทึกเพื่อป้องกันข้อมูลสูญหาย");
  return value;
}
function saveStore(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); }
  catch { throw new Error("บันทึกไม่ได้ พื้นที่เบราว์เซอร์อาจเต็ม กรุณาส่งออกหรือคัดลอกเนื้อหาไว้"); }
}
const getNotebooks = () => readStore("hermes-notebooks", item => item && (typeof item.id === "string" || typeof item.id === "number") && typeof item.title === "string" && typeof item.content === "string");
function renderNotebooks() {
  const grid = $("#notebook-grid"), list = $("#notebook-list");
  grid.replaceChildren(); list.replaceChildren();
  try {
    const notes = getNotebooks();
    const query = $("#notebook-filter").value.trim().toLocaleLowerCase();
    const filtered = notes.filter(note => (note.title + " " + note.content).toLocaleLowerCase().includes(query));
    $("#notebook-count").textContent = filtered.length + " บันทึก";
    notes.forEach(note => list.append(button(note.title, "project-item", () => openNotebook(note), "book")));
    if (!notes.length) list.append(el("p", "side-note", "เรื่องราวดี ๆ เริ่มจากบันทึกแรก"));
    filtered.forEach(note => {
      const card = button("", "notebook-card", () => openNotebook(note));
      card.replaceChildren();
      const top = el("div", "card-top"), symbol = el("span", "card-icon");
      symbol.append(icon("book")); top.append(symbol, icon("edit"));
      card.append(top, el("h3", "", note.title), el("p", "", note.content || "ยังไม่มีเนื้อหา"), el("span", "card-footer", "แก้ไขล่าสุด · " + formatDate(note.updated)));
      grid.append(card);
    });
    if (!filtered.length) {
      const empty = el("div", "empty-state");
      empty.append(el("h2", "", query ? "ไม่พบบันทึกที่ตรงกัน" : "พื้นที่สำหรับสิ่งที่คุณเรียนรู้"), el("p", "", query ? "ลองค้นด้วยชื่อหรือคำในเนื้อหา" : "เพิ่มบันทึกแรก เพื่อเก็บไอเดียและงานที่ผ่านมา"));
      grid.append(empty);
    }
  } catch (error) { grid.append(el("p", "inline-error", errorMessage(error))); $("#notebook-count").textContent = ""; }
}
let editingNotebook = null, notebookOriginal = "", notebookRevision = null;
const notebookValue = () => JSON.stringify([$("#notebook-title-input").value, $("#notebook-content-input").value]);
const notebookDirty = () => notebookValue() !== notebookOriginal;
function openNotebook(note = null) {
  closeDrawer();
  editingNotebook = note?.id ?? null;
  notebookRevision = note ? JSON.stringify(note) : null;
  $("#notebook-dialog-title").textContent = note ? "แก้ไข Notebook" : "เพิ่ม Notebook";
  $("#notebook-title-input").value = note?.title || "";
  $("#notebook-content-input").value = note?.content || "";
  $("#delete-notebook").hidden = !note;
  $("#export-notebook").hidden = false;
  notebookOriginal = notebookValue();
  formError($("#notebook-form"));
  $("#notebook-dialog").showModal();
  $("#notebook-title-input").focus();
}
$("#notebook-form").addEventListener("submit", event => {
  event.preventDefault();
  const title = $("#notebook-title-input").value.trim();
  if (!title) return formError(event.currentTarget, "กรุณาระบุชื่อ Notebook");
  try {
    const notes = getNotebooks();
    const record = { id: editingNotebook ?? crypto.randomUUID(), title, content: $("#notebook-content-input").value, updated: new Date().toISOString() };
    const index = notes.findIndex(note => note.id === editingNotebook);
    if (editingNotebook !== null && (index < 0 || JSON.stringify(notes[index]) !== notebookRevision)) {
      throw new Error("บันทึกนี้ถูกเปลี่ยนในอีกแท็บ กรุณาส่งออกเนื้อหาปัจจุบันก่อน แล้วเปิดบันทึกใหม่เพื่อป้องกันการเขียนทับ");
    }
    if (index >= 0) notes[index] = { ...notes[index], ...record }; else notes.unshift(record);
    saveStore("hermes-notebooks", notes);
    $("#notebook-dialog").close(); renderNotebooks(); toast("บันทึก Notebook แล้ว");
  } catch (error) { formError(event.currentTarget, errorMessage(error)); }
});
$("#export-notebook").addEventListener("click", () => {
  const title = $("#notebook-title-input").value.trim() || "Notebook";
  const blob = new Blob([title + "\n\n" + $("#notebook-content-input").value], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob), link = el("a");
  link.href = url; link.download = title.replace(/[\\/:*?"<>|]/g, "-").slice(0, 100) + ".txt";
  link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
});
$("#delete-notebook").addEventListener("click", async () => {
  if (!await confirmAction("ลบ Notebook?", "บันทึกนี้จะถูกลบจากเบราว์เซอร์ ส่งออกไฟล์ก่อนลบหากต้องการเก็บไว้", "ลบบันทึก")) return;
  try {
    saveStore("hermes-notebooks", getNotebooks().filter(note => note.id !== editingNotebook));
    $("#notebook-dialog").close(); renderNotebooks(); toast("ลบบันทึกแล้ว");
  } catch (error) { formError($("#notebook-form"), errorMessage(error)); }
});
$("#notebook-filter").addEventListener("input", renderNotebooks);
window.addEventListener("storage", event => {
  if (event.key === "hermes-notebooks") renderNotebooks();
  if (event.key === "hermes-workers") renderWorkers();
});
const getWorkers = () => readStore("hermes-workers", item => item && typeof item.name === "string" && typeof item.host === "string");
function renderWorkers() {
  const grid = $("#worker-grid"); grid.replaceChildren();
  const online = !!state.health?.ok;
  const local = el("article", "worker-card"), top = el("div", "card-top");
  top.append(icon("server"), el("span", "worker-status" + (online ? " online" : ""), state.health === null ? "กำลังตรวจสอบ" : (online ? "Online" : "ไม่พร้อมใช้งาน")));
  local.append(top, el("h3", "", "เซิร์ฟเวอร์นี้"), el("p", "worker-meta", location.hostname + "\n" + (online ? "Ollama เชื่อมต่อแล้ว · " + state.health.models.length + " โมเดล" : "ยังยืนยันการเชื่อมต่อ Ollama ไม่ได้")));
  grid.append(local);
  state.providers.filter(provider => provider.id !== "ollama").forEach(provider => {
    const card = el("article", "worker-card"), heading = el("div", "card-top");
    heading.append(icon("key"), el("span", "worker-status" + (provider.has_key ? " online" : ""), provider.has_key ? "พร้อมใช้" : "ไม่มี API key"));
    const providerLabel = provider.type === "google-ai-studio" ? "Gemini native API" : "OpenAI-compatible API";
    const details = el("p", "worker-meta", providerLabel + "\n" + (provider.models || []).join(", "));
    card.append(heading, el("h3", "", provider.name), details);
    if (provider.source === "runtime") {
      card.append(button("ลบและล้าง API key", "text-button worker-remove", async () => {
        if (!await confirmAction("ลบ API นี้?", "API key จะถูกล้างออกจากหน่วยความจำของเซิร์ฟเวอร์ และโมเดลของ API นี้จะหายจากรายการเลือก", "ลบ API")) return;
        try {
          await api("/api/providers/" + encodeURIComponent(provider.id), { method: "DELETE" });
          const data = await api("/api/models");
          applyModelCatalog(data);
          toast("ลบ API และล้างคีย์แล้ว");
        } catch (error) { toast(errorMessage(error), true); }
      }));
    }
    grid.append(card);
  });
  try {
    getWorkers().forEach((worker, index) => {
      if (worker.name === "เครื่องนี้" && worker.host === "localhost") return; // Old synthetic row; the live server replaces it.
      const card = el("article", "worker-card"), heading = el("div", "card-top");
      heading.append(icon("server"), el("span", "worker-status", "ยังไม่ตรวจสอบ"));
      card.append(heading, el("h3", "", worker.name), el("p", "worker-meta", worker.host + "\nบันทึกรายชื่อแล้ว · ยังไม่เชื่อมต่อ"),
        button("นำออกจากรายการ", "text-button worker-remove", async () => {
          if (!await confirmAction("นำเครื่องออก?", "ลบเฉพาะรายชื่อที่บันทึกไว้ ไม่เปลี่ยนแปลงเครื่องปลายทาง", "นำออก")) return;
          try {
            const workers = getWorkers();
            if (workers[index]?.host !== worker.host) throw new Error("รายการเปลี่ยนไปแล้ว กรุณาลองใหม่");
            workers.splice(index, 1); saveStore("hermes-workers", workers); renderWorkers(); toast("นำเครื่องออกจากรายการแล้ว");
          } catch (error) { toast(errorMessage(error), true); }
        }));
      grid.append(card);
    });
  } catch (error) { grid.append(el("p", "inline-error", errorMessage(error))); }
}
$("#worker-form").addEventListener("submit", event => {
  event.preventDefault();
  const name = $("#worker-name-input").value.trim(), host = $("#worker-host-input").value.trim().toLowerCase();
  const validHost = /^(?=.{1,253}$)[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$/.test(host) && host.split(".").every(part => part.length > 0 && part.length <= 63 && !part.startsWith("-") && !part.endsWith("-"));
  const validIP = /^\d+\.\d+\.\d+\.\d+$/.test(host) && host.split(".").every(part => Number(part) <= 255);
  if (!name || !validHost || (/^[\d.]+$/.test(host) && !validIP)) return formError(event.currentTarget, "ระบุชื่อเครื่องและโฮสต์ เช่น gpu-worker.local หรือ 192.168.1.10 โดยไม่ใส่ http:// หรือพอร์ต");
  try {
    const workers = getWorkers();
    if (workers.some(worker => worker.host.toLowerCase() === host)) throw new Error("มีเครื่องที่ใช้โฮสต์นี้อยู่แล้ว");
    workers.push({ id: crypto.randomUUID(), name, host, status: "pending" });
    saveStore("hermes-workers", workers);
    $("#worker-dialog").close(); renderWorkers(); toast("บันทึกรายชื่อเครื่องแล้ว ยังไม่ได้เชื่อมต่อ");
  } catch (error) { formError(event.currentTarget, errorMessage(error)); }
});
function syncApiProviderPreset() {
  const google = $("#api-provider-kind").value === "google";
  const name = $("#api-provider-name"), url = $("#api-provider-url"), models = $("#api-provider-models");
  if (google) {
    name.value = "Google AI Studio";
    url.value = "https://generativelanguage.googleapis.com/v1beta/openai";
    url.readOnly = true;
    if (!models.value || models.dataset.preset === "true") models.value = "gemini-3.8-flash";
    models.dataset.preset = "true";
    $("#api-provider-url-help").textContent = "ใช้ Gemini native generateContent API อัตโนมัติ";
  } else {
    if (name.value === "Google AI Studio") name.value = "";
    url.value = "";
    url.readOnly = false;
    if (models.dataset.preset === "true") models.value = "";
    delete models.dataset.preset;
    $("#api-provider-url-help").textContent = "ต้องเป็น HTTPS และลงท้ายก่อน /chat/completions";
  }
}
$("#api-provider-kind").addEventListener("change", syncApiProviderPreset);
$("#api-provider-models").addEventListener("input", () => { delete $("#api-provider-models").dataset.preset; });
$("#api-provider-form").addEventListener("submit", async event => {
  event.preventDefault();
  const form = event.currentTarget;
  if (form.dataset.saving) return;
  const models = $("#api-provider-models").value.split(",").map(value => value.trim()).filter(Boolean);
  if (!models.length) return formError(form, "กรุณาระบุชื่อโมเดลอย่างน้อย 1 รายการ");
  form.dataset.saving = "true";
  $$('button', form).forEach(node => node.disabled = true);
  try {
    const provider = await api("/api/providers", mutation("POST", {
      name: $("#api-provider-name").value.trim(),
      base_url: $("#api-provider-url").value.trim(),
      api_key: $("#api-provider-key").value,
      models,
      provider_type: $("#api-provider-kind").value,
    }));
    $("#api-provider-key").value = "";
    const data = await api("/api/models");
    applyModelCatalog(data);
    const buildModelId = provider.id + ":" + models[0];
    if (data.models.some(model => model.id === buildModelId)) $("#build-model").value = buildModelId;
    $("#api-provider-dialog").close();
    toast("เชื่อมต่อ API แล้ว และเลือกโมเดลนี้ให้ Build Assistant");
  } catch (error) { formError(form, errorMessage(error)); }
  finally { delete form.dataset.saving; $$('button', form).forEach(node => node.disabled = false); }
});

function addCreateTab(value = "หน้าใหม่", pageType = "standard") {
  if ($$(".create-tab-row").length >= 12) return;
  const row = el("div", "create-tab-row");
  const input = el("input", "create-tab-name");
  input.maxLength = 60;
  input.value = value;
  input.setAttribute("aria-label", "ชื่อหน้า");
  const remove = button("ลบ", "text-button remove-create-tab");
  row.append(input, createPageTypeSelect(pageType), remove);
  $("#create-tab-list").append(row);
  state.createSpec = null;
  syncGuidedBuild();
  input.focus();
}
$("#toggle-guided-build").addEventListener("click", () => {
  state.guidedBuild = !state.guidedBuild;
  if (!state.guidedBuild) { state.guidedConversation = null; state.guidedPayload = null; }
  syncGuidedBuild();
  if (state.guidedBuild) $("#create-project-name").focus();
});
$("#guided-start").addEventListener("click", startGuidedConversation);
$("#bth-create-form").addEventListener("change", event => {
  state.createSpec = null;
  if (event?.target?.closest?.(".create-form-grid, .create-options, .create-tab-list")) state.guidedPayload = null;
  syncGuidedBuild();
});
$("#bth-create-form").addEventListener("input", () => { state.createSpec = null; state.guidedPayload = null; });
$("#create-blueprint").addEventListener("change", () => {
  state.guidedConversation = null; state.guidedPayload = null;
  const blueprintId = $("#create-blueprint").value;
  const website = isWebsiteBlueprint(blueprintId);
  const blueprintDefaults = {
    "website.corporate.v1": [["หน้าหลัก", "home"], ["เกี่ยวกับบริษัท", "about"], ["บริการ", "service"], ["นโยบาย", "policy"], ["ข่าวสาร", "news"], ["ติดต่อ", "contact"]],
    "website.organization.v1": [["หน้าหลัก", "home"], ["เกี่ยวกับองค์กร", "about"], ["นโยบาย", "policy"], ["กฎระเบียบ", "document_library"], ["คลังความรู้", "knowledge_library"], ["ติดต่อ", "contact"]],
    "website.retail.v1": [["หน้าร้าน", "home"], ["สินค้า", "product_catalog"], ["โปรโมชั่น", "news"], ["เกี่ยวกับร้าน", "about"], ["ติดต่อ", "contact"]],
    "website.services.v1": [["หน้าหลัก", "home"], ["บริการ", "service"], ["ขั้นตอนทำงาน", "standard"], ["ผลงานและบทความ", "news"], ["เกี่ยวกับเรา", "about"], ["ติดต่อ", "contact"]],
    "website.knowledge.v1": [["หน้าหลัก", "home"], ["นโยบาย", "policy"], ["กฎระเบียบ", "document_library"], ["คลังความรู้", "knowledge_library"], ["ข่าวสาร", "news"], ["เกี่ยวกับ", "about"]],
    "catalog.library.v1": [["หนังสือทั้งหมด", "knowledge_library"], ["วรรณกรรม", "knowledge_library"], ["ธุรกิจ", "knowledge_library"], ["เทคโนโลยี", "knowledge_library"]],
    "catalog.documents.v1": [["เอกสารทั้งหมด", "document_library"], ["นโยบาย", "policy"], ["คู่มือ", "document_library"], ["รายงาน", "document_library"]],
    "catalog.products.v1": [["ทั้งหมด", "product_catalog"], ["สินค้า", "product_catalog"], ["บริการ", "service"], ["เอกสารดาวน์โหลด", "document_library"]],
    "catalog.media.v1": [["สื่อทั้งหมด", "standard"], ["ภาพ", "standard"], ["วิดีโอ", "standard"], ["สิ่งพิมพ์", "document_library"]],
    "catalog.learning.v1": [["บทเรียนทั้งหมด", "knowledge_library"], ["หลักสูตร", "service"], ["คู่มือ", "document_library"], ["เอกสารประกอบ", "document_library"]],
  };
  if (blueprintDefaults[blueprintId]) {
    $("#create-tab-list").replaceChildren();
    blueprintDefaults[blueprintId].forEach(([name, pageType]) => addCreateTab(name, pageType));
  }
  $("#create-network").value = website ? "internet" : "local";
  $("#create-density").value = website ? "comfortable" : "compact";
  if (website) $("#create-auth").checked = true;
  syncGuidedBuild();
});
$("#add-create-tab").addEventListener("click", () => addCreateTab());
$("#create-tab-list").addEventListener("click", event => {
  const remove = event.target.closest(".remove-create-tab");
  if (!remove || $$(".create-tab-row").length <= 1) return;
  remove.closest(".create-tab-row").remove();
  state.createSpec = null;
  syncGuidedBuild();
});
$("#create-project-name").addEventListener("input", () => { state.createSpec = null; });
$("#create-spec-preview").addEventListener("click", async () => {
  const form = $("#bth-create-form");
  if (!state.project || state.buildBusy || !form.reportValidity()) return;
  state.buildBusy = true; syncBuild();
  $("#create-spec-output").textContent = "กำลังตรวจ Project Spec…";
  try {
    const result = await api("/api/projects/" + encodeURIComponent(state.project.id) + "/bth-create/spec", {
      ...mutation("POST", createPayload()), timeout: 30000,
    });
    state.createSpec = result.project_spec;
    $("#create-spec-output").textContent = JSON.stringify(result.project_spec, null, 2);
    $("#build-output").textContent = "Project Spec ผ่านการตรวจสอบ\nBlueprint: " + result.project_spec.blueprint.id + "\nTheme: " + result.project_spec.theme.id + "\nComponents: " + Object.keys(result.catalog_versions.components).join(", ");
    toast("Project Spec พร้อม Freeze");
  } catch (error) {
    $("#create-spec-output").textContent = errorMessage(error);
    toast(errorMessage(error), true);
  } finally { state.buildBusy = false; syncBuild(); }
});
$("#bth-create-form").addEventListener("submit", async event => {
  event.preventDefault();
  if (!state.project || state.buildBusy || !event.currentTarget.reportValidity()) return;
  const projectId = state.project.id;
  state.buildBusy = true; syncBuild();
  $("#create-spec-output").textContent = "Freeze Spec → Gap Analysis → Task DAG → Build → Verify…";
  $("#build-output").textContent = "BTH Create กำลังสร้างผลงานจาก Frozen Spec…";
  try {
    const result = await api("/api/projects/" + encodeURIComponent(projectId) + "/bth-create/build", {
      ...mutation("POST", createPayload()), timeout: 180000,
    });
    state.createSpec = result.project_spec;
    const frozenId = result.frozen_spec.project_spec_id + "-r" + result.frozen_spec.revision;
    $("#create-spec-output").textContent = "สำเร็จ\nFrozen Spec: " + frozenId + "\nGap: " + (result.gap_analysis.missing.length ? "พบส่วนที่ขาด" : "ใช้ของเดิมได้ทั้งหมด") + "\nVerification: " + result.verification.status;
    $("#build-output").textContent = "BTH Create completed\nFrozen Spec: " + frozenId + "\nTasks: " + result.task_dag.tasks.length + "\nVerification: " + result.verification.results.filter(item => item.status === "passed").length + "/" + result.verification.results.length + " passed\nFiles: " + result.promoted_files.join(", ");
    state.buildPreviewUrl = result.preview_url;
    state.buildBusy = false;
    await loadBuildFiles();
    toast("BTH Create สร้างและตรวจสอบ Dashboard สำเร็จ");
    showBuildPreview(result.preview_url);
  } catch (error) {
    $("#create-spec-output").textContent = errorMessage(error);
    $("#build-output").textContent = "BTH Create blocked\n" + errorMessage(error);
    toast(errorMessage(error), true);
  } finally { state.buildBusy = false; syncBuild(); }
});
$("#build-editor").addEventListener("input", () => { syncBuild(); checkBuildDiagnostics($("#build-editor").value); });
$("#build-agent-instruction").addEventListener("input", syncBuild);
$("#build-agent-instruction").addEventListener("keydown", event => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    $("#build-chat-form").requestSubmit();
  }
});
$("#build-chat-suggestions").addEventListener("click", event => {
  const prompt = event.target.closest("[data-prompt]")?.dataset.prompt;
  if (!prompt) return;
  $("#build-agent-instruction").value = prompt;
  syncBuild();
  $("#build-chat-form").requestSubmit();
});
$("#clear-build-chat").addEventListener("click", async () => {
  if (!state.project || !getBuildChat().length) return;
  if (!await confirmAction("เริ่มบทสนทนาใหม่?", "ประวัติ Build Assistant ของโปรเจกต์นี้จะถูกล้าง", "ล้างบทสนทนา")) return;
  saveBuildChat([]);
  renderBuildChat();
  $("#build-agent-instruction").focus();
});
$("#build-chat-form").addEventListener("submit", async event => {
  event.preventDefault();
  const message = $("#build-agent-instruction").value.trim();
  if (!state.project || state.buildBusy || state.buildAssistantBusy || !message) return;
  const projectId = state.project.id;
  const previous = getBuildChat();
  saveBuildChat([...previous, { role: "user", content: message }]);
  $("#build-agent-instruction").value = "";
  state.buildAssistantBusy = true;
  renderBuildChat(true);
  try {
    const result = await api("/api/projects/" + encodeURIComponent(projectId) + "/workspace/assistant", {
      ...mutation("POST", { message, model: $("#build-model").value, history: previous.slice(-12) }), timeout: 180000,
    });
    if (state.project?.id !== projectId) return;
    saveBuildChat([...getBuildChat(), { role: "assistant", content: result.reply }]);
  } catch (error) {
    if (state.project?.id === projectId) {
      saveBuildChat([...getBuildChat(), { role: "assistant", content: "ขออภัย ยังตอบไม่ได้: " + errorMessage(error) }]);
      toast(errorMessage(error), true);
    }
  } finally {
    state.buildAssistantBusy = false;
    renderBuildChat();
    $("#build-agent-instruction").focus();
  }
});
$("#preview-build").addEventListener("click", () => showBuildPreview());
$("#preview-viewport").addEventListener("change", setPreviewViewport);
$("#preview-edit-mode").addEventListener("click", () => setPreviewEditMode(!state.previewEditMode));
window.addEventListener("message", async event => {
  if (event.source !== $("#build-preview-frame").contentWindow || event.data?.source !== "hermes-preview") return;
  if (event.data.type === "selected") {
    state.previewSelection = event.data;
    $("#preview-selection").textContent = `${event.data.tag} · ${event.data.nodeId}${event.data.text ? " · " + event.data.text.slice(0, 80) : ""}`;
    loadPreviewProperties(event.data.nodeId);
  }
  if (event.data.type === "inline-text" && state.project) {
    try {
      await api("/api/projects/" + encodeURIComponent(state.project.id) + "/workspace/preview/edit-text", { ...mutation("POST", { node_id: event.data.nodeId, text: event.data.text }) });
      toast("บันทึกข้อความจาก Preview แล้ว");
      showBuildPreview();
      await loadBuildFiles();
    } catch (error) { toast(errorMessage(error), true); }
  }
});
$("#preview-apply-properties").addEventListener("click", applyPreviewProperties);
$("#open-build-preview-tab").addEventListener("click", () => {
  if (state.buildPreviewUrl) window.open(state.buildPreviewUrl, "_blank", "noopener,noreferrer");
});
$("#new-build-file").addEventListener("click", () => {
  if (!state.project) return;
  openName("สร้างไฟล์", "", 500, async path => {
    const clean = path.trim();
    if (state.buildFiles.some(file => file.path === clean)) throw new Error("มีไฟล์ชื่อนี้อยู่แล้ว");
    await api("/api/projects/" + encodeURIComponent(state.project.id) + "/workspace/file", mutation("PUT", { path: clean, content: "" }));
    await loadBuildFiles();
    await openBuildFile(clean);
    toast("สร้างไฟล์แล้ว");
  });
});
$("#refresh-build-files").addEventListener("click", async () => {
  if (buildDirty() && !await confirmAction("ละทิ้งการแก้ไข?", "ไฟล์ปัจจุบันยังไม่ได้บันทึก", "ละทิ้ง")) return;
  await loadBuildFiles();
});
$("#save-build-file").addEventListener("click", async () => {
  if (!state.project || !state.buildFilePath || state.buildBusy) return;
  state.buildBusy = true; syncBuild();
  try {
    const content = $("#build-editor").value;
    const diagnostics = await api("/api/projects/" + encodeURIComponent(state.project.id) + "/workspace/diagnostics", { ...mutation("POST", { path: state.buildFilePath, content }) });
    state.buildDiagnostics = diagnostics.issues || []; renderBuildDiagnostics();
    if (!diagnostics.valid) { toast("บันทึกไม่ได้: พบ syntax error ในไฟล์", true); return; }
    const saved = await api("/api/projects/" + encodeURIComponent(state.project.id) + "/workspace/file", mutation("PUT", { path: state.buildFilePath, content, base_revision: state.buildFileRevision }));
    state.buildFileContent = content;
    state.buildFileRevision = saved.revision || state.buildFileRevision;
    await loadBuildFiles();
    toast("บันทึก " + state.buildFilePath + " แล้ว");
  } catch (error) { toast(errorMessage(error), true); }
  finally { state.buildBusy = false; syncBuild(); }
});
$("#delete-build-file").addEventListener("click", async () => {
  if (!state.project || !state.buildFilePath || state.buildBusy) return;
  const path = state.buildFilePath;
  if (!await confirmAction("ลบไฟล์นี้หรือไม่?", `ไฟล์ “${path}” จะถูกลบถาวร`, "ลบไฟล์")) return;
  state.buildBusy = true; syncBuild();
  try {
    await api("/api/projects/" + encodeURIComponent(state.project.id) + "/workspace/file?path=" + encodeURIComponent(path), { method: "DELETE" });
    state.buildFilePath = null; state.buildFileContent = ""; $("#build-editor").value = "";
    await loadBuildFiles(); toast("ลบไฟล์แล้ว");
  } catch (error) { toast(errorMessage(error), true); }
  finally { state.buildBusy = false; syncBuild(); }
});
$("#run-command-form").addEventListener("submit", async event => {
  event.preventDefault();
  if (!state.project || state.buildBusy) return;
  if (buildDirty()) { toast("บันทึกไฟล์ก่อนรันคำสั่ง", true); return; }
  const command = $("#run-command").value.trim();
  if (!command) return;
  state.buildBusy = true; syncBuild();
  $("#build-output").textContent = "$ " + command + "\nกำลังรัน…";
  try {
    const result = await api("/api/projects/" + encodeURIComponent(state.project.id) + "/workspace/run", {
      ...mutation("POST", { command, timeout: 60 }), timeout: 70000,
    });
    const status = result.timed_out ? "หมดเวลา" : "exit " + result.exit_code;
    const output = [result.stdout, result.stderr].filter(Boolean).join("\n");
    $("#build-output").textContent = "$ " + command + "\n[" + status + " · " + result.duration_ms + " ms]\n" + (output || "(ไม่มี output)") + (result.truncated ? "\n[output ถูกตัดตามขนาดที่กำหนด]" : "");
  } catch (error) { $("#build-output").textContent = "$ " + command + "\n" + errorMessage(error); }
  finally { state.buildBusy = false; syncBuild(); }
});
async function runBuildAgent() {
  if (!state.project || state.buildBusy || state.buildAssistantBusy || $("#build-agent-button").disabled) return;
  if (buildDirty()) { toast("บันทึกไฟล์ปัจจุบันก่อนให้ AI แก้โปรเจกต์", true); return; }
  const instruction = buildActionInstruction();
  const draftInstruction = $("#build-agent-instruction").value.trim();
  if (draftInstruction && (getBuildChat().at(-1)?.role !== "user" || getBuildChat().at(-1)?.content !== draftInstruction)) {
    saveBuildChat([...getBuildChat(), { role: "user", content: draftInstruction }]);
  }
  let firstChanged = null;
  state.buildBusy = true; syncBuild();
  $("#build-output").textContent = "AI กำลังอ่านโปรเจกต์และลงมือแก้ไข…";
  const projectId = state.project.id;
  let progressLoading = false;
  const progressTimer = setInterval(async () => {
    if (progressLoading) return;
    progressLoading = true;
    try {
      const data = await api("/api/projects/" + encodeURIComponent(projectId) + "/workspace/build-runs");
      const run = data.runs[0];
      if (state.buildBusy && run) $("#build-output").textContent = "Build: " + run.status + "\n" + run.attempts.map(step => "รอบ " + step.attempt + (step.target_file ? " · " + step.target_file : "") + " · " + step.status + "\n" + (step.issues || []).join("\n")).join("\n") + "\nรายงาน: " + run.path;
    } catch { /* The final request retains its own error handling. */ }
    finally { progressLoading = false; }
  }, 5000);
  try {
    const result = await api("/api/projects/" + encodeURIComponent(state.project.id) + "/workspace/agent", {
      ...mutation("POST", { instruction, model: $("#build-model").value, run_command: true }), timeout: 1000000,
    });
    const changed = result.files.map(file => file.path);
    state.buildFilePath = null; state.buildFileContent = ""; $("#build-editor").value = "";
    await loadBuildFiles();
    firstChanged = changed[0] || null;
    const run = result.run;
    const runText = run ? "\n\n$ " + run.command.join(" ") + "\n[exit " + run.exit_code + " · " + run.duration_ms + " ms]\n" + [run.stdout, run.stderr].filter(Boolean).join("\n") : "";
    const issueText = result.issues?.length ? "\n\nยังต้องตรวจสอบ:\n- " + result.issues.join("\n- ") : "";
    $("#build-output").textContent = result.summary + "\nสถานะ: " + (result.status === "completed" ? "พร้อมใช้งาน" : "ต้องตรวจสอบเพิ่มเติม") + " · " + result.attempts + " รอบ\nไฟล์ที่เปลี่ยน: " + (changed.join(", ") || "ไม่มี") + runText + issueText;
    if (result.report_path) $("#build-output").textContent += "\nรายงานทุกขั้นตอน: " + result.report_path;
    $("#build-agent-instruction").value = "";
    saveBuildChat([...getBuildChat(), { role: "assistant", content: result.summary + "\n\nไฟล์ที่เปลี่ยน: " + (changed.join(", ") || "ไม่มี") }]);
    renderBuildChat();
    if (result.preview_url) state.buildPreviewUrl = result.preview_url;
    if (result.status === "completed") {
      toast(result.preview_url ? "สร้างเว็บไซต์เสร็จแล้ว" : "AI ทำโปรเจกต์เสร็จแล้ว");
      if (result.preview_url) showBuildPreview(result.preview_url);
    } else toast("AI ทำงานครบจำนวนรอบแล้ว กรุณาตรวจผลลัพธ์", true);
  } catch (error) { $("#build-output").textContent = errorMessage(error); toast(errorMessage(error), true); }
  finally { clearInterval(progressTimer); state.buildBusy = false; syncBuild(); }
  if (firstChanged) await openBuildFile(firstChanged);
}
$("#build-agent-button").addEventListener("click", runBuildAgent);

function switchView(view) {
  closeDrawer();
  state.view = view;
  $("#main-panel").className = "main-panel view-" + view;
  ["chat", "build", "notebook", "workers"].forEach(name => {
    $("#" + name + "-view").hidden = name !== view;
    const sidebar = name === "workers" ? $("#worker-sidebar") : $("#" + name + "-sidebar");
    sidebar.hidden = name !== view;
    const tab = $("#tab-" + name);
    tab.classList.toggle("active", name === view);
    tab.setAttribute("aria-selected", String(name === view));
    tab.tabIndex = name === view ? 0 : -1;
  });
  $("#right-panel").hidden = view !== "chat";
  setHeading(); syncDrawers();
  if (view === "notebook") renderNotebooks();
  if (view === "build") { renderBuildProjects(); loadBuildFiles(); }
  if (view === "workers") { renderWorkers(); refreshHealth(); }
}
$$(".workspace-tab").forEach((tab, index, tabs) => {
  tab.addEventListener("click", () => switchView(tab.dataset.view));
  tab.addEventListener("keydown", event => {
    let next;
    if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
    if (event.key === "ArrowLeft") next = (index + tabs.length - 1) % tabs.length;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = tabs.length - 1;
    if (next !== undefined) { event.preventDefault(); tabs[next].focus(); switchView(tabs[next].dataset.view); }
  });
});
let drawer = null, drawerTrigger = null;
function syncDrawers() {
  $("#sidebar").inert = (matchMedia("(max-width: 900px)").matches && drawer !== "sidebar") || drawer === "right-panel";
  $("#right-panel").inert = state.view !== "chat" || (matchMedia("(max-width: 1180px)").matches && drawer !== "right-panel") || drawer === "sidebar";
  ["topbar", "workspace-bar", "workspace-content", "connection-banner"].forEach(id => $("#" + id).inert = !!drawer);
  $("#drawer-backdrop").hidden = !drawer;
  $("#mobile-menu").setAttribute("aria-expanded", String(drawer === "sidebar"));
  $("#mobile-settings").setAttribute("aria-expanded", String(drawer === "right-panel"));
  ["sidebar", "right-panel"].forEach(id => {
    $("#" + id).classList.toggle("open", drawer === id);
    if (drawer === id) { $("#" + id).setAttribute("role", "dialog"); $("#" + id).setAttribute("aria-modal", "true"); }
    else { $("#" + id).removeAttribute("role"); $("#" + id).removeAttribute("aria-modal"); }
  });
}
function openDrawer(id, trigger) {
  drawer = id; drawerTrigger = trigger; syncDrawers();
  const panel = $("#" + id);
  ($("button:not(:disabled)", panel) || panel).focus();
}
function closeDrawer() {
  const trigger = drawerTrigger, wasOpen = !!drawer;
  drawer = null; drawerTrigger = null; syncDrawers();
  if (wasOpen) trigger?.focus();
}
document.addEventListener("keydown", event => {
  if (!drawer || $("dialog[open]")) return;
  if (event.key === "Escape") { event.preventDefault(); closeDrawer(); return; }
  if (event.key !== "Tab") return;
  const panel = $("#" + drawer);
  const focusable = $$('button:not(:disabled), input:not(:disabled), select:not(:disabled), [tabindex="0"]', panel).filter(node => node.getClientRects().length);
  const first = focusable[0], last = focusable.at(-1);
  if (!first) { event.preventDefault(); panel.focus(); }
  else if (event.shiftKey && (document.activeElement === first || document.activeElement === panel)) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
});
window.addEventListener("resize", () => { if (drawer) closeDrawer(); else syncDrawers(); resizeInput(); });
$("#drawer-backdrop").addEventListener("click", closeDrawer);
$("#mobile-menu").addEventListener("click", event => openDrawer("sidebar", event.currentTarget));
$("#mobile-settings").addEventListener("click", event => openDrawer("right-panel", event.currentTarget));
async function loadReadme() {
  const target = $("#readme-content");
  target.textContent = "กำลังโหลด README.md…";
  try {
    const response = await fetch("/api/readme", { headers: state.token ? { "x-hermes-token": state.token } : {} });
    if (!response.ok) throw new Error("โหลดคู่มือไม่สำเร็จ (" + response.status + ")");
    target.textContent = await response.text();
  } catch (error) { target.textContent = "ไม่สามารถโหลด README.md ได้\n\n" + error.message; }
}
function openSettingsDialog() {
  if (state.view !== "chat") switchView("chat");
  const dialog = $("#settings-dialog");
  if (!dialog.open) dialog.showModal();
  loadReadme();
  $("#ui-theme-select").focus();
}
$("#brand-settings").addEventListener("click", openSettingsDialog);
$("#ui-theme-select").addEventListener("change", event => applyUiTheme(event.target.value));
$("#reload-readme").addEventListener("click", loadReadme);
$("#close-sidebar").addEventListener("click", closeDrawer);
$("#close-settings").addEventListener("click", closeDrawer);

let resourceBusy = false, healthBusy = false;
async function refreshResources() {
  if (resourceBusy || document.hidden) return;
  resourceBusy = true;
  try {
    const result = await api("/api/resources");
    const gpus = result.gpus || [];
    $("#gpu-resources").replaceChildren(...gpus.map(gpu => {
      const item = el("div");
      const row = el("div", "resource-row");
      row.append(el("span", "", "GPU " + gpu.index), el("span", "", Math.round(gpu.utilization) + "%"));
      const bar = el("div", "resource-bar"), fill = el("span");
      fill.style.width = Math.max(0, Math.min(100, gpu.utilization)) + "%";
      bar.setAttribute("aria-hidden", "true"); bar.append(fill);
      item.append(el("div", "gpu-name", gpu.name), row, bar, el("div", "gpu-temp", "VRAM " + (gpu.memory_used / 1024).toFixed(1) + " / " + (gpu.memory_total / 1024).toFixed(1) + " GB · " + gpu.temperature + "°C"));
      return item;
    }));
    if (!gpus.length) $("#gpu-resources").append(el("p", "resource-empty", "ไม่มีข้อมูล GPU จากเซิร์ฟเวอร์"));
    $("#ram-value").textContent = result.memory.total ? (result.memory.used / 1024).toFixed(1) + " / " + (result.memory.total / 1024).toFixed(1) + " GB" : "ไม่มีข้อมูล";
    $("#ram-bar").style.width = Math.max(0, Math.min(100, result.memory.percent)) + "%";
    $("#load-value").textContent = result.load;
    $("#resource-refresh").textContent = new Date().toLocaleTimeString("th-TH", { hour: "2-digit", minute: "2-digit" });
  } catch {
    $("#resource-refresh").textContent = "อัปเดตไม่ได้";
    $("#ram-value").textContent = "—"; $("#load-value").textContent = "—"; $("#ram-bar").style.width = "0%";
    $("#gpu-resources").replaceChildren(el("p", "resource-empty", "ไม่สามารถอ่านทรัพยากรได้"));
  } finally { resourceBusy = false; }
}
async function refreshHealth() {
  if (healthBusy) return;
  healthBusy = true; $("#refresh-workers").disabled = true;
  try { state.health = await api("/api/health"); }
  catch { state.health = { ok: false, models: [] }; }
  finally {
    healthBusy = false; $("#refresh-workers").disabled = false;
    $("#status-dot").classList.toggle("online", !!state.health?.ok);
    $("#provider-state").textContent = state.health?.ok ? "Ollama เชื่อมต่อแล้ว" : "Ollama ไม่พร้อมใช้งาน";
    renderWorkers();
  }
}
async function connectWorkspace() {
  if (state.connecting || locked()) return;
  state.connecting = true;
  // An earlier request may have failed after the page was restored from cache.
  // Always begin a new workspace sync with a fresh, server-backed status.
  composerError();
  $("#retry-connection").disabled = true;
  $("#banner-retry").disabled = true;
  const errors = [];
  try {
    await reloadProjects();
    if (!state.project && state.projects.length) await selectProject(state.projects[0].id);
    if (!state.project) { applyConversation(null); }
  } catch (error) { errors.push(error); }
  try {
    const data = await api("/api/models");
    applyModelCatalog(data);
    if (!data.models.length) errors.push(new Error("ยังไม่มีโมเดลพร้อมใช้งาน กรุณาติดตั้งโมเดลบน Ollama"));
  } catch (error) { state.modelsReady = false; errors.push(error); modelInfo(); }
  if (errors.length) banner(errors.map(errorMessage).join(" · "), errors.some(error => error.status === 401));
  else banner();
  state.connecting = false; $("#retry-connection").disabled = false; $("#banner-retry").disabled = false;
  syncComposer();
  await Promise.all([refreshHealth(), refreshResources()]);
}
$("#auth-form").addEventListener("submit", async event => {
  event.preventDefault();
  const form = event.currentTarget, previous = state.token;
  if (form.dataset.saving) return;
  form.dataset.saving = "true"; $("button[type=submit]", form).disabled = true;
  state.token = $("#auth-token").value;
  try { await api("/api/projects"); $("#auth-dialog").close(); $("#auth-token").value = ""; await connectWorkspace(); }
  catch (error) { state.token = previous; formError(form, errorMessage(error)); }
  finally { delete form.dataset.saving; $("button[type=submit]", form).disabled = false; }
});
$("#auth-open").addEventListener("click", () => { formError($("#auth-form")); $("#auth-dialog").showModal(); });
$("#retry-connection").addEventListener("click", connectWorkspace);
$("#banner-retry").addEventListener("click", connectWorkspace);
$("#refresh-workers").addEventListener("click", refreshHealth);
$("#new-chat").addEventListener("click", newChat);
$("#chat-sidebar-search").addEventListener("input", scheduleChatSearch);
$("#chat-sidebar-search").addEventListener("keydown", event => {
  if (event.key === "Escape" && event.currentTarget.value) {
    event.preventDefault();
    clearChatSearch();
    renderProjects();
  }
});
$("#new-project").addEventListener("click", newProject);
$("#new-build-project").addEventListener("click", newProject);
$("#rename-chat").addEventListener("click", () => { if (state.conversation) renameConversation(state.conversation); });
$("#new-notebook").addEventListener("click", () => openNotebook());
$("#new-notebook-main").addEventListener("click", () => openNotebook());
$("#discover-workers").addEventListener("click", () => { $("#worker-form").reset(); formError($("#worker-form")); $("#worker-dialog").showModal(); });
$("#add-api-provider").addEventListener("click", () => { $("#api-provider-form").reset(); formError($("#api-provider-form")); syncApiProviderPreset(); $("#api-provider-dialog").showModal(); $("#api-provider-key").focus(); });
window.addEventListener("beforeunload", event => {
  const otherDrafts = [...state.drafts.keys()].some(id => id !== state.conversation?.id);
  if (locked() || buildDirty() || $("#build-agent-instruction").value.trim() || $("#message").value.trim() || state.files.length || otherDrafts || ($("#notebook-dialog").open && notebookDirty())) {
    event.preventDefault(); event.returnValue = "";
  }
});
document.addEventListener("visibilitychange", () => { if (!document.hidden) { refreshResources(); refreshHealth(); } });
setInterval(refreshResources, 10000);
setInterval(() => { if (!document.hidden) refreshHealth(); }, 30000);
syncDrawers();
renderBuildFiles();
connectWorkspace();
