const { app, BrowserWindow, dialog, ipcMain, shell } = require("electron");
const path = require("node:path");
const { createFileService } = require("./file-service");
const { createWatcherService } = require("./watchers");

let mainWindow;
let fileService;
let watcherService;

function emitLog(level, message, detail = "") {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("organizer:log", {
      level,
      message,
      detail,
      time: new Date().toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit"
      })
    });
  }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 900,
    minHeight: 640,
    backgroundColor: "#080d19",
    title: "Smart File Organizer",
    titleBarStyle: "hidden",
    titleBarOverlay: {
      color: "#080d19",
      symbolColor: "#cbd5e1",
      height: 36
    },
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  });

  mainWindow.loadFile(path.join(__dirname, "index.html"));
  mainWindow.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
}

ipcMain.handle("organizer:select-folder", async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: "Choose a folder to organize",
    properties: ["openDirectory", "createDirectory"]
  });
  if (result.canceled || result.filePaths.length === 0) {
    return null;
  }
  emitLog("info", "Folder selected", result.filePaths[0]);
  return result.filePaths[0];
});

ipcMain.handle("organizer:organize-folder", async (_event, folderPath) => {
  if (watcherService.getStatus().running) {
    throw new Error("Stop the active folder watcher before organizing manually.");
  }
  emitLog("info", "Organization started", path.resolve(folderPath));
  const result = await fileService.organizeFolder(folderPath);
  emitLog(
    result.errors.length ? "warning" : "success",
    `Finished · ${result.moved} file(s) organized`,
    result.errors.length ? `${result.errors.length} file(s) could not be moved.` : path.resolve(folderPath)
  );
  return result;
});

ipcMain.handle("organizer:organize-dropped", async (_event, filePaths) => {
  if (watcherService.getStatus().running) {
    throw new Error("Stop the active folder watcher before organizing dropped files.");
  }
  if (!Array.isArray(filePaths)) {
    throw new Error("Dropped file paths must be provided as a list.");
  }
  emitLog("info", "Dropped files received", `${filePaths.length} file(s)`);
  const result = await fileService.organizeDroppedFiles(filePaths);
  emitLog(
    result.errors.length ? "warning" : "success",
    `Finished · ${result.moved} dropped file(s) organized`,
    result.errors.length ? `${result.errors.length} file(s) could not be moved.` : ""
  );
  return result;
});

ipcMain.handle("organizer:activity", () => fileService.getActivity());
ipcMain.handle("organizer:undo", async () => {
  if (watcherService.getStatus().running) {
    throw new Error("Stop the active folder watcher before undoing an action.");
  }
  const result = await fileService.undoLatest();
  emitLog("info", `Undo restored ${result.restored} file(s)`, result.errors.join("; "));
  return result;
});
ipcMain.handle("organizer:rules", () => fileService.getRules());
ipcMain.handle("organizer:add-rule", (_event, extension, category) =>
  fileService.addRule(extension, category)
);
ipcMain.handle("organizer:remove-rule", (_event, extension) =>
  fileService.removeRule(extension)
);
ipcMain.handle("organizer:scan-cleanup", (_event, folder) =>
  fileService.scanCleanup(folder)
);
ipcMain.handle("organizer:trash-cleanup", async (_event, folder, paths) => {
  const result = await fileService.moveToTrash(folder, paths);
  emitLog(
    result.errors.length ? "warning" : "success",
    `Moved ${result.moved} file(s) to Trash`,
    `${result.reclaimedSize} bytes reclaimed`
  );
  return result;
});
ipcMain.handle("organizer:vault-list", (_event, folder) => fileService.listVault(folder));
ipcMain.handle("organizer:vault-hide", async (_event, folder, names) => {
  const result = await fileService.hideVaultItems(folder, names);
  emitLog("info", `Moved ${result.moved.length} item(s) into the vault`, result.errors.join("; "));
  return result;
});
ipcMain.handle("organizer:vault-restore", async (_event, folder, names) => {
  const result = await fileService.restoreVaultItems(folder, names);
  emitLog("info", `Restored ${result.moved.length} vault item(s)`, result.errors.join("; "));
  return result;
});
ipcMain.handle("organizer:watcher-status", () => watcherService.getStatus());
ipcMain.handle("organizer:watcher-start", (_event, kind, folder, destination) =>
  watcherService.start(kind, folder, destination)
);
ipcMain.handle("organizer:watcher-stop", () => watcherService.stop());

app.whenReady().then(() => {
  fileService = createFileService({
    userDataDirectory: app.getPath("userData"),
    emitLog,
    trashItem: (filePath) => shell.trashItem(filePath)
  });
  watcherService = createWatcherService({
    fileService,
    emitLog,
    emitStatus: (status) => {
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send("organizer:watcher-status", status);
      }
    }
  });
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", () => {
  if (watcherService) {
    watcherService.stop();
  }
});
