param([string]$OutputDirectory = 'dist', [switch]$SkipShortcut)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    throw 'Crie o ambiente .venv e instale requirements.txt primeiro.'
}
& $taskPython tools\prepare_build.py
if ($LASTEXITCODE -ne 0) { throw 'Falha ao preparar recursos.' }
# Keep unrelated tools' DLLs (for example Poppler's versioned ICU) out of the bundle.
$taskOriginalPath = $env:PATH
try {
    $env:PATH = "$(Split-Path -Parent $taskPython);$env:WINDIR\System32;$env:WINDIR"
    & $taskPython -m PyInstaller --noconfirm --windowed --onedir --distpath $OutputDirectory --name Entrelinhas --icon assets\entrelinhas.ico --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtWebEngineWidgets --exclude-module PySide6.QtQml --exclude-module PySide6.QtQuick main.py
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao gerar o executável.' }
} finally {
    $env:PATH = $taskOriginalPath
}
$taskDistribution = Join-Path ([System.IO.Path]::GetFullPath($OutputDirectory, $PSScriptRoot)) 'Entrelinhas'
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'README.md') -Destination $taskDistribution
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'LICENSE') -Destination $taskDistribution
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'licenses') -Destination $taskDistribution -Recurse -Force
$taskSource = Join-Path $taskDistribution 'source'
New-Item -Path $taskSource -ItemType Directory -Force | Out-Null
foreach ($taskFile in @('main.py', 'requirements.txt', 'build.ps1', 'README.md', 'LICENSE')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $taskFile) -Destination $taskSource -Force
}
foreach ($taskFolder in @('leitor', 'tests', 'tools')) {
    $taskDestination = Join-Path $taskSource $taskFolder
    New-Item -Path $taskDestination -ItemType Directory -Force | Out-Null
    Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot $taskFolder) -File -Filter '*.py' | Copy-Item -Destination $taskDestination -Force
}
if (-not $SkipShortcut) {
$taskShell = New-Object -ComObject WScript.Shell
$taskShortcut = $taskShell.CreateShortcut((Join-Path $PSScriptRoot 'Abrir Entrelinhas.lnk'))
$taskShortcut.TargetPath = Join-Path $taskDistribution 'Entrelinhas.exe'
$taskShortcut.WorkingDirectory = $taskDistribution
$taskShortcut.IconLocation = $taskShortcut.TargetPath
$taskShortcut.Description = 'Entrelinhas - sua biblioteca de PDFs'
$taskShortcut.Save()
}
Write-Output "Aplicativo pronto: $taskDistribution\Entrelinhas.exe"
