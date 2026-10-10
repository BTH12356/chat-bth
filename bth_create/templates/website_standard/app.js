"use strict";

const menuButton = document.querySelector(".menu-toggle");
const navigation = document.querySelector(".site-nav");
const resourceDatabaseName = `bth-page-resources-v1:${location.pathname}`;
menuButton?.addEventListener("click", () => {
  const open = navigation.classList.toggle("open");
  menuButton.setAttribute("aria-expanded", String(open));
});

document.querySelectorAll(".page-image-input").forEach((input, index) => {
  const slot = input.closest("[data-image-slot]");
  const storageKey = `bth-page-image:${location.pathname}:${index}`;
  const saved = localStorage.getItem(storageKey);
  if (saved) {
    slot.style.backgroundImage = `url("${saved}")`;
    slot.querySelector("span")?.setAttribute("hidden", "");
  }
  input.addEventListener("change", () => {
    const file = input.files[0];
    if (!file) return;
    if (!file.type.startsWith("image/") || file.size > 2 * 1024 * 1024) {
      window.alert("กรุณาเลือกไฟล์ภาพขนาดไม่เกิน 2 MB");
      input.value = "";
      return;
    }
    const reader = new FileReader();
    reader.addEventListener("load", () => {
      slot.style.backgroundImage = `url("${reader.result}")`;
      slot.querySelector("span")?.setAttribute("hidden", "");
      try { localStorage.setItem(storageKey, reader.result); } catch (_) { /* Preview still works for this session. */ }
    });
    reader.readAsDataURL(file);
  });
});

function applyPageSearch() {
  const input = document.querySelector("[data-page-search]");
  if (!input) return;
  const query = input.value.trim().toLocaleLowerCase("th");
  const direction = document.querySelector("[data-page-sort]")?.value || "az";
  const grid = document.querySelector("[data-search-grid]");
  const items = [...document.querySelectorAll("[data-search-item]")];
  items.forEach((item) => { item.hidden = Boolean(query) && !item.textContent.toLocaleLowerCase("th").includes(query); });
  if (grid) items.filter((item) => item.parentElement === grid)
    .sort((a, b) => a.textContent.localeCompare(b.textContent, "th", { sensitivity: "base" }) * (direction === "az" ? 1 : -1))
    .forEach((item) => grid.append(item));
}

document.querySelector("[data-page-search]")?.addEventListener("input", applyPageSearch);
document.querySelector("[data-page-sort]")?.addEventListener("change", applyPageSearch);

function openResourceDatabase() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(resourceDatabaseName, 1);
    request.onupgradeneeded = () => request.result.createObjectStore("resources", { keyPath: "id" });
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function resourceStore(mode, value) {
  const database = await openResourceDatabase();
  return new Promise((resolve, reject) => {
    const transaction = database.transaction("resources", mode === "save" ? "readwrite" : "readonly");
    const store = transaction.objectStore("resources");
    const request = mode === "save" ? store.put(value) : store.getAll();
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
    transaction.oncomplete = () => database.close();
  });
}

function appendResource(resource) {
  const grid = document.querySelector("[data-search-grid]");
  if (!grid) return;
  const card = document.createElement("article");
  card.className = "resource-card";
  card.dataset.searchItem = "";
  const heading = document.createElement("h3");
  heading.textContent = resource.name.replace(/\.pdf$/i, "");
  const description = document.createElement("p");
  description.textContent = `PDF · ${(resource.size / 1024 / 1024).toFixed(1)} MB`;
  const link = document.createElement("a");
  link.href = URL.createObjectURL(resource.file);
  link.target = "_blank";
  link.rel = "noopener";
  link.textContent = "เปิดเอกสาร →";
  card.append(heading, description, link);
  grid.prepend(card);
}

document.querySelectorAll("[data-resource-file]").forEach((input) => input.addEventListener("change", () => {
  const file = input.files[0];
  if (!file) return;
  if (file.type !== "application/pdf" && !file.name.toLocaleLowerCase().endsWith(".pdf")) {
    window.alert("กรุณาเลือกไฟล์ PDF");
    input.value = "";
    return;
  }
  if (file.size > 50 * 1024 * 1024) {
    window.alert("ไฟล์ PDF ต้องมีขนาดไม่เกิน 50 MB");
    input.value = "";
    return;
  }
  const resource = { id: crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`, name: file.name, size: file.size, file };
  resourceStore("save", resource).catch(() => {});
  appendResource(resource);
  input.value = "";
}));

resourceStore("read")
  .then((resources) => resources.forEach(appendResource))
  .catch(() => {});

document.querySelector(".contact-form")?.addEventListener("submit", (event) => {
  event.preventDefault();
  window.alert("รับข้อมูลแล้ว — เชื่อม API หรืออีเมลเพื่อใช้งานจริง");
});

fetch("project-config.json")
  .then((response) => response.json())
  .then((config) => { document.getElementById("build-status").textContent = `Frozen spec: ${config.frozen_spec_id}`; })
  .catch(() => { document.getElementById("build-status").textContent = "ไม่สามารถโหลด Build metadata"; });
