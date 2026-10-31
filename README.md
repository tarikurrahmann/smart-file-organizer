# Smart File Organizer

> **Less clutter. More room to think.**
>
> A calmer home for your files: sort the busy folders, keep an eye on new downloads, and stay in control of every change.

[![Windows x64](https://img.shields.io/badge/platform-Windows%20x64-0f766e)](https://github.com/tarikurrahmann/smart-file-organizer/releases)
[![MIT License](https://img.shields.io/badge/license-MIT-64748b.svg)](LICENSE)
[![Website](https://img.shields.io/badge/website-live-0e7490)](https://smart-file-org.netlify.app/)

Smart File Organizer is an open-source desktop app for organizing files without sending them to a cloud service. Categorize files, watch folders, find exact duplicates, and review or undo recent changes—all on your device.

## What it can do

- **Sort in a click:** Group common file types into Images, Documents, Videos, Audio, Archives, Code, and more.
- **Watch folders:** Automatically sort new files while the desktop app is running.
- **Find duplicates:** Compare file contents with SHA-256 hashes and review candidates before cleanup.
- **Tidy images:** Sort incoming images into dated folders.
- **Keep a local history:** Review recent activity and undo the latest organization action.
- **Use the private vault:** Move items into `.private_vault` for separation. This is not encryption or password protection.

Files are handled locally. Duplicate cleanup sends selected items to the operating system Trash/Recycle Bin.

## Choose your desktop app

This repository contains two independent implementations:

| App | Stack | How it works |
| --- | --- | --- |
| Electron desktop | Electron, JavaScript, Tailwind CSS | Electron's main process handles file operations through a restricted preload bridge. |
| Python desktop | Python, PyQt6, Watchdog | A standalone desktop app with its own organizer, watcher, activity, cleanup, and vault modules. |

The Electron app does not invoke or depend on the Python app.

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

## [Contributors](https://github.com/tarikurrahmann/smart-file-organizer/graphs/contributors)

- [Tarikur Rahman](https://github.com/tarikurrahmann) — Creator and maintainer.
- [Claude AI](https://claude.ai/) — Assisted with project ideas, writing, and refinement.

## License

This project is licensed under the [MIT License](LICENSE).
