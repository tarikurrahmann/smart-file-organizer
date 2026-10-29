const fs = require("node:fs");
const fsp = require("node:fs/promises");
const path = require("node:path");

const IMAGE_EXTENSIONS = new Set([
  ".avif", ".bmp", ".gif", ".heic", ".heif", ".jpeg", ".jpg",
  ".png", ".tif", ".tiff", ".webp"
]);
const INCOMPLETE_EXTENSIONS = new Set([
  ".crdownload", ".download", ".filepart", ".part", ".partial", ".tmp"
]);

function createWatcherService({ fileService, emitLog, emitStatus = () => {} }) {
  let activeWatcher = null;

  function getStatus() {
    if (!activeWatcher) {
      return { running: false, kind: null, folder: null };
    }
    return {
      running: true,
      kind: activeWatcher.kind,
      folder: activeWatcher.folder,
      destination: activeWatcher.destination
    };
  }

  function stop() {
    if (!activeWatcher) {
      return getStatus();
    }
    const watcher = activeWatcher;
    activeWatcher = null;
    watcher.watching.close();
    for (const timer of watcher.timers.values()) {
      clearTimeout(timer);
    }
    watcher.timers.clear();
    watcher.queued.clear();
    emitStatus(getStatus());
    emitLog("info", `${watcher.kind === "images" ? "Image auto-sort" : "Live file organizer"} stopped`);
    return getStatus();
  }

  async function waitForStableFile(watcher, filePath) {
    let lastSize = -1;
    let lastModified = -1;
    let stableSince = null;
    const deadline = Date.now() + 5 * 60 * 1000;
    while (activeWatcher === watcher && Date.now() < deadline) {
      let info;
      try {
        info = await fsp.lstat(filePath);
      } catch (error) {
        if (error.code === "ENOENT") {
          return false;
        }
        await new Promise((resolve) => setTimeout(resolve, 500));
        continue;
      }
      if (info.isSymbolicLink() || !info.isFile()) {
        return false;
      }
      if (info.size === lastSize && info.mtimeMs === lastModified) {
        stableSince ??= Date.now();
        if (Date.now() - stableSince >= 1500) {
          return true;
        }
      } else {
        lastSize = info.size;
        lastModified = info.mtimeMs;
        stableSince = null;
      }
      await new Promise((resolve) => setTimeout(resolve, 400));
    }
    if (activeWatcher === watcher) {
      emitLog("warning", "Watcher skipped a file that did not finish writing", filePath);
    }
    return false;
  }

  async function processFile(watcher, filePath) {
    try {
      if (!(await waitForStableFile(watcher, filePath)) || activeWatcher !== watcher) {
        return;
      }
      if (watcher.kind === "organizer") {
        const result = await fileService.organizeDroppedFiles([filePath]);
        if (result.errors.length) {
          emitLog("error", `Live organizer could not move ${path.basename(filePath)}`, result.errors[0].message);
        }
        return;
      }
      const now = new Date();
      const day = [
        now.getFullYear(),
        String(now.getMonth() + 1).padStart(2, "0"),
        String(now.getDate()).padStart(2, "0")
      ].join("-");
      const destination = path.join(
        watcher.destination,
        `Screenshots_${now.getFullYear()}`,
        day
      );
      await fsp.mkdir(destination, { recursive: true });
      await fileService.organizeImage(filePath, destination);
    } catch (error) {
      emitLog("error", `Watcher could not process ${path.basename(filePath)}`, error.message);
    } finally {
      watcher.queued.delete(filePath);
      watcher.timers.delete(filePath);
    }
  }

  function enqueue(watcher, filename) {
    if (activeWatcher !== watcher || filename == null) {
      return;
    }
    const fileName = Buffer.isBuffer(filename) ? filename.toString() : String(filename);
    if (!fileName || fileName.includes("/") || fileName.includes("\\")) {
      return;
    }
    const extension = path.extname(fileName).toLowerCase();
    if (watcher.kind === "images" && !IMAGE_EXTENSIONS.has(extension)) {
      return;
    }
    if (
      watcher.kind === "organizer" &&
      (INCOMPLETE_EXTENSIONS.has(extension) || fileName.startsWith("~$"))
    ) {
      return;
    }
    const filePath = path.join(watcher.folder, fileName);
    if (watcher.queued.has(filePath)) {
      clearTimeout(watcher.timers.get(filePath));
    } else {
      watcher.queued.add(filePath);
    }
    watcher.timers.set(filePath, setTimeout(() => processFile(watcher, filePath), 350));
  }

  async function start(kind, folder, destination = folder) {
    if (!["organizer", "images"].includes(kind)) {
      throw new Error("Unknown watcher type.");
    }
    if (activeWatcher) {
      if (activeWatcher.kind === kind && path.resolve(folder) === activeWatcher.folder) {
        return getStatus();
      }
      throw new Error("Stop the active watcher before starting another one.");
    }
    const root = path.resolve(folder);
    const rootInfo = await fsp.stat(root);
    if (!rootInfo.isDirectory()) {
      throw new Error("Choose an existing folder to watch.");
    }
    const target = path.resolve(destination);
    const targetInfo = await fsp.stat(target);
    if (!targetInfo.isDirectory()) {
      throw new Error("Choose an existing destination folder.");
    }
    const watcher = {
      kind,
      folder: root,
      destination: target,
      queued: new Set(),
      timers: new Map(),
      watching: null
    };
    watcher.watching = fs.watch(root, { persistent: true }, (_eventType, filename) => {
      enqueue(watcher, filename);
    });
    watcher.watching.on("error", (error) => {
      emitLog("error", "Folder watcher encountered an error", error.message);
      if (activeWatcher === watcher) {
        stop();
      }
    });
    activeWatcher = watcher;
    emitStatus(getStatus());
    emitLog(
      "success",
      kind === "images" ? "Image auto-sort started" : "Live file organizer started",
      kind === "images"
        ? `Watching ${root}; images go to Screenshots_YEAR/YYYY-MM-DD inside ${target}`
        : `Watching ${root} for new files`
    );
    return getStatus();
  }

  return { start, stop, getStatus };
}

module.exports = { createWatcherService };
