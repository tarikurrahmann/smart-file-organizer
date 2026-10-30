$ErrorActionPreference = "Stop"

$archiveUrl = "https://github.com/tarikurrahmann/smart-file-organizer/releases/latest/download/Smart%20File%20Organizer-1.0.0-win.zip"
$installDirectory = Join-Path $env:LOCALAPPDATA "Programs\Smart File Organizer"
$archivePath = Join-Path $env:TEMP ("smart-file-organizer-{0}.zip" -f [guid]::NewGuid())
$executablePath = Join-Path $installDirectory "Smart File Organizer.exe"

try {
  Invoke-WebRequest -Uri $archiveUrl -OutFile $archivePath -UseBasicParsing
  New-Item -ItemType Directory -Path $installDirectory -Force | Out-Null
  Expand-Archive -LiteralPath $archivePath -DestinationPath $installDirectory -Force

  if (-not (Test-Path -LiteralPath $executablePath -PathType Leaf)) {
    throw "The downloaded archive did not contain Smart File Organizer.exe."
  }

  Start-Process -FilePath $executablePath
  Write-Host "Smart File Organizer installed to $installDirectory"
}
finally {
  if (Test-Path -LiteralPath $archivePath -PathType Leaf) {
    Remove-Item -LiteralPath $archivePath -Force
  }
}
