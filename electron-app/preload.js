const { contextBridge, ipcRenderer, webUtils } = require("electron");

contextBridge.exposeInMainWorld("organizer", {
  selectFolder: () => ipcRenderer.invoke("organizer:select-folder"),
  organizeFolder: (folderPath) =>
    ipcRenderer.invoke("organizer:organize-folder", folderPath),
  organizeDroppedFiles: (files) => {
    const paths = files.map((file) => webUtils.getPathForFile(file));
    return ipcRenderer.invoke("organizer:organize-dropped", paths);
  },
  getActivity: () => ipcRenderer.invoke("organizer:activity"),
  undoLatest: () => ipcRenderer.invoke("organizer:undo"),
  getRules: () => ipcRenderer.invoke("organizer:rules"),
  addRule: (extension, category) =>
    ipcRenderer.invoke("organizer:add-rule", extension, category),
  removeRule: (extension) => ipcRenderer.invoke("organizer:remove-rule", extension),
  scanCleanup: (folderPath) =>
    ipcRenderer.invoke("organizer:scan-cleanup", folderPath),
  moveToTrash: (folderPath, filePaths) =>
    ipcRenderer.invoke("organizer:trash-cleanup", folderPath, filePaths),
  listVault: (folderPath) => ipcRenderer.invoke("organizer:vault-list", folderPath),
  hideVaultItems: (folderPath, names) =>
    ipcRenderer.invoke("organizer:vault-hide", folderPath, names),
  restoreVaultItems: (folderPath, names) =>
    ipcRenderer.invoke("organizer:vault-restore", folderPath, names),
  getWatcherStatus: () => ipcRenderer.invoke("organizer:watcher-status"),
  startWatcher: (kind, folderPath, destinationPath) =>
    ipcRenderer.invoke("organizer:watcher-start", kind, folderPath, destinationPath),
  stopWatcher: () => ipcRenderer.invoke("organizer:watcher-stop"),
  onLog: (callback) => {
    if (typeof callback !== "function") {
      throw new TypeError("Log callback must be a function.");
    }
    const listener = (_event, entry) => callback(entry);
    ipcRenderer.on("organizer:log", listener);
    return () => ipcRenderer.removeListener("organizer:log", listener);
  },
  onWatcherStatus: (callback) => {
    if (typeof callback !== "function") {
      throw new TypeError("Watcher status callback must be a function.");
    }
    const listener = (_event, status) => callback(status);
    ipcRenderer.on("organizer:watcher-status", listener);
    return () => ipcRenderer.removeListener("organizer:watcher-status", listener);
  }
});
