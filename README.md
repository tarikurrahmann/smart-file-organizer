# Smart File Organizer

> **Less clutter. More room to think.**
>
> Bring order to busy folders, let new files find their place, and stay in control of every change.

Smart File Organizer is a local-first desktop app for sorting and managing files on your computer. Choose a folder, let the organizer group files by type, and use optional tools to watch incoming files, find exact duplicates, tuck items away, and undo recent organization.

Your selected files are processed on your device; the desktop apps do not upload them to a cloud service.

## How it works

### 1. Choose a folder or drop in files

Open the desktop app and select a folder such as Downloads or Desktop, then choose **Organize now**. The app sorts regular files directly inside that folder. Existing subfolders are left in place.

You can also drag individual files into the app. Each dropped file is sorted beside its original location, so files from different folders go back into category folders beside themselves.

### 2. Files are sorted by extension

For each file, the organizer checks its extension and chooses a destination category. Common defaults include:

| Extensions | Category folder |
| --- | --- |
| `.jpg`, `.jpeg`, `.png`, `.gif`, `.bmp`, `.svg`, `.webp` | `Images` |
| `.pdf`, `.doc`, `.docx`, `.txt`, `.xlsx`, `.pptx`, `.csv` | `Documents` |
| `.mp4`, `.mkv`, `.flv`, `.avi`, `.mov` | `Videos` |
| `.mp3`, `.wav`, `.aac`, `.flac` | `Audio` |
| `.zip`, `.rar`, `.7z`, `.tar`, `.gz` | `Archives` |
| `.py`, `.js`, `.html`, `.css`, `.json`, `.cpp`, `.c`, `.php` | `Code` |
| `.exe`, `.msi` | `Executables` |
| Any other extension | `Others` |

The category folder is created beside the file if it does not already exist. The exact built-in extension list can vary slightly between the Electron and Python implementations. Custom extension rules override built-in categories—for example, a rule can send `.psd` files to `Design`.

The organizer does not overwrite a file that already has the same name at the destination. It adds a number to the incoming filename instead. Folders and symbolic links are not treated as ordinary files to organize.

### 3. Watch for new files (optional)

Turn on the live folder watcher when you want new arrivals sorted automatically. The watcher runs while the desktop app is open. It waits until a file's size and modification time have stopped changing before moving it, helping avoid files that are still downloading or being saved. Recognized partial-download files are skipped.

Image auto-sort is a separate watcher for incoming images. Choose a destination root and new images are placed in year and date folders, such as:

```text
Screenshots_2026/
└── 2026-10-31/
    └── photo.png
```

Watchers are optional and can be stopped in the app. Only one watcher mode runs at a time.

### 4. Review duplicates and likely junk

The cleanup scanner searches the selected folder and its subfolders. It first groups files by size, then compares same-size files using SHA-256 hashes. A matching hash identifies an exact content duplicate; matching filenames alone are not enough.

The scanner also flags common temporary files, including `.tmp`, `.temp`, `.cache`, editor backup files ending in `~`, and Office lock files beginning with `~$`.

Scanning only reports candidates—it does not remove anything automatically. Review the reasons and select what you want to clean up. Confirmed items are sent to the operating system's Recycle Bin or Trash rather than being silently erased by the organizer.

### 5. Move selected items into the private vault

The vault moves chosen files or folders into a `.private_vault` directory inside the selected folder. You can list the stored items and restore selected ones later. On Windows, the app marks the vault folder as hidden.

**The vault is for organization, not security.** It does not encrypt files, require a password, or prevent another person or application from opening them. Use device encryption for sensitive information.

### 6. Review activity and undo

After organization, the app saves a local record of each move, including the original path, new path, category, and time. The activity view shows recent operations and category totals.

Undo reverses the most recent organization action by returning its files to their original locations. Before restoring, the app checks that the original path is available and that the organized file still exists. If there is a conflict, it reports the problem instead of overwriting another file.

## Two independent desktop apps

This repository contains two implementations with their own user interfaces and file-operation code:

| Desktop app | Technology | File operations |
| --- | --- | --- |
| Electron app | Electron, JavaScript, Tailwind CSS | Electron's main process performs file operations through a restricted preload bridge. |
| Python app | Python, PyQt6, Watchdog | The standalone Python GUI calls its own organizer, watcher, cleanup, activity, and vault modules. |

The Electron app does not launch or depend on the Python app. The hosted website is a landing page; organizing files requires one of the desktop apps.

## Run the desktop app

### Electron

Install Node.js 20 or newer, then run these commands from the repository root:

```powershell
npm install
npm start
```

### Python

Install Python and the dependencies, then run:

```powershell
pip install -r requirements.txt
python main.py
```

## Build Windows packages

From the repository root, run:

```powershell
npm run dist
```

The build creates a portable executable, a ZIP archive, and a Windows setup installer in `dist/`. The setup installer can create Desktop and Start Menu shortcuts.

The Windows builds are unsigned. Windows Smart App Control may show a warning when launching them.

## License

This project is available under the [MIT License](LICENSE).
