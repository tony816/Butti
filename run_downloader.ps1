$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$localPython = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"

if (Test-Path -LiteralPath $localPython) {
    & $localPython "opendart_gui.py"
    Read-Host "`nPress Enter to close"
    exit $LASTEXITCODE
}

$commands = @(
    @{ Name = "py"; VersionArgs = @("-3", "--version"); Args = @("-3", "opendart_gui.py") },
    @{ Name = "python"; VersionArgs = @("--version"); Args = @("opendart_gui.py") },
    @{ Name = "python3"; VersionArgs = @("--version"); Args = @("opendart_gui.py") }
)

foreach ($command in $commands) {
    if (Get-Command $command.Name -ErrorAction SilentlyContinue) {
        & $command.Name @($command.VersionArgs) *> $null
        if ($LASTEXITCODE -ne 0) {
            continue
        }
        & $command.Name @($command.Args)
        Read-Host "`nPress Enter to close"
        exit $LASTEXITCODE
    }
}

Write-Host "Python launcher was not found."
Write-Host "Install Python 3.10 or newer, then run this file again."
Write-Host "Download: https://www.python.org/downloads/windows/"
Read-Host "`nPress Enter to close"
exit 1
