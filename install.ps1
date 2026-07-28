<#
.SYNOPSIS
    Installs the BugPilot CLI from a local wheel using pipx.

.DESCRIPTION
    Detects Python and pipx (installing pipx if needed), finds the BugPilot
    wheel next to this script, installs it with pipx, and verifies the install.

.NOTES
    Runs on Windows PowerShell 5.1 and PowerShell 7+.
    Place this script in the same folder as a bugpilot-*.whl file and run it.
#>

$ErrorActionPreference = 'Stop'

# --- output helpers ---------------------------------------------------------

function Write-Step    { param([string]$Message) Write-Host "==> $Message" -ForegroundColor Cyan }
function Write-Ok      { param([string]$Message) Write-Host "    $Message" -ForegroundColor Green }
function Write-Note    { param([string]$Message) Write-Host "    $Message" -ForegroundColor Yellow }
function Write-Fail    { param([string]$Message) Write-Host $Message -ForegroundColor Red }

function Write-Banner {
    Write-Host ""
    Write-Host "  ============================================" -ForegroundColor Cyan
    Write-Host "        BugPilot CLI" -NoNewline -ForegroundColor White
    Write-Host "  -  Installer" -ForegroundColor Cyan
    Write-Host "  ============================================" -ForegroundColor Cyan
    Write-Host "    Prepare-only AI-assisted Jira bug workflow" -ForegroundColor DarkGray
    Write-Host ""
}

# Run a native command and fail (throw) on a non-zero exit code.
function Invoke-Native {
    param(
        [Parameter(Mandatory)][string]$Exe,
        [string[]]$Arguments = @()
    )
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed (exit $LASTEXITCODE): $Exe $($Arguments -join ' ')"
    }
}

# Return the first working Python 3 launcher ('python' or 'py'), or $null.
function Resolve-Python {
    foreach ($candidate in @('python', 'py')) {
        if (-not (Get-Command $candidate -ErrorAction SilentlyContinue)) { continue }
        $version = & $candidate --version 2>&1
        if ($LASTEXITCODE -eq 0 -and $version -match 'Python 3') {
            return $candidate
        }
    }
    return $null
}

# --- installation -----------------------------------------------------------

try {
    Write-Banner

    # 1. Python -------------------------------------------------------------
    Write-Step "Checking for Python..."
    $python = Resolve-Python
    if (-not $python) {
        Write-Fail "Python 3 was not found on your PATH."
        Write-Fail "Install Python 3.10 or newer from https://www.python.org/downloads/"
        Write-Fail "(during install, tick 'Add python.exe to PATH'), then re-run this script."
        exit 1
    }
    $pythonVersion = (& $python --version 2>&1).Trim()
    Write-Ok "Found $pythonVersion ($python)"

    # 2. pipx ---------------------------------------------------------------
    Write-Step "Checking for pipx..."
    & $python -m pipx --version *> $null
    $pipxInstalled = ($LASTEXITCODE -eq 0)
    $pathMayHaveChanged = $false

    if ($pipxInstalled) {
        Write-Ok "pipx is already installed."
    }
    else {
        Write-Note "pipx not found - installing it now..."
        Invoke-Native $python @('-m', 'pip', 'install', '--user', 'pipx')
        Invoke-Native $python @('-m', 'pipx', 'ensurepath')
        $pathMayHaveChanged = $true
        Write-Ok "pipx installed."
    }

    # 3. Locate the wheel ---------------------------------------------------
    Write-Step "Locating the BugPilot wheel..."
    $wheels = Get-ChildItem -Path $PSScriptRoot -Filter 'bugpilot-*.whl' -File |
        Sort-Object LastWriteTime -Descending
    if (-not $wheels) {
        throw "No BugPilot wheel (bugpilot-*.whl) found in '$PSScriptRoot'."
    }
    $wheel = $wheels[0]
    if ($wheels.Count -gt 1) {
        Write-Note "Multiple wheels found; using the newest: $($wheel.Name)"
    }
    Write-Ok "Using $($wheel.Name)"

    # 4. Install via pipx ---------------------------------------------------
    Write-Step "Installing BugPilot with pipx..."
    # --force lets the installer double as an upgrader when re-run.
    Invoke-Native $python @('-m', 'pipx', 'install', '--force', $wheel.FullName)
    Write-Ok "BugPilot installed."

    # 5. Verify -------------------------------------------------------------
    Write-Step "Verifying installation..."
    # pipx's bin dir may not be on PATH in this session yet; add it so the
    # verification below can find the freshly installed 'bugpilot' command.
    $pipxBin = & $python -m pipx environment --value PIPX_BIN_DIR 2>$null
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($pipxBin)) {
        $pipxBin = Join-Path $env:USERPROFILE '.local\bin'
    }
    if (Test-Path $pipxBin) {
        $env:PATH = "$pipxBin;$env:PATH"
    }

    $bugpilotCmd = Get-Command bugpilot -ErrorAction SilentlyContinue
    if ($bugpilotCmd) {
        $bugpilotExe = $bugpilotCmd.Source
    }
    else {
        $bugpilotExe = Join-Path $pipxBin 'bugpilot.exe'
    }
    Invoke-Native $bugpilotExe @('--help')
    Write-Ok "'bugpilot --help' ran successfully."

    # 6. Done ---------------------------------------------------------------
    Write-Host ""
    Write-Host "Installation completed successfully!" -ForegroundColor Green
    Write-Host ""
    if ($pathMayHaveChanged) {
        Write-Note "PATH was updated. Restart PowerShell before using 'bugpilot' in a new window."
        Write-Host ""
    }
    Write-Host "Next step:" -ForegroundColor White
    Write-Host ""
    Write-Host "    bugpilot setup" -ForegroundColor Cyan
    Write-Host ""
}
catch {
    Write-Host ""
    Write-Fail "Installation failed."
    Write-Fail $_.Exception.Message
    Write-Host ""
    Write-Fail "Troubleshooting:"
    Write-Fail "  - Ensure Python 3.10+ is installed and on PATH ('python --version')."
    Write-Fail "  - Try running the failed command manually to see the full output."
    Write-Fail "  - If pipx was just installed, restart PowerShell and re-run this script."
    exit 1
}
