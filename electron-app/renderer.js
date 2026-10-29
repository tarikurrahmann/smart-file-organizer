const elements = {
  folder: document.getElementById("selected-folder"),
  selectFolder: document.getElementById("select-folder"),
  changeFolder: document.getElementById("change-folder"),
  organizeNow: document.getElementById("organize-now"),
  dropZone: document.getElementById("drop-zone"),
  statusText: document.getElementById("status-text"),
  statusDot: document.getElementById("status-dot"),
  activityLog: document.getElementById("activity-log"),
  consoleFooter: document.getElementById("console-footer"),
  clearLogs: document.getElementById("clear-logs"),
  dashboardPage: document.getElementById("dashboard-page"),
  featurePage: document.getElementById("feature-page"),
  pageTitle: document.getElementById("page-title"),
  pageSubtitle: document.getElementById("page-subtitle"),
  pageContent: document.getElementById("page-content"),
  pageBack: document.getElementById("page-back"),
  autoSortButton: document.getElementById("auto-sort-toggle"),
  autoSortStatus: document.getElementById("auto-sort-status"),
  liveWatchButton: document.getElementById("live-watch-toggle"),
  liveWatchStatus: document.getElementById("live-watch-status")
};

const hasDesktopBridge = Boolean(window.organizer);
let selectedFolder = null;
let isOrganizing = false;
let activeWatcher = { running: false, kind: null };
let removeLogListener;
let removeWatcherStatusListener;

function setStatus(message, state = "ready") {
  elements.statusText.textContent = message;
  elements.statusDot.className = "h-2 w-2 rounded-full";
  if (state === "busy") {
    elements.statusDot.classList.add("animate-pulse", "bg-amber-300");
  } else if (state === "error") {
    elements.statusDot.classList.add("bg-rose-400");
  } else {
    elements.statusDot.classList.add("bg-emerald-400");
  }
}

function appendLog(entry) {
  const row = document.createElement("div");
  row.className = "log-row";
  const time = document.createElement("span");
  time.className = "log-time";
  time.textContent = entry.time || new Date().toLocaleTimeString();
  const dot = document.createElement("span");
  dot.className = "log-dot";
  dot.classList.add(
    entry.level === "error"
      ? "bg-rose-400"
      : entry.level === "success"
        ? "bg-emerald-400"
        : entry.level === "warning"
          ? "bg-amber-300"
          : "bg-cyan-300"
  );
  const content = document.createElement("div");
  content.className = "min-w-0 flex-1";
  const message = document.createElement("p");
  message.className = "truncate text-xs text-slate-300";
  message.textContent = entry.message;
  content.append(message);
  if (entry.detail) {
    const detail = document.createElement("p");
    detail.className = "mt-0.5 truncate text-[10px] text-slate-600";
    detail.textContent = entry.detail;
    content.append(detail);
  }
  row.append(time, dot, content);
  elements.activityLog.append(row);
  elements.activityLog.scrollTop = elements.activityLog.scrollHeight;
}

function node(tag, className = "", text = "") {
  const item = document.createElement(tag);
  if (className) {
    item.className = className;
  }
  if (text) {
    item.textContent = text;
  }
  return item;
}

function button(text, className = "modal-button", onClick = null) {
  const item = node("button", className, text);
  item.type = "button";
  if (onClick) {
    item.addEventListener("click", onClick);
  }
  return item;
}

function showDialog(title, subtitle, content) {
  elements.pageTitle.textContent = title;
  elements.pageSubtitle.textContent = subtitle;
  elements.pageContent.replaceChildren();
  if (typeof content === "function") {
    content(elements.pageContent);
  } else if (content) {
    elements.pageContent.append(
      typeof content === "string"
        ? node("p", "text-sm text-slate-400", content)
        : content
    );
  }
  elements.dashboardPage.classList.add("hidden");
  elements.featurePage.classList.remove("hidden");
  elements.featurePage.classList.add("flex");
  document.querySelectorAll(".nav-link").forEach((item) => item.classList.remove("nav-link-active"));
  const activeNavigation = {
    "Activity & stats": "nav-activity",
    "Custom rules": "nav-rules",
    "Duplicate cleaner": "nav-cleaner",
    "Private vault": "nav-vault"
  }[title];
  if (activeNavigation) {
    document.getElementById(activeNavigation).classList.add("nav-link-active");
  }
  elements.pageContent.scrollTop = 0;
  document.querySelector("main").scrollTo({ top: 0, behavior: "smooth" });
}

function showDashboard() {
  elements.featurePage.classList.add("hidden");
  elements.featurePage.classList.remove("flex");
  elements.dashboardPage.classList.remove("hidden");
  document.querySelectorAll(".nav-link").forEach((item) => item.classList.remove("nav-link-active"));
  document.getElementById("nav-overview").classList.add("nav-link-active");
  document.querySelector("main").scrollTo({ top: 0, behavior: "smooth" });
}

function showDesktopRequired(title, subtitle) {
  const message = node(
    "p",
    "rounded-xl border border-amber-300/15 bg-amber-300/[0.06] p-4 text-sm leading-6 text-amber-100",
    "এই ফিচারগুলো আপনার ফাইল ও ফোল্ডারে কাজ করে, তাই Electron desktop app-এ খুলতে হবে। শুধু index.html ব্রাউজারে খুললে OS file access পাওয়া যায় না।"
  );
  const steps = node(
    "p",
    "mt-4 rounded-xl border border-white/[0.07] bg-white/[0.03] p-4 font-mono text-xs leading-6 text-slate-300",
    "Project folder-এ terminal খুলে চালান:\n\nnpm install\nnpm start"
  );
  const wrap = node("div");
  wrap.append(message, steps);
  showDialog(title, subtitle, wrap);
}

function setSelectedFolder(folderPath) {
  selectedFolder = folderPath;
  elements.folder.textContent = folderPath || "No folder selected";
  elements.folder.title = folderPath || "";
  elements.organizeNow.disabled = !folderPath || isOrganizing || activeWatcher.running;
  if (folderPath) {
    setStatus("Folder ready");
    elements.consoleFooter.textContent = "Ready to organize files in the selected folder.";
  } else {
    setStatus("Ready to organize");
  }
}

function refreshWatcherUi() {
  const imageActive = activeWatcher.running && activeWatcher.kind === "images";
  const organizerActive = activeWatcher.running && activeWatcher.kind === "organizer";
  elements.autoSortButton.textContent = imageActive ? "Stop" : "Start";
  elements.liveWatchButton.textContent = organizerActive ? "Stop" : "Start";
  elements.autoSortButton.disabled =
    !imageActive && (activeWatcher.running || isOrganizing);
  elements.liveWatchButton.disabled =
    !organizerActive && (activeWatcher.running || isOrganizing);
  elements.selectFolder.disabled = activeWatcher.running || isOrganizing;
  elements.changeFolder.disabled = activeWatcher.running || isOrganizing;
  elements.dropZone.disabled = activeWatcher.running || isOrganizing;
  if (imageActive) {
    elements.autoSortStatus.textContent = `Watching ${activeWatcher.folder}. Images are sorted into dated Screenshots folders.`;
    elements.liveWatchStatus.textContent = "Stop image auto-sort before enabling the live file watcher.";
  } else if (organizerActive) {
    elements.liveWatchStatus.textContent = `Watching ${activeWatcher.folder} for new files.`;
    elements.autoSortStatus.textContent = "Stop live file organization before enabling image auto-sort.";
  } else {
    elements.autoSortStatus.textContent = selectedFolder
      ? "Watch new images and sort them into dated folders."
      : "Select a folder first to watch and sort new images.";
    elements.liveWatchStatus.textContent = selectedFolder
      ? "Automatically sort new files as they arrive."
      : "Select a folder first to start watching it.";
  }
  elements.organizeNow.disabled = hasDesktopBridge
    ? !selectedFolder || isOrganizing || activeWatcher.running
    : false;
}

async function chooseFolder() {
  if (!hasDesktopBridge) {
    showDesktopRequired("Select a folder", "Use the desktop app to browse local folders.");
    return null;
  }
  try {
    const folderPath = await window.organizer.selectFolder();
    if (folderPath) {
      setSelectedFolder(folderPath);
      refreshWatcherUi();
    }
    return folderPath;
  } catch (error) {
    setStatus("Could not select folder", "error");
    appendLog({ level: "error", message: "Could not select folder", detail: error.message });
    return null;
  }
}

async function ensureFolderSelected() {
  if (!hasDesktopBridge) {
    return false;
  }
  if (selectedFolder) {
    return true;
  }
  return Boolean(await chooseFolder());
}

async function organizeSelectedFolder() {
  if (!hasDesktopBridge) {
    showDesktopRequired("Organize files", "Folder organization runs inside Electron.");
    return;
  }
  if (!selectedFolder || isOrganizing || activeWatcher.running) {
    return;
  }
  isOrganizing = true;
  elements.organizeNow.disabled = true;
  elements.organizeNow.classList.add("is-busy");
  elements.organizeNow.querySelector("span").textContent = "Organizing…";
  elements.selectFolder.disabled = true;
  setStatus("Organizing files", "busy");
  refreshWatcherUi();
  elements.consoleFooter.textContent = "Sorting files into category folders…";
  try {
    const result = await window.organizer.organizeFolder(selectedFolder);
    const summary = `${result.moved} file${result.moved === 1 ? "" : "s"} organized`;
    setStatus(result.errors.length ? "Finished with some issues" : "Organization complete",
      result.errors.length ? "error" : "ready");
    elements.consoleFooter.textContent = result.errors.length
      ? `${summary} · ${result.errors.length} could not be moved.`
      : `${summary} · Your folder is up to date.`;
  } catch (error) {
    setStatus("Organization failed", "error");
    appendLog({ level: "error", message: "Organization failed", detail: error.message });
    elements.consoleFooter.textContent = error.message;
  } finally {
    isOrganizing = false;
    elements.organizeNow.classList.remove("is-busy");
    elements.organizeNow.querySelector("span").textContent = "Organize now";
    elements.selectFolder.disabled = false;
    refreshWatcherUi();
  }
}

async function organizeDroppedFiles(files) {
  if (!hasDesktopBridge) {
    showDesktopRequired("Organize dropped files", "Drag and drop works in the Electron desktop app.");
    return;
  }
  if (isOrganizing || activeWatcher.running || files.length === 0) {
    return;
  }
  isOrganizing = true;
  elements.organizeNow.disabled = true;
  elements.selectFolder.disabled = true;
  setStatus("Organizing dropped files", "busy");
  refreshWatcherUi();
  elements.consoleFooter.textContent = `Sorting ${files.length} dropped file(s)…`;
  try {
    const result = await window.organizer.organizeDroppedFiles(files);
    const summary = `${result.moved} dropped file${result.moved === 1 ? "" : "s"} organized`;
    setStatus(result.errors.length ? "Finished with some issues" : "Organization complete",
      result.errors.length ? "error" : "ready");
    elements.consoleFooter.textContent = result.errors.length
      ? `${summary} · ${result.errors.length} could not be moved.`
      : `${summary} · Files sorted beside their original locations.`;
  } catch (error) {
    setStatus("Could not organize dropped files", "error");
    appendLog({ level: "error", message: "Could not organize dropped files", detail: error.message });
    elements.consoleFooter.textContent = error.message;
  } finally {
    isOrganizing = false;
    elements.selectFolder.disabled = false;
    refreshWatcherUi();
  }
}

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes;
  let index = -1;
  do {
    value /= 1024;
    index += 1;
  } while (value >= 1024 && index < units.length - 1);
  return `${value.toFixed(value >= 10 ? 1 : 2)} ${units[index]}`;
}

function makeModalSection(title, description = "") {
  const section = node("section", "mb-4");
  section.append(node("h3", "text-sm font-semibold text-slate-100", title));
  if (description) {
    section.append(node("p", "mt-1 text-xs leading-5 text-slate-500", description));
  }
  return section;
}

async function openActivity() {
  if (!hasDesktopBridge) {
    showDesktopRequired("Activity & stats", "View organization history and undo from the desktop app.");
    return;
  }
  showDialog("Activity & stats", "Local history of your file organization.", "Loading activity…");
  try {
    const activity = await window.organizer.getActivity();
    const content = node("div");
    const stats = node("div", "mb-5 grid gap-3 sm:grid-cols-2");
    const total = node("article", "stat-card");
    total.append(node("p", "text-xs text-slate-500", "Files organized"), node("p", "mt-2 text-2xl font-semibold text-white", String(activity.total)));
    const categoryCount = node("article", "stat-card");
    categoryCount.append(node("p", "text-xs text-slate-500", "Categories used"), node("p", "mt-2 text-2xl font-semibold text-white", String(Object.keys(activity.categories).length)));
    stats.append(total, categoryCount);
    content.append(stats);

    const categories = makeModalSection("Files by category");
    const sortedCategories = Object.entries(activity.categories).sort((a, b) => b[1] - a[1]);
    if (!sortedCategories.length) {
      categories.append(node("p", "mt-3 text-xs text-slate-500", "No organized files yet."));
    }
    const maxCount = Math.max(1, ...sortedCategories.map(([, count]) => count));
    for (const [name, count] of sortedCategories) {
      const line = node("div", "mb-3");
      const label = node("div", "mb-1 flex justify-between text-xs");
      label.append(node("span", "text-slate-300", name), node("span", "text-slate-500", String(count)));
      const track = node("div", "h-1.5 overflow-hidden rounded-full bg-white/[0.06]");
      const fill = node("div", "h-full rounded-full bg-gradient-to-r from-emerald-300 to-cyan-400");
      fill.style.width = `${Math.max(3, (count / maxCount) * 100)}%`;
      track.append(fill);
      line.append(label, track);
      categories.append(line);
    }
    content.append(categories);

    const historySection = makeModalSection("Recent activity", "Latest 200 file operations. History is saved locally.");
    const table = node("div", "mt-3 max-h-60 overflow-auto rounded-xl border border-white/[0.07]");
    if (!activity.entries.length) {
      table.append(node("p", "p-4 text-xs text-slate-500", "No activity recorded yet. Organize a folder to get started."));
    }
    for (const entry of activity.entries) {
      const row = node("div", "grid gap-1 border-b border-white/[0.05] px-3 py-2.5 last:border-0 sm:grid-cols-[115px_80px_1fr]");
      row.append(
        node("span", "text-[10px] text-slate-500", new Date(entry.occurredAt).toLocaleString()),
        node("span", `text-xs ${entry.undone ? "text-amber-300" : "text-emerald-300"}`, entry.undone ? `${entry.category} · undone` : entry.category),
        node("span", "truncate text-[10px] text-slate-400", `${entry.source} → ${entry.destination}`)
      );
      table.append(row);
    }
    historySection.append(table);
    content.append(historySection);
    const controls = node("div", "mt-5 flex flex-wrap justify-end gap-2");
    controls.append(
      button("Refresh", "modal-button-secondary", openActivity),
      button(
        activity.undoCount ? `Undo latest action (${activity.undoCount})` : "Nothing to undo",
        "modal-button-primary",
        async () => {
          if (!activity.undoCount || !window.confirm(`Restore ${activity.undoCount} file(s) to their original locations? Existing files will never be overwritten.`)) return;
          try {
            const result = await window.organizer.undoLatest();
            if (result.errors.length) {
              window.alert(`Restored ${result.restored} file(s).\n\n${result.errors.slice(0, 5).join("\n")}`);
            }
            appendLog({ level: result.errors.length ? "warning" : "success", message: `Undo restored ${result.restored} file(s)`, detail: result.errors.join("; ") });
            await openActivity();
          } catch (error) {
            window.alert(`Undo failed: ${error.message}`);
          }
        }
      )
    );
    controls.lastChild.disabled = !activity.undoCount || activeWatcher.running;
    content.append(controls);
    showDialog("Activity & stats", "Local history of your file organization.", content);
  } catch (error) {
    showDialog("Activity & stats", "Could not load your local history.", node("p", "text-sm text-rose-300", error.message));
  }
}

async function openRules() {
  if (!hasDesktopBridge) {
    showDesktopRequired("Custom rules", "Create and save extension-based filing rules in the desktop app.");
    return;
  }
  showDialog("Custom rules", "Custom rules override the built-in file categories.", "Loading rules…");
  try {
    const rules = await window.organizer.getRules();
    const content = node("div");
    const form = node("form", "grid gap-3 rounded-xl border border-white/[0.07] bg-white/[0.025] p-4 sm:grid-cols-[1fr_1fr_auto]");
    const extensionField = node("input", "modal-input");
    extensionField.placeholder = ".pdf";
    extensionField.setAttribute("aria-label", "File extension");
    extensionField.required = true;
    const categoryField = node("input", "modal-input");
    categoryField.placeholder = "E-Books";
    categoryField.setAttribute("aria-label", "Folder category");
    categoryField.required = true;
    const addButton = node("button", "modal-button-primary", "Add rule");
    addButton.type = "submit";
    form.append(extensionField, categoryField, addButton);
    const error = node("p", "mt-2 hidden text-xs text-rose-300");
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      error.classList.add("hidden");
      try {
        await window.organizer.addRule(extensionField.value, categoryField.value);
        appendLog({ level: "success", message: `Custom rule saved for ${extensionField.value.trim().toLowerCase()}`, detail: categoryField.value.trim() });
        await openRules();
      } catch (saveError) {
        error.textContent = saveError.message;
        error.classList.remove("hidden");
      }
    });
    const rulesSection = makeModalSection("Saved rules", "Rules are saved locally and used by manual and live organization.");
    rulesSection.classList.add("mt-6");
    if (!Object.keys(rules).length) {
      rulesSection.append(node("p", "mt-2 text-xs text-slate-500", "No custom rules yet. Built-in categories are used by default."));
    }
    for (const [extension, category] of Object.entries(rules).sort(([a], [b]) => a.localeCompare(b))) {
      const row = node("div", "mb-2 flex items-center justify-between rounded-xl border border-white/[0.06] bg-white/[0.025] px-3 py-2.5");
      const label = node("span", "text-sm text-slate-200", `${extension}  →  ${category}`);
      const remove = button("Remove", "modal-button-danger", async () => {
        try {
          await window.organizer.removeRule(extension);
          appendLog({ level: "info", message: `Removed custom rule for ${extension}` });
          await openRules();
        } catch (removeError) {
          window.alert(removeError.message);
        }
      });
      row.append(label, remove);
      rulesSection.append(row);
    }
    content.append(form, error, rulesSection);
    showDialog("Custom rules", "Custom rules override the built-in file categories.", content);
  } catch (error) {
    showDialog("Custom rules", "Could not load saved rules.", node("p", "text-sm text-rose-300", error.message));
  }
}

async function openCleaner() {
  if (!hasDesktopBridge) {
    showDesktopRequired("Duplicate cleaner", "Scan folders and move selected cleanup candidates to Trash.");
    return;
  }
  if (!(await ensureFolderSelected())) return;
  const scanFolder = selectedFolder;
  const content = node("div");
  const intro = node("p", "mb-4 rounded-xl border border-amber-300/15 bg-amber-300/[0.05] p-3 text-xs leading-5 text-amber-100", "Duplicates are detected by SHA-256 after matching file sizes. Cleanup sends selected files to your system Trash/Recycle Bin; it does not permanently erase them.");
  const status = node("p", "mb-3 text-xs text-slate-400", "Scanning folder and subfolders…");
  const list = node("div", "max-h-72 overflow-auto rounded-xl border border-white/[0.07]");
  const controls = node("div", "mt-4 flex flex-wrap items-center justify-between gap-2");
  const total = node("span", "text-xs text-slate-400");
  const selectAll = button("Select all", "modal-button-secondary");
  const cleanButton = button("Move selected to Trash", "modal-button-primary");
  controls.append(total, node("div", "flex gap-2"));
  controls.lastChild.append(selectAll, cleanButton);
  content.append(intro, status, list, controls);
  showDialog("Duplicate cleaner", `Scanning ${scanFolder}`, content);
  let candidates = [];
  const renderCandidates = (result) => {
    candidates = result.candidates;
    list.replaceChildren();
    status.textContent = result.candidates.length
      ? `Found ${result.candidates.length} candidate(s). Review and select what you want to move.`
      : "No duplicate or temporary files found.";
    if (result.errors.length) {
      status.textContent += ` ${result.errors.length} file(s) could not be scanned; see activity console.`;
      result.errors.slice(0, 10).forEach((message) => appendLog({ level: "warning", message: "Cleaner scan skipped an item", detail: message }));
    }
    total.textContent = `${formatSize(result.reclaimableSize)} potentially reclaimable · ${formatSize(result.totalSize)} scanned`;
    for (const candidate of candidates) {
      const row = node("label", "flex cursor-pointer items-center gap-3 border-b border-white/[0.05] px-3 py-3 last:border-0 hover:bg-white/[0.025]");
      const checkbox = node("input", "h-4 w-4 accent-emerald-300");
      checkbox.type = "checkbox";
      checkbox.dataset.path = candidate.path;
      const info = node("span", "min-w-0 flex-1");
      info.append(node("span", "block truncate text-xs text-slate-200", candidate.name));
      info.append(node("span", "mt-1 block truncate text-[10px] text-slate-500", `${candidate.reason} · ${formatSize(candidate.size)} · ${candidate.path}`));
      row.append(checkbox, info);
      list.append(row);
    }
    cleanButton.disabled = candidates.length === 0;
  };
  selectAll.addEventListener("click", () => {
    const boxes = [...list.querySelectorAll('input[type="checkbox"]')];
    const allChecked = boxes.length > 0 && boxes.every((checkbox) => checkbox.checked);
    boxes.forEach((checkbox) => { checkbox.checked = !allChecked; });
    selectAll.textContent = allChecked ? "Select all" : "Select none";
  });
  cleanButton.addEventListener("click", async () => {
    const selected = [...list.querySelectorAll('input[type="checkbox"]:checked')].map((checkbox) => checkbox.dataset.path);
    if (!selected.length) {
      window.alert("Select at least one file to move to Trash.");
      return;
    }
    const selectedSize = candidates.filter((candidate) => selected.includes(candidate.path)).reduce((sum, candidate) => sum + candidate.size, 0);
    if (!window.confirm(`Move ${selected.length} selected file(s) (${formatSize(selectedSize)}) to the system Trash/Recycle Bin?`)) return;
    cleanButton.disabled = true;
    try {
      const result = await window.organizer.moveToTrash(scanFolder, selected);
      appendLog({ level: result.errors.length ? "warning" : "success", message: `Moved ${result.moved} file(s) to Trash`, detail: `${formatSize(result.reclaimedSize)} reclaimed` });
      status.textContent = `Moved ${result.moved} file(s) to Trash (${formatSize(result.reclaimedSize)}).`;
      if (result.errors.length) status.textContent += ` ${result.errors.length} could not be moved.`;
      const updated = await window.organizer.scanCleanup(scanFolder);
      renderCandidates(updated);
      status.textContent = `Moved ${result.moved} file(s) to Trash (${formatSize(result.reclaimedSize)}). ` +
        (updated.candidates.length ? `${updated.candidates.length} candidate(s) remain.` : "No candidates remain.");
    } catch (error) {
      status.textContent = `Cleanup failed: ${error.message}`;
      status.className = "mb-3 text-xs text-rose-300";
    } finally {
      cleanButton.disabled = false;
    }
  });
  try {
    renderCandidates(await window.organizer.scanCleanup(scanFolder));
  } catch (error) {
    status.textContent = `Scan failed: ${error.message}`;
    status.className = "mb-3 text-xs text-rose-300";
  }
}

async function openVault() {
  if (!hasDesktopBridge) {
    showDesktopRequired("Private vault", "Move selected items into the hidden folder inside the desktop app.");
    return;
  }
  if (!(await ensureFolderSelected())) return;
  const vaultFolder = selectedFolder;
  const content = node("div");
  const warning = node("p", "mb-4 rounded-xl border border-amber-300/15 bg-amber-300/[0.05] p-3 text-xs leading-5 text-amber-100", "Hidden-folder mode only: this does not encrypt or password-protect your files. Anyone with access to the folder can reveal and open the vault.");
  const pathLabel = node("p", "mb-4 break-all text-[10px] text-slate-500");
  const columns = node("div", "grid gap-4 md:grid-cols-2");
  const availableSection = makeModalSection("Selected folder");
  const hiddenSection = makeModalSection("Hidden vault");
  const availableList = node("div", "mt-2 max-h-60 overflow-auto rounded-xl border border-white/[0.07]");
  const hiddenList = node("div", "mt-2 max-h-60 overflow-auto rounded-xl border border-white/[0.07]");
  availableSection.append(availableList);
  hiddenSection.append(hiddenList);
  columns.append(availableSection, hiddenSection);
  const status = node("p", "mt-3 text-xs text-slate-500");
  const controls = node("div", "mt-4 flex flex-wrap justify-end gap-2");
  const refresh = button("Refresh", "modal-button-secondary");
  const hide = button("Move selected into vault", "modal-button-primary");
  const restore = button("Restore selected", "modal-button-secondary");
  controls.append(refresh, hide, restore);
  content.append(warning, pathLabel, columns, status, controls);
  showDialog("Private vault", `Contents of ${vaultFolder}`, content);

  const populate = (container, entries, disabledNames = new Set()) => {
    container.replaceChildren();
    if (!entries.length) {
      container.append(node("p", "p-3 text-xs text-slate-500", "Nothing here."));
      return;
    }
    for (const entry of entries) {
      const row = node("label", "flex cursor-pointer items-center gap-2 border-b border-white/[0.05] px-3 py-2.5 last:border-0");
      const checkbox = node("input", "h-4 w-4 accent-emerald-300");
      checkbox.type = "checkbox";
      checkbox.value = entry.name;
      checkbox.disabled = disabledNames.has(entry.name);
      const name = node("span", "min-w-0 flex-1 truncate text-xs text-slate-300", `${entry.name}${entry.isDirectory ? "  [folder]" : ""}`);
      name.title = entry.path;
      row.append(checkbox, name);
      container.append(row);
    }
  };
  const refreshLists = async () => {
    status.textContent = "Loading vault contents…";
    try {
      const result = await window.organizer.listVault(vaultFolder);
      pathLabel.textContent = `Vault location: ${result.vaultPath}`;
      populate(availableList, result.available, new Set([".private_vault"]));
      populate(hiddenList, result.hidden);
      status.textContent = "Select items to move into or restore from the vault.";
    } catch (error) {
      status.textContent = error.message;
      status.className = "mt-3 text-xs text-rose-300";
    }
  };
  const selectedNames = (container) => [...container.querySelectorAll('input[type="checkbox"]:checked')].map((checkbox) => checkbox.value);
  refresh.addEventListener("click", refreshLists);
  hide.addEventListener("click", async () => {
    const names = selectedNames(availableList);
    if (!names.length) {
      window.alert("Select files or folders to move into the vault.");
      return;
    }
    if (!window.confirm(`Move ${names.length} item(s) into the hidden vault? This does not encrypt the files.`)) return;
    try {
      const result = await window.organizer.hideVaultItems(vaultFolder, names);
      appendLog({ level: result.errors.length ? "warning" : "success", message: `Moved ${result.moved.length} item(s) into the vault`, detail: result.errors.join("; ") });
      status.textContent = `Moved ${result.moved.length} item(s) into the vault.${result.errors.length ? ` ${result.errors.length} could not be moved.` : ""}`;
      await refreshLists();
    } catch (error) {
      status.textContent = error.message;
      status.className = "mt-3 text-xs text-rose-300";
    }
  });
  restore.addEventListener("click", async () => {
    const names = selectedNames(hiddenList);
    if (!names.length) {
      window.alert("Select vault items to restore.");
      return;
    }
    try {
      const result = await window.organizer.restoreVaultItems(vaultFolder, names);
      appendLog({ level: result.errors.length ? "warning" : "success", message: `Restored ${result.moved.length} vault item(s)`, detail: result.errors.join("; ") });
      status.textContent = `Restored ${result.moved.length} item(s).${result.errors.length ? ` ${result.errors.length} could not be restored.` : ""}`;
      await refreshLists();
    } catch (error) {
      status.textContent = error.message;
      status.className = "mt-3 text-xs text-rose-300";
    }
  });
  await refreshLists();
}

async function toggleWatcher(kind) {
  if (!hasDesktopBridge) {
    showDesktopRequired(
      kind === "images" ? "Image auto-sort" : "Live file watcher",
      "Background file watching is available in the Electron desktop app."
    );
    return;
  }
  if (activeWatcher.running && activeWatcher.kind === kind) {
    try {
      activeWatcher = await window.organizer.stopWatcher();
      appendLog({ level: "info", message: "Folder watcher stopped" });
      refreshWatcherUi();
      setStatus("Watcher stopped");
    } catch (error) {
      appendLog({ level: "error", message: "Could not stop folder watcher", detail: error.message });
    }
    return;
  }
  if (activeWatcher.running) return;
  if (!(await ensureFolderSelected())) return;
  try {
    activeWatcher = await window.organizer.startWatcher(kind, selectedFolder, selectedFolder);
    refreshWatcherUi();
    setStatus(kind === "images" ? "Image auto-sort active" : "Live file watcher active");
  } catch (error) {
    appendLog({ level: "error", message: "Could not start folder watcher", detail: error.message });
    window.alert(`Could not start watcher: ${error.message}`);
  }
}

elements.selectFolder.addEventListener("click", chooseFolder);
elements.changeFolder.addEventListener("click", chooseFolder);
elements.dropZone.addEventListener("click", chooseFolder);
elements.organizeNow.addEventListener("click", organizeSelectedFolder);
elements.clearLogs.addEventListener("click", () => {
  elements.activityLog.replaceChildren();
  appendLog({ level: "info", message: "Console cleared" });
});
elements.pageBack.addEventListener("click", showDashboard);

document.getElementById("nav-activity").addEventListener("click", openActivity);
document.getElementById("nav-rules").addEventListener("click", openRules);
document.getElementById("nav-cleaner").addEventListener("click", openCleaner);
document.getElementById("nav-vault").addEventListener("click", openVault);
document.getElementById("action-activity").addEventListener("click", openActivity);
document.getElementById("action-rules").addEventListener("click", openRules);
document.getElementById("action-cleaner").addEventListener("click", openCleaner);
document.getElementById("action-vault").addEventListener("click", openVault);
document.getElementById("nav-overview").addEventListener("click", showDashboard);
elements.autoSortButton.addEventListener("click", () => toggleWatcher("images"));
elements.liveWatchButton.addEventListener("click", () => toggleWatcher("organizer"));

elements.dropZone.addEventListener("dragover", (event) => {
  event.preventDefault();
  elements.dropZone.classList.add("drop-active");
});
elements.dropZone.addEventListener("dragleave", (event) => {
  if (!elements.dropZone.contains(event.relatedTarget)) {
    elements.dropZone.classList.remove("drop-active");
  }
});
elements.dropZone.addEventListener("drop", (event) => {
  event.preventDefault();
  elements.dropZone.classList.remove("drop-active");
  const files = Array.from(event.dataTransfer.files);
  if (!files.length) {
    appendLog({ level: "warning", message: "No files found in drop." });
    return;
  }
  organizeDroppedFiles(files);
});

if (hasDesktopBridge) {
  removeLogListener = window.organizer.onLog(appendLog);
  removeWatcherStatusListener = window.organizer.onWatcherStatus((status) => {
    activeWatcher = status;
    refreshWatcherUi();
  });
  window.organizer.getWatcherStatus()
    .then((status) => {
      activeWatcher = status;
      refreshWatcherUi();
    })
    .catch((error) => appendLog({ level: "error", message: "Could not load watcher state", detail: error.message }));
} else {
  setStatus("Browser preview");
  elements.selectFolder.disabled = false;
  elements.changeFolder.disabled = false;
  elements.dropZone.disabled = false;
  elements.organizeNow.disabled = false;
  elements.consoleFooter.textContent = "Preview only — launch the desktop app to access your files.";
  appendLog({
    level: "warning",
    message: "Browser preview mode",
    detail: "Open the project with npm start to use file and folder features."
  });
  refreshWatcherUi();
}

window.addEventListener("beforeunload", () => {
  if (removeLogListener) {
    removeLogListener();
  }
  if (removeWatcherStatusListener) {
    removeWatcherStatusListener();
  }
});
