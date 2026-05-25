$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$Version = "2.5.0"
$Python = Join-Path $Root "venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

Write-Host "== CheckPilot commercial build =="
Write-Host "Root: $Root"

Write-Host "[1/5] Compile check"
$pyFiles = Get-ChildItem -Path $Root -Filter "*.py" -Recurse | Where-Object {
    $_.FullName -notmatch "venv|__pycache__|\.browsers|\\build\\|\\dist\\|\\release_v"
} | ForEach-Object { $_.FullName }
foreach ($f in $pyFiles) { & $Python -m py_compile $f }

Write-Host "[2/5] Ensure PyInstaller"
& $Python -m pip install --quiet --disable-pip-version-check pyinstaller

Write-Host "[3/5] Build app folder"
Remove-Item -Recurse -Force "build", "dist\CheckPilot" -ErrorAction SilentlyContinue
& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --windowed `
    --name CheckPilot `
    --icon "assets\icon.ico" `
    --add-data "assets;assets" `
    --add-data "sample_data.csv;." `
    --add-data "version.json;." `
    --add-data "yummi_sushi_data.csv;." `
    --add-data "YUMMI SAFETY CULTURE;YUMMI SAFETY CULTURE" `
    --add-data ".browsers;.browsers" `
    --hidden-import "PIL._tkinter_finder" `
    main.py

Write-Host "[4/5] Add client handoff files"
Copy-Item "README.md" "dist\CheckPilot\README.md" -Force
Copy-Item "HUONG_DAN_SU_DUNG.md" "dist\CheckPilot\HUONG_DAN_SU_DUNG.md" -Force
Copy-Item "sample_data.csv" "dist\CheckPilot\sample_data.csv" -Force
Copy-Item "version.json" "dist\CheckPilot\version.json" -Force
Copy-Item "yummi_sushi_data.csv" "dist\CheckPilot\yummi_sushi_data.csv" -Force

Write-Host "[5/5] Build installer"
$IsccPath = $null
$Iscc = (Get-Command iscc.exe -ErrorAction SilentlyContinue)
if ($Iscc) {
    $IsccPath = $Iscc.Source
}
if (-not $IsccPath) {
    $Possible = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
    )
    foreach ($Path in $Possible) {
        if (Test-Path $Path) {
            $IsccPath = $Path
            break
        }
    }
}

if (-not $IsccPath) {
    throw "Inno Setup compiler not found. Install Inno Setup 6, then rerun installer\build_release.ps1."
}

& $IsccPath "installer\CheckPilot.iss"

$Installer = Join-Path $Root "release\CheckPilot_Setup_v$Version.exe"
if (-not (Test-Path $Installer)) {
    throw "Installer was not created: $Installer"
}

Write-Host "DONE: $Installer"
