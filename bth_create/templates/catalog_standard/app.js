"use strict";

const cards = () => [...document.querySelectorAll(".catalog-card")];
const sections = () => [...document.querySelectorAll(".site-section")];
const catalogDatabaseName = `bth-catalog-v1:${location.pathname}`;
let activeObjectUrl = "";

function openDialog(id) {
  const dialog = document.getElementById(id);
  if (typeof dialog.showModal === "function") dialog.showModal();
  else dialog.setAttribute("open", "");
}

function closeDialog(id) {
  const dialog = document.getElementById(id);
  if (typeof dialog.close === "function") dialog.close();
  else dialog.removeAttribute("open");
}

function updateCounts() {
  let visibleTotal = 0;
  sections().forEach((section) => {
    const visible = [...section.querySelectorAll(".catalog-card")].filter((card) => !card.hidden).length;
    visibleTotal += visible;
    section.querySelector(".topic-count").textContent = `${visible} รายการ`;
    section.hidden = visible === 0;
  });
  document.getElementById("total-count").textContent = cards().length;
  document.getElementById("catalog-empty").hidden = visibleTotal !== 0;
}

function filterAndSort() {
  const query = document.getElementById("catalog-search").value.trim().toLocaleLowerCase("th");
  const direction = document.getElementById("catalog-sort").value;
  cards().forEach((card) => {
    const text = `${card.dataset.title} ${card.dataset.topicName} ${card.dataset.author || ""} ${card.dataset.description || ""}`.toLocaleLowerCase("th");
    card.hidden = Boolean(query) && !text.includes(query);
  });
  sections().forEach((section) => {
    const grid = section.querySelector(".catalog-grid");
    [...grid.querySelectorAll(".catalog-card")]
      .sort((a, b) => a.dataset.title.localeCompare(b.dataset.title, "th", { sensitivity: "base" }) * (direction === "az" ? 1 : -1))
      .forEach((card) => grid.append(card));
  });
  updateCounts();
}

function showDetails(card) {
  document.getElementById("detail-topic").textContent = card.dataset.topicName;
  document.getElementById("detail-title").textContent = card.dataset.title;
  document.getElementById("detail-author").textContent = card.dataset.author ? `ผู้เขียน / เจ้าของข้อมูล: ${card.dataset.author}` : "";
  document.getElementById("detail-description").textContent = card.dataset.description || "ยังไม่มีคำอธิบาย";
  const cover = document.getElementById("detail-cover");
  cover.textContent = card.dataset.coverUrl ? "" : card.dataset.title.slice(0, 1).toLocaleUpperCase("th");
  cover.style.backgroundImage = card.dataset.coverUrl ? `url("${card.dataset.coverUrl}")` : "";
  const link = document.getElementById("detail-pdf-link");
  const noPdf = document.getElementById("detail-no-pdf");
  if (activeObjectUrl) URL.revokeObjectURL(activeObjectUrl);
  activeObjectUrl = "";
  if (card._pdfBlob) {
    activeObjectUrl = URL.createObjectURL(card._pdfBlob);
    link.href = activeObjectUrl;
    link.hidden = false;
    noPdf.hidden = true;
  } else {
    link.hidden = true;
    noPdf.hidden = false;
  }
  openDialog("item-detail-dialog");
}

function createCard(item) {
  const card = document.createElement("article");
  card.className = "catalog-card";
  card.dataset.title = item.title;
  card.dataset.topic = item.topic;
  card.dataset.topicName = item.topicName;
  card.dataset.author = item.author || "";
  card.dataset.description = item.description || "";
  card._pdfBlob = item.pdf || null;
  let visual;
  if (item.cover) {
    visual = document.createElement("img");
    visual.className = "card-cover";
    visual.alt = `หน้าปก ${item.title}`;
    visual.src = URL.createObjectURL(item.cover);
    card.dataset.coverUrl = visual.src;
  } else {
    visual = document.createElement("div");
    visual.className = "cover-placeholder";
    visual.setAttribute("aria-hidden", "true");
    const mark = document.createElement("span");
    mark.textContent = item.title.slice(0, 1).toLocaleUpperCase("th");
    visual.append(mark);
  }
  const copy = document.createElement("div");
  copy.className = "card-copy";
  const topic = document.createElement("span");
  topic.className = "card-topic";
  topic.textContent = item.topicName;
  const title = document.createElement("h3");
  title.textContent = item.title;
  const description = document.createElement("p");
  description.textContent = item.description || "ยังไม่มีคำอธิบาย";
  const button = document.createElement("button");
  button.className = "open-detail";
  button.type = "button";
  button.textContent = "ดูรายละเอียด";
  copy.append(topic, title, description, button);
  card.append(visual, copy);
  return card;
}

function openDatabase() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(catalogDatabaseName, 1);
    request.onupgradeneeded = () => request.result.createObjectStore("items", { keyPath: "id" });
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function storedItems(mode, value) {
  const database = await openDatabase();
  return new Promise((resolve, reject) => {
    const transaction = database.transaction("items", mode === "save" ? "readwrite" : "readonly");
    const store = transaction.objectStore("items");
    const request = mode === "save" ? store.put(value) : store.getAll();
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
    transaction.oncomplete = () => database.close();
  });
}

document.querySelectorAll(".nav-tab").forEach((button, index) => {
  if (index === 0) button.classList.add("active");
  button.addEventListener("click", () => {
    document.querySelectorAll(".nav-tab").forEach((item) => item.classList.toggle("active", item === button));
    document.getElementById(button.dataset.tab)?.scrollIntoView({ behavior: "smooth" });
  });
});

document.addEventListener("click", (event) => {
  const closeButton = event.target.closest("[data-close]");
  if (closeButton) closeDialog(closeButton.dataset.close);
  const detailButton = event.target.closest(".open-detail");
  if (detailButton) showDetails(detailButton.closest(".catalog-card"));
});

document.getElementById("open-add-item").addEventListener("click", () => openDialog("add-item-dialog"));
document.getElementById("catalog-search").addEventListener("input", filterAndSort);
document.getElementById("catalog-sort").addEventListener("change", filterAndSort);
document.getElementById("add-item-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const topic = document.getElementById("item-topic");
  const coverFile = document.getElementById("item-cover").files[0] || null;
  const pdfFile = document.getElementById("item-pdf").files[0] || null;
  if (coverFile && !coverFile.type.startsWith("image/")) return window.alert("กรุณาเลือกไฟล์ภาพสำหรับหน้าปก");
  if (coverFile && coverFile.size > 5 * 1024 * 1024) return window.alert("ไฟล์หน้าปกต้องมีขนาดไม่เกิน 5 MB");
  if (pdfFile && pdfFile.type !== "application/pdf" && !pdfFile.name.toLocaleLowerCase().endsWith(".pdf")) return window.alert("กรุณาเลือกไฟล์ PDF");
  if (pdfFile && pdfFile.size > 50 * 1024 * 1024) return window.alert("ไฟล์ PDF ต้องมีขนาดไม่เกิน 50 MB");
  const item = {
    id: crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`,
    title: document.getElementById("item-title").value.trim(),
    topic: topic.value,
    topicName: topic.selectedOptions[0].textContent,
    author: document.getElementById("item-author").value.trim(),
    description: document.getElementById("item-description").value.trim(),
    cover: coverFile,
    pdf: pdfFile,
    createdAt: new Date().toISOString(),
  };
  try { await storedItems("save", item); } catch (_) { /* The item still works for this browser session. */ }
  document.querySelector(`#${CSS.escape(item.topic)} .catalog-grid`).append(createCard(item));
  event.currentTarget.reset();
  closeDialog("add-item-dialog");
  filterAndSort();
});

storedItems("read")
  .then((items) => items.forEach((item) => document.querySelector(`#${CSS.escape(item.topic)} .catalog-grid`)?.append(createCard(item))))
  .catch(() => {})
  .finally(filterAndSort);

fetch("project-config.json")
  .then((response) => response.json())
  .then((config) => { document.getElementById("build-status").textContent = `Frozen spec: ${config.frozen_spec_id}`; })
  .catch(() => { document.getElementById("build-status").textContent = "ไม่สามารถโหลด Build metadata"; });
