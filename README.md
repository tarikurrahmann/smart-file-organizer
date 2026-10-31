# Smart File Organizer

> **Less clutter. More room to think.**
>
> A calmer home for your files: sort the busy folders, keep an eye on new downloads, and stay in control of every change.

[![Windows x64](https://img.shields.io/badge/platform-Windows%20x64-0f766e)](https://github.com/tarikurrahmann/smart-file-organizer/releases)
[![MIT License](https://img.shields.io/badge/license-MIT-64748b.svg)](LICENSE)
[![Website](https://img.shields.io/badge/website-live-0e7490)](https://smart-file-org.netlify.app/)

Smart File Organizer turns a crowded folder into a set of clear, type-based folders. Choose when to organize, let the app watch for new files, and review changes afterward. The desktop apps perform file operations on your computer; they do not upload your files to a cloud service.

## How the app works

### 1. Choose what to organize

Open the desktop app and select a folder, such as Downloads or Desktop. You can organize the files in that folder with one click, or drag individual files into the app. Dragged files are organized beside their original location.

For a folder-wide organization, the app processes regular files directly inside the selected folder; it does not sweep through existing subfolders. The duplicate scanner is different: it searches through the selected folder and its subfolders.

### 2. The app decides where each file belongs

The organizer reads each file's extension, such as `.jpg`, `.pdf`, or `.mp4`, and matches it to a category:

| File examples | Destination folder |
| --- | --- |
| `.jpg`, `.png`, `.webp` | `Images` |
| `.pdf`, `.docx`, `.txt`, `.csv` | `Documents` |
| `.mp4`, `.mkv`, `.mov` | `Videos` |
| `.mp3`, `.wav`, `.flac` | `Audio` |
| `.zip`, `.7z`, `.tar` | `Archives` |
| `.py`, `.js`, `.html`, `.css` | `Code` |
| `.exe`, `.msi` | `Executables` |
| Unknown extensions | `Others` |

Custom extension rules take priority over the built-in categories. For example, you can route `.psd` files to a folder named `Design`. If a destination folder does not exist, the app creates it beside the files being organized.

The organizer avoids overwriting existing files. When a file with the same name is already in the destination, it gives the incoming file a numbered name instead. The app processes regular files, skips folders during normal sorting, and refuses symbolic links.

### 3. Follow new files automatically (optional)

If you turn on the live folder watcher, the app watches the selected folder while the desktop app is running. When a new file arrives, the watcher waits for its size and modification time to stop changing before organizing it. This helps avoid moving a download while it is still being written. Known partial-download and temporary-file extensions are ignored by the watcher.

The image auto-sort mode watches for new images and places them in a dated structure, for example:

```text
Screenshots_2026/
└── 2026-10-31/
    └── image.png
```

Choose the destination root when starting image auto-sort. Watchers are optional, run locally, and stop when you stop them or close the desktop app.

### 4. Review duplicates and temporary files

The cleanup scanner searches the selected folder tree and looks for:

- **Exact duplicates:** Files with the same size are compared using SHA-256 content hashes. Matching hashes identify byte-for-byte copies; files are not treated as duplicates based on their names alone.
- **Likely temporary files:** `.tmp`, `.temp`, `.cache`, editor backup files ending in `~`, and Office lock files beginning with `~$`.

The scan shows candidates and their reasons so you can choose what to remove. Nothing is deleted just because a scan found it. When you confirm cleanup, selected files are sent to the operating system's Recycle Bin/Trash, where they can generally be reviewed or restored using the operating system.

### 5. Keep items out of sight with the private vault

Select files or folders and move them into `.private_vault` inside the chosen folder. The app can list vault contents and move selected items back. On Windows, the vault folder is marked hidden.

**The vault is not a security feature:** it does not encrypt files, require a password, or prevent another person or application from accessing them. Use device-level encryption for sensitive data.

### 6. Check activity and undo

After organizing, the app records each move locally with its source, destination, category, and time. The activity view summarizes recent work and category totals. Undo reverses the latest organization action by moving those files back to their original locations.

Undo checks for conflicts before restoring a file. If the original path is already occupied or an organized file is missing, it reports the issue rather than silently overwriting another file. Stop an active watcher before manually organizing or undoing an action.

## The two desktop apps

This repository contains two independent implementations:

| App | Stack | How it works |
| --- | --- | --- |
| Electron desktop | Electron, JavaScript, Tailwind CSS | The interface asks Electron's main process to perform approved file operations through a restricted preload bridge. |
| Python desktop | Python, PyQt6, Watchdog | A standalone desktop app with its own organizer, watcher, activity, cleanup, and vault modules. |

The Electron app does not invoke or depend on the Python app. Both are desktop applications; the hosted website is a landing page and does not organize files in the browser.

## Run the desktop apps

### Run the Electron app

Requirements: Node.js 20 or newer.

```powershell
npm install
npm start
```

### Run the Python app

Requirements: Python and the packages listed in `requirements.txt`.

```powershell
pip install -r requirements.txt
python main.py
```

### Build Windows releases

From the repository root, run:

```powershell
npm run dist
```

The build produces a portable EXE, ZIP archive, and NSIS setup installer in `dist/`. The installer can create Desktop and Start Menu shortcuts. The executables are unsigned, so Windows Smart App Control may show a warning.

## Website and downloads

The live multi-page website is [smart-file-org.netlify.app](https://smart-file-org.netlify.app/). Its Netlify-ready files are in `Netlify/`; `Website/` contains the original site source. The pages are:

- `/` — overview
- `/install/` — downloads, requirements, and quick start
- `/integrations/` — supported local workflows
- `/enterprise/` — current team/enterprise limitations
- `/blog/` — project updates

### Deploy your own copy

Connect this GitHub repository to Netlify and set:

- **Base directory:** `Netlify`
- **Build command:** leave empty
- **Publish directory:** `.`

The Netlify configuration is in `Netlify/netlify.toml`.

To preview the website locally from the repository root:

```powershell
python scripts/serve-website.py
```

Then open <http://127.0.0.1:8765/>.

### Download a release

The Windows builds are larger than 100 MB, so download buttons and the PowerShell installer fetch them from [GitHub Releases](https://github.com/tarikurrahmann/smart-file-organizer/releases). Release assets must keep these exact filenames:

- `Smart.File.Organizer.1.0.0.exe` — portable app
- `Smart.File.Organizer-1.0.0-win.zip` — ZIP archive
- `Smart.File.Organizer.Setup.1.0.0.exe` — setup installer

If a download fails, check that the release is published as the latest release and that the uploaded asset names match exactly.

To install the ZIP build from PowerShell, review [`Netlify/install.ps1`](Netlify/install.ps1) first, then run:

```powershell
irm https://smart-file-org.netlify.app/install.ps1 | iex
```

This runs a remote script that downloads and launches the ZIP build. Only run it if you trust the source. Direct downloads are also available from the website's Install page.

To publish a blog update, edit `Netlify/blog/index.html` and deploy the site again.

## License

This project is licensed under the [MIT License](LICENSE).
