$ErrorActionPreference = "Stop"

python -m PyInstaller `
  --clean `
  --noconfirm `
  --onefile `
  --windowed `
  --name pyRPC3-GUI `
  --exclude-module pandas `
  --exclude-module matplotlib `
  --exclude-module scipy `
  --exclude-module torch `
  --exclude-module IPython `
  --exclude-module pytest `
  --exclude-module boto3 `
  --exclude-module botocore `
  --paths . `
  src\gui_launcher.py

if ($LASTEXITCODE -ne 0) {
  exit $LASTEXITCODE
}

Write-Host "Built: dist\pyRPC3-GUI.exe"
