const crypto = require("node:crypto");
const { constants } = require("node:fs");
const fs = require("node:fs/promises");
const path = require("node:path");

const FILE_CATEGORIES = new Map([
  [".jpg", "Images"],
  [".jpeg", "Images"],
  [".png", "Images"],
  [".gif", "Images"],
  [".bmp", "Images"],
  [".svg", "Images"],
  [".webp", "Images"],
  [".pdf", "Documents"],
  [".doc", "Documents"],
  [".docx", "Documents"],
  [".txt", "Documents"],
  [".rtf", "Documents"],
  [".xls", "Documents"],
  [".xlsx", "Documents"],
  [".ppt", "Documents"],
  [".pptx", "Documents"],
  [".csv", "Documents"],
  [".mp4", "Videos"],
  [".mkv", "Videos"],
  [".flv", "Videos"],
  [".avi", "Videos"],
  [".mov", "Videos"],
  [".mp3", "Audio"],
  [".wav", "Audio"],
  [".aac", "Audio"],
  [".flac", "Audio"],
  [".zip", "Archives"],
  [".rar", "Archives"],
  [".7z", "Archives"],
  [".tar", "Archives"],
  [".gz", "Archives"],
  [".py", "Code"],
  [".js", "Code"],
  [".html", "Code"],
  [".css", "Code"],
  [".json", "Code"],
  [".cpp", "Code"],
  [".c", "Code"],
  [".php", "Code"],
  [".exe", "Executables"],
  [".msi", "Executables"],
  [".dmg", "Executables"]
]);

const JUNK_EXTENSIONS = new Set([".tmp", ".temp", ".cache"]);
const VAULT_DIRECTORY_NAME = ".private_vault";
const INVALID_CATEGORY_CHARACTERS = /[<>:"/\\|?*\x00-\x1f]/;
const WINDOWS_RESERVED_NAMES = new Set([
  "CON", "PRN", "AUX", "NUL",
  ...Array.from({ length: 9 }, (_, index) => `COM${index + 1}`),
  ...Array.from({ length: 9 }, (_, index) => `LPT${index + 1}`)
]);

function isWithin(parent, candidate) {
  const relative = path.relative(parent, candidate);
  return relative !== "" && !relative.startsWith(`..${path.sep}`) && relative !== ".." && !path.isAbsolute(relative);
}

function validateRule(extension, category) {
  if (typeof extension !== "string" || typeof category !== "string") {
    throw new TypeError("Extension and category must be text.");
  }
  const normalizedExtension = extension.trim().toLowerCase();
  const normalizedCategory = category.trim();
  if (!/^\.[a-z0-9][a-z0-9_-]*$/.test(normalizedExtension)) {
    throw new Error("Extension must look like .pdf or .zip.");
  }
  if (
    !normalizedCategory ||
    normalizedCategory === "." ||
    normalizedCategory === ".." ||
    normalizedCategory.toLowerCase() === VAULT_DIRECTORY_NAME ||
    /[. ]$/.test(normalizedCategory) ||
    INVALID_CATEGORY_CHARACTERS.test(normalizedCategory) ||
    WINDOWS_RESERVED_NAMES.has(normalizedCategory.split(".", 1)[0].toUpperCase())
  ) {
    throw new Error("Enter a valid folder name for the category.");
  }
  return [normalizedExtension, normalizedCategory];
}

function createFileService({ userDataDirectory, emitLog, trashItem }) {
  const rulesPath = path.join(userDataDirectory, "custom_rules.json");
  const historyPath = path.join(userDataDirectory, "activity.json");

  async function readJson(filePath, fallback, description) {
    try {
      return JSON.parse(await fs.readFile(filePath, "utf8"));
    } catch (error) {
      if (error.code === "ENOENT") {
        return fallback;
      }
      if (error instanceof SyntaxError) {
        throw new Error(`${description} contains invalid JSON: ${error.message}`);
      }
      throw new Error(`Could not read ${description}: ${error.message}`);
    }
  }

  async function writeJson(filePath, data, description) {
    await fs.mkdir(userDataDirectory, { recursive: true });
    const temporaryPath = `${filePath}.${crypto.randomUUID()}.tmp`;
    try {
      await fs.writeFile(temporaryPath, `${JSON.stringify(data, null, 2)}\n`, {
        encoding: "utf8",
        flag: "wx"
      });
      await fs.rename(temporaryPath, filePath);
    } catch (error) {
      try {
        await fs.unlink(temporaryPath);
      } catch (cleanupError) {
        if (cleanupError.code !== "ENOENT") {
          throw new Error(
            `${description} could not be saved (${error.message}); temporary data could not be removed (${cleanupError.message}).`
          );
        }
      }
      throw new Error(`Could not save ${description}: ${error.message}`);
    }
  }

  async function getRules() {
    const document = await readJson(rulesPath, { version: 1, rules: [] }, "custom rules");
    if (!document || document.version !== 1 || !Array.isArray(document.rules)) {
      throw new Error("Custom rules file has an unsupported format.");
    }
    const rules = {};
    for (const [index, entry] of document.rules.entries()) {
      if (!entry || typeof entry.extension !== "string" || typeof entry.category !== "string") {
        throw new Error(`Custom rule #${index + 1} is invalid.`);
      }
      const [extension, category] = validateRule(entry.extension, entry.category);
      if (Object.hasOwn(rules, extension)) {
        throw new Error(`Duplicate custom rule for ${extension}.`);
      }
      rules[extension] = category;
    }
    return rules;
  }

  async function saveRules(rules) {
    const entries = Object.entries(rules)
      .map(([extension, category]) => {
        const [normalizedExtension, normalizedCategory] = validateRule(extension, category);
        return [normalizedExtension, normalizedCategory];
      })
      .sort(([left], [right]) => left.localeCompare(right));
    const uniqueRules = new Map(entries);
    if (uniqueRules.size !== entries.length) {
      throw new Error("Each file extension can only have one custom rule.");
    }
    await writeJson(
      rulesPath,
      {
        version: 1,
        rules: entries.map(([extension, category]) => ({ extension, category }))
      },
      "custom rules"
    );
    return Object.fromEntries(entries);
  }

  async function recordOrganized(items, actionId) {
    if (items.length === 0) {
      return;
    }
    const history = await readJson(historyPath, [], "activity history");
    if (!Array.isArray(history)) {
      throw new Error("Activity history file has an unsupported format.");
    }
    const occurredAt = new Date().toISOString();
    for (const item of items) {
      history.push({
        actionId,
        occurredAt,
        source: item.source,
        destination: item.destination,
        category: item.category,
        undone: false
      });
    }
    await writeJson(historyPath, history, "activity history");
  }

  async function uniqueDestination(directory, filename) {
    const parsed = path.parse(filename);
    for (let counter = 0; ; counter += 1) {
      const suffix = counter === 0 ? "" : ` (${counter})`;
      const destination = path.join(directory, `${parsed.name}${suffix}${parsed.ext}`);
      try {
        await fs.lstat(destination);
      } catch (error) {
        if (error.code === "ENOENT") {
          return destination;
        }
        throw error;
      }
    }
  }

  async function copyWithoutOverwrite(source, directory) {
    await fs.mkdir(directory, { recursive: true });
    for (;;) {
      const destination = await uniqueDestination(directory, path.basename(source));
      try {
        await fs.copyFile(source, destination, fs.constants.COPYFILE_EXCL);
        return destination;
      } catch (error) {
        if (error.code === "EEXIST") {
          continue;
        }
        throw error;
      }
    }
  }

  async function moveFile(filePath, rules) {
    if (typeof filePath !== "string" || !path.isAbsolute(filePath)) {
      throw new Error("Invalid file path received.");
    }
    const source = path.resolve(filePath);
    const sourceInfo = await fs.lstat(source);
    if (sourceInfo.isSymbolicLink() || !sourceInfo.isFile()) {
      throw new Error("Only regular, non-symlink files can be organized.");
    }
    const extension = path.extname(source).toLowerCase();
    const category = rules[extension] ?? FILE_CATEGORIES.get(extension) ?? "Others";
    const destinationDirectory = path.join(path.dirname(source), category);
    if (path.dirname(source) === destinationDirectory) {
      return { source, destination: source, category, skipped: true };
    }
    const destination = await copyWithoutOverwrite(source, destinationDirectory);
    try {
      await fs.unlink(source);
    } catch (error) {
      try {
        await fs.unlink(destination);
      } catch (cleanupError) {
        if (cleanupError.code !== "ENOENT") {
          throw new Error(
            `Original file could not be removed (${error.message}); copied file remains at ${destination} (${cleanupError.message}).`
          );
        }
      }
      throw error;
    }
    return { source, destination, category };
  }

  async function organizePaths(filePaths) {
    if (!Array.isArray(filePaths)) {
      throw new Error("File paths must be provided as a list.");
    }
    const rules = await getRules();
    const actionId = crypto.randomUUID();
    const results = [];
    const errors = [];
    for (const filePath of filePaths) {
      try {
        const item = await moveFile(filePath, rules);
        if (!item.skipped) {
          results.push(item);
          emitLog("success", `Organized ${path.basename(item.source)}`, `${item.category} · ${item.destination}`);
        } else {
          emitLog("info", `${path.basename(item.source)} is already in its category folder`);
        }
      } catch (error) {
        const message = error.message || String(error);
        errors.push({ path: String(filePath), message });
        emitLog("error", `Could not organize ${path.basename(String(filePath))}`, message);
      }
    }
    try {
      await recordOrganized(results, actionId);
    } catch (historyError) {
      const rollbackErrors = [];
      for (const item of [...results].reverse()) {
        try {
          await fs.access(item.source).then(() => {
            throw new Error(`Original path is occupied: ${item.source}`);
          }, async (error) => {
            if (error.code !== "ENOENT") {
              throw error;
            }
            await fs.rename(item.destination, item.source);
          });
        } catch (rollbackError) {
          rollbackErrors.push(`${item.destination}: ${rollbackError.message}`);
        }
      }
      if (rollbackErrors.length) {
        throw new Error(
          `Activity history could not be saved (${historyError.message}). Some files could not be restored: ${rollbackErrors.join("; ")}`
        );
      }
      throw new Error(`Activity history could not be saved. Moved files were restored: ${historyError.message}`);
    }
    return { moved: results.length, results, errors };
  }

  async function getActivity() {
    const entries = await readJson(historyPath, [], "activity history");
    if (!Array.isArray(entries)) {
      throw new Error("Activity history file has an unsupported format.");
    }
    const categories = {};
    for (const entry of entries) {
      categories[entry.category] = (categories[entry.category] ?? 0) + 1;
    }
    const latestAction = [...entries].reverse().find((entry) => !entry.undone)?.actionId;
    const undoCount = latestAction
      ? entries.filter((entry) => entry.actionId === latestAction && !entry.undone).length
      : 0;
    return {
      total: entries.length,
      categories,
      entries: entries.slice(-200).reverse(),
      undoCount
    };
  }

  async function undoLatest() {
    const entries = await readJson(historyPath, [], "activity history");
    if (!Array.isArray(entries)) {
      throw new Error("Activity history file has an unsupported format.");
    }
    const latest = [...entries].reverse().find((entry) => !entry.undone);
    if (!latest) {
      return { restored: 0, errors: [] };
    }
    const actionEntries = entries
      .map((entry, index) => ({ entry, index }))
      .filter(({ entry }) => entry.actionId === latest.actionId && !entry.undone)
      .reverse();
    let restored = 0;
    const errors = [];
    for (const { entry, index } of actionEntries) {
      try {
        await fs.lstat(entry.source).then(
          () => {
            throw new Error(`Restore path already exists: ${entry.source}`);
          },
          async (error) => {
            if (error.code !== "ENOENT") {
              throw error;
            }
            const info = await fs.lstat(entry.destination);
            if (info.isSymbolicLink() || !info.isFile()) {
              throw new Error(`Organized file is missing or not a regular file: ${entry.destination}`);
            }
            await fs.rename(entry.destination, entry.source);
          }
        );
        entries[index] = { ...entry, undone: true, undoneAt: new Date().toISOString() };
        try {
          await writeJson(historyPath, entries, "activity history");
        } catch (historyError) {
          try {
            await fs.rename(entry.source, entry.destination);
          } catch (rollbackError) {
            errors.push(
              `${entry.source}: history update failed and the file remains restored because rollback failed (${rollbackError.message}).`
            );
            continue;
          }
          entries[index] = entry;
          errors.push(`${entry.source}: history update failed (${historyError.message}).`);
          continue;
        }
        restored += 1;
      } catch (error) {
        errors.push(`${entry.source}: ${error.message}`);
      }
    }
    return { restored, errors };
  }

  async function sha256(filePath) {
    const hash = crypto.createHash("sha256");
    const handle = await fs.open(filePath, "r");
    try {
      const buffer = Buffer.allocUnsafe(1024 * 1024);
      for (;;) {
        const { bytesRead } = await handle.read(buffer, 0, buffer.length, null);
        if (bytesRead === 0) {
          break;
        }
        hash.update(buffer.subarray(0, bytesRead));
      }
    } finally {
      await handle.close();
    }
    return hash.digest("hex");
  }

  async function scanCleanup(folder) {
    const root = path.resolve(folder);
    const rootInfo = await fs.stat(root);
    if (!rootInfo.isDirectory()) {
      throw new Error("Select a folder to scan.");
    }
    const filesBySize = new Map();
    const reasons = new Map();
    const sizesByPath = new Map();
    let totalSize = 0;
    const errors = [];
    const pending = [root];
    while (pending.length) {
      const directory = pending.pop();
      let entries;
      try {
        entries = await fs.readdir(directory, { withFileTypes: true });
      } catch (error) {
        errors.push(`${directory}: ${error.message}`);
        continue;
      }
      for (const entry of entries) {
        const filePath = path.join(directory, entry.name);
        try {
          if (entry.isSymbolicLink()) {
            continue;
          }
          if (entry.isDirectory()) {
            pending.push(filePath);
            continue;
          }
          if (!entry.isFile()) {
            continue;
          }
          const info = await fs.stat(filePath);
          totalSize += info.size;
          sizesByPath.set(filePath, info.size);
          if (!filesBySize.has(info.size)) {
            filesBySize.set(info.size, []);
          }
          filesBySize.get(info.size).push({ path: filePath, size: info.size });
          if (
            JUNK_EXTENSIONS.has(path.extname(entry.name).toLowerCase()) ||
            entry.name.endsWith("~") ||
            entry.name.startsWith("~$")
          ) {
            reasons.set(filePath, new Set(["Temporary file"]));
          }
        } catch (error) {
          errors.push(`${filePath}: ${error.message}`);
        }
      }
    }
    for (const sameSizeFiles of filesBySize.values()) {
      if (sameSizeFiles.length < 2) {
        continue;
      }
      const hashes = new Map();
      for (const file of sameSizeFiles) {
        try {
          const hash = await sha256(file.path);
          if (!hashes.has(hash)) {
            hashes.set(hash, []);
          }
          hashes.get(hash).push(file);
        } catch (error) {
          errors.push(`${file.path}: ${error.message}`);
        }
      }
      for (const sameHashFiles of hashes.values()) {
        if (sameHashFiles.length < 2) {
          continue;
        }
        for (const duplicate of sameHashFiles.sort((a, b) => a.path.localeCompare(b.path)).slice(1)) {
          if (!reasons.has(duplicate.path)) {
            reasons.set(duplicate.path, new Set());
          }
          reasons.get(duplicate.path).add("Duplicate copy");
        }
      }
    }
    const candidates = [...reasons.entries()]
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([filePath, fileReasons]) => ({
        path: filePath,
        name: path.basename(filePath),
        size: sizesByPath.get(filePath) ?? 0,
        reason: [...fileReasons].sort().join(", ")
      }));
    return {
      root,
      totalSize,
      candidates,
      reclaimableSize: candidates.reduce((total, file) => total + file.size, 0),
      errors
    };
  }

  async function moveToTrash(folder, selectedPaths) {
    if (!Array.isArray(selectedPaths)) {
      throw new Error("Select the cleanup candidates to move to Trash.");
    }
    const root = path.resolve(folder);
    const rootInfo = await fs.stat(root);
    if (!rootInfo.isDirectory()) {
      throw new Error("The scan folder no longer exists.");
    }
    const moved = [];
    const errors = [];
    for (const filePath of selectedPaths) {
      try {
        if (typeof filePath !== "string" || !isWithin(root, path.resolve(filePath))) {
          throw new Error("Selected item is outside the scanned folder.");
        }
        const info = await fs.lstat(filePath);
        if (info.isSymbolicLink() || !info.isFile()) {
          throw new Error("File no longer exists or is not a regular file.");
        }
        await trashItem(filePath);
        moved.push({ path: filePath, size: info.size });
      } catch (error) {
        errors.push(`${filePath}: ${error.message}`);
      }
    }
    return {
      moved: moved.length,
      reclaimedSize: moved.reduce((total, item) => total + item.size, 0),
      errors
    };
  }

  async function vaultDirectory(folder, create = false) {
    const root = path.resolve(folder);
    const info = await fs.stat(root);
    if (!info.isDirectory()) {
      throw new Error("Select a folder to open its private vault.");
    }
    const vault = path.join(root, VAULT_DIRECTORY_NAME);
    try {
      const vaultInfo = await fs.lstat(vault);
      if (vaultInfo.isSymbolicLink() || !vaultInfo.isDirectory()) {
        throw new Error(`Vault path is not a folder: ${vault}`);
      }
    } catch (error) {
      if (error.code !== "ENOENT" || !create) {
        if (error.code === "ENOENT" && !create) {
          return null;
        }
        throw error;
      }
      await fs.mkdir(vault);
      if (process.platform === "win32") {
        const { execFile } = require("node:child_process");
        await new Promise((resolve, reject) => {
          execFile("attrib.exe", ["+h", vault], (execError) => {
            if (execError) {
              reject(execError);
            } else {
              resolve();
            }
          });
        });
      }
    }
    return { root, vault };
  }

  async function listVault(folder) {
    const paths = await vaultDirectory(folder);
    if (!paths) {
      return { available: [], hidden: [], vaultPath: path.join(path.resolve(folder), VAULT_DIRECTORY_NAME) };
    }
    const [available, hidden] = await Promise.all([
      fs.readdir(paths.root, { withFileTypes: true }),
      fs.readdir(paths.vault, { withFileTypes: true })
    ]);
    const listEntries = (entries, directory) =>
      entries
        .filter((entry) => entry.isFile() || entry.isDirectory())
        .filter((entry) => !entry.isSymbolicLink() && entry.name !== VAULT_DIRECTORY_NAME)
        .map((entry) => ({
          name: entry.name,
          isDirectory: entry.isDirectory(),
          path: path.join(directory, entry.name)
        }))
        .sort((left, right) => left.name.localeCompare(right.name));
    return {
      available: listEntries(available, paths.root),
      hidden: listEntries(hidden, paths.vault),
      vaultPath: paths.vault
    };
  }

  async function moveVaultItems(folder, selectedNames, restore) {
    if (!Array.isArray(selectedNames)) {
      throw new Error("Select the vault items first.");
    }
    const paths = await vaultDirectory(folder, !restore);
    if (!paths) {
      return { moved: [], errors: ["The vault folder does not exist."] };
    }
    const sourceDirectory = restore ? paths.vault : paths.root;
    const destinationDirectory = restore ? paths.root : paths.vault;
    const moved = [];
    const errors = [];
    for (const name of selectedNames) {
      try {
        if (
          typeof name !== "string" ||
          !name ||
          name === "." ||
          name === ".." ||
          name.includes("/") ||
          name.includes("\\") ||
          (!restore && name === VAULT_DIRECTORY_NAME)
        ) {
          throw new Error(`Only direct child names can be moved: ${String(name)}`);
        }
        const source = path.join(sourceDirectory, name);
        const info = await fs.lstat(source);
        if (info.isSymbolicLink() || (!info.isFile() && !info.isDirectory())) {
          throw new Error(`Not a movable direct file or folder: ${source}`);
        }
        const destination = await uniqueDestination(destinationDirectory, name);
        await fs.rename(source, destination);
        moved.push({ source, destination });
      } catch (error) {
        errors.push(`${String(name)}: ${error.message}`);
      }
    }
    return { moved, errors };
  }

  return {
    organizeFolder: async (folder) => {
      const root = path.resolve(folder);
      const info = await fs.stat(root);
      if (!info.isDirectory()) {
        throw new Error("Select a valid folder first.");
      }
      const entries = await fs.readdir(root, { withFileTypes: true });
      const files = entries.filter((entry) => entry.isFile()).map((entry) => path.join(root, entry.name));
      return organizePaths(files);
    },
    organizeDroppedFiles: organizePaths,
    organizeImage: async (source, destination) => {
      const sourceInfo = await fs.lstat(source);
      if (sourceInfo.isSymbolicLink() || !sourceInfo.isFile()) {
        throw new Error("Image is no longer a regular file.");
      }
      const target = await copyWithoutOverwrite(source, destination);
      try {
        await fs.unlink(source);
      } catch (error) {
        try {
          await fs.unlink(target);
        } catch (cleanupError) {
          if (cleanupError.code !== "ENOENT") {
            throw new Error(`Could not restore ${source}: ${cleanupError.message}`);
          }
        }
        throw error;
      }
      const item = { source, destination: target, category: "Screenshots" };
      try {
        await recordOrganized([item], crypto.randomUUID());
      } catch (error) {
        try {
          await fs.rename(target, source);
        } catch (rollbackError) {
          throw new Error(`History could not be saved and image remains at ${target}: ${rollbackError.message}`);
        }
        throw error;
      }
      emitLog("success", `Sorted ${path.basename(source)}`, `Screenshots · ${target}`);
      return item;
    },
    getActivity,
    undoLatest,
    getRules,
    addRule: async (extension, category) => {
      const [normalizedExtension, normalizedCategory] = validateRule(extension, category);
      const rules = await getRules();
      if (Object.hasOwn(rules, normalizedExtension)) {
        throw new Error(`A rule for ${normalizedExtension} already exists.`);
      }
      rules[normalizedExtension] = normalizedCategory;
      return saveRules(rules);
    },
    removeRule: async (extension) => {
      const rules = await getRules();
      if (!Object.hasOwn(rules, extension)) {
        throw new Error(`No custom rule exists for ${extension}.`);
      }
      delete rules[extension];
      return saveRules(rules);
    },
    scanCleanup,
    moveToTrash,
    listVault,
    hideVaultItems: (folder, names) => moveVaultItems(folder, names, false),
    restoreVaultItems: (folder, names) => moveVaultItems(folder, names, true)
  };
}

module.exports = { createFileService };
