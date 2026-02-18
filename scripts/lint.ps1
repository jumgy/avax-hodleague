# Lint and format code with ruff and mypy
# Usage: .\scripts\lint.ps1 [-Fix] [-TypeCheck] [-All]

param(
    [Parameter(Mandatory=$false)]
    [switch]$Fix,
    
    [Parameter(Mandatory=$false)]
    [switch]$TypeCheck,
    
    [Parameter(Mandatory=$false)]
    [switch]$All,
    
    [Parameter(Mandatory=$false)]
    [string]$Path = "."
)

$ErrorActionPreference = "Stop"

# Color output functions
function Write-Success { param($msg) Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Error { param($msg) Write-Host "[ERROR] $msg" -ForegroundColor Red }
function Write-Info { param($msg) Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Write-Warning { param($msg) Write-Host "[WARN] $msg" -ForegroundColor Yellow }

Write-Info "Code Quality Check"
Write-Host ""

$hasErrors = $false

# If -All is specified, enable everything
if ($All) {
    $Fix = $true
    $TypeCheck = $true
}

# ==================== Ruff Lint ====================
Write-Info "Running ruff check..."
Write-Host ""

try {
    if ($Fix) {
        Write-Info "Auto-fixing issues..."
        ruff check $Path --fix
    } else {
        ruff check $Path
    }
    
    if ($LASTEXITCODE -eq 0) {
        Write-Success "No linting issues found"
    } else {
        Write-Warning "Linting issues detected"
        $hasErrors = $true
    }
} catch {
    Write-Error "Ruff not found. Install it with: pip install ruff"
    exit 1
}

Write-Host ""

# ==================== Ruff Format ====================
if ($Fix) {
    Write-Info "Running ruff format..."
    Write-Host ""
    
    try {
        ruff format $Path
        
        if ($LASTEXITCODE -eq 0) {
            Write-Success "Code formatted successfully"
        } else {
            Write-Warning "Formatting issues"
            $hasErrors = $true
        }
    } catch {
        Write-Error "Ruff format failed"
        $hasErrors = $true
    }
    
    Write-Host ""
}

# ==================== Type Check (mypy) ====================
if ($TypeCheck) {
    Write-Info "Running mypy type checker..."
    Write-Host ""
    
    # Check if mypy is available
    if (-not (Get-Command "mypy" -ErrorAction SilentlyContinue)) {
        Write-Warning "mypy not found. Install it with: pip install mypy"
    } else {
        try {
            mypy $Path --pretty --show-error-codes
            
            if ($LASTEXITCODE -eq 0) {
                Write-Success "No type errors found"
            } else {
                Write-Warning "Type errors detected"
                $hasErrors = $true
            }
        } catch {
            Write-Error "Type checking failed"
            $hasErrors = $true
        }
    }
    
    Write-Host ""
}

# ==================== Summary ====================
Write-Host "─" * 80
Write-Host ""

if ($hasErrors) {
    Write-Error "Code quality check completed with issues"
    Write-Host ""
    Write-Info "Suggestions:"
    if (-not $Fix) {
        Write-Host "  - Run with -Fix flag to auto-fix linting and formatting issues"
    }
    if (-not $TypeCheck) {
        Write-Host "  - Run with -TypeCheck flag to check type hints"
    }
    Write-Host "  - Run with -All flag to run all checks and fixes"
    Write-Host ""
    exit 1
} else {
    Write-Success "All checks passed! Code quality is good."
    Write-Host ""
    exit 0
}
