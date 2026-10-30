# Netlify deployment

This folder contains the static website prepared for Netlify. Connect the GitHub repository and set:

- Base directory: `Netlify`
- Build command: leave empty
- Publish directory: `.`

The site includes the overview, `/install/`, `/integrations/`, `/enterprise/`, and `/blog/` pages. It also includes `install.ps1`, shared styling, and the MIT license.

The packaged Windows downloads are larger than 100 MB each, so they are intentionally not copied into this deploy folder. The website links to GitHub Releases instead. Before publishing, create a GitHub release and upload these exact assets:

- `Smart File Organizer 1.0.0.exe`
- `Smart File Organizer-1.0.0-win.zip`
- `Smart File Organizer Setup 1.0.0.exe`

The `install.ps1` download URL uses the latest GitHub release. After the site is deployed, run:

```powershell
irm https://smart-file-org.netlify.app/install.ps1 | iex
```

The installer will download successfully after the ZIP is published as a GitHub Release asset. Review the PowerShell script before running it.

To publish a blog update, edit `blog/index.html`.
