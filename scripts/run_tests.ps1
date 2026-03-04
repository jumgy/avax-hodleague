# Run tests with coverage report
# Usage: .\scripts\run_tests.ps1 [-Coverage] [-File <path>] [-Verbose]

param(
    [Parameter(Mandatory=$false)]
    [switch]$Coverage,
    
    [Parameter(Mandatory=$false)]
    [string]$File,
    
    [Parameter(Mandatory=$false)]
    [switch]$Verbose,
    
    [Parameter(Mandatory=$false)]
    [switch]$FailFast,
    
    [Parameter(Mandatory=$false)]
    [string]$Keyword,
    
    # Only print the pytest command, do not run tests (useful when run_tests.ps1 fails to spawn)
    [Parameter(Mandatory=$false)]
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# Color output functions
function Write-Success { param($msg) Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Error { param($msg) Write-Host "[ERROR] $msg" -ForegroundColor Red }
function Write-Info { param($msg) Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Write-Warning { param($msg) Write-Host "[WARN] $msg" -ForegroundColor Yellow }

Write-Info "Running Tests"
Write-Host ""

# Check if pytest is available
if (-not (Get-Command "pytest" -ErrorAction SilentlyContinue)) {
    Write-Error "pytest not found. Install it with: pip install pytest pytest-asyncio"
    exit 1
}

# Build pytest arguments
$args = @()

# Test path
if ($File) {
    if (-not (Test-Path $File)) {
        Write-Error "Test file not found: $File"
        exit 1
    }
    $args += $File
    Write-Info "Running single file: $File"
} else {
    $args += "tests"
    Write-Info "Running all tests"
}

# Verbosity
if ($Verbose) {
    $args += "-vv"
} else {
    $args += "-v"
}

# Fail fast
if ($FailFast) {
    $args += "-x"
}

# Keyword filter
if ($Keyword) {
    $args += "-k"
    $args += $Keyword
    Write-Info "Filtering by keyword: $Keyword"
}

# Coverage
if ($Coverage) {
    $args += "--cov=."
    $args += "--cov-report=term-missing"
    $args += "--cov-report=html:htmlcov"
    $args += "--cov-report=json:coverage.json"
    Write-Info "Coverage reporting enabled"
}

# Additional flags
$args += "--tb=short"
$args += "--color=yes"

Write-Host ""
Write-Info "Command: pytest $($args -join ' ')"
Write-Host "─" * 80
Write-Host ""

if ($DryRun) {
    Write-Warning "DryRun: not running pytest. Run manually: pytest $($args -join ' ')"
    exit 0
}

# Run pytest
try {
    $startTime = Get-Date
    & pytest @args
    $exitCode = $LASTEXITCODE
    $duration = (Get-Date) - $startTime
    
    Write-Host ""
    Write-Host "─" * 80
    
    if ($exitCode -eq 0) {
        Write-Success "All tests passed! ($($duration.TotalSeconds.ToString('F2'))s)"
        
        if ($Coverage) {
            Write-Host ""
            Write-Info "Coverage report saved to:"
            Write-Host "  - htmlcov/index.html (HTML report)"
            Write-Host "  - coverage.json (JSON data)"
            
            # Try to parse coverage percentage
            if (Test-Path "coverage.json") {
                try {
                    $coverageData = Get-Content "coverage.json" | ConvertFrom-Json
                    $totalCoverage = [math]::Round($coverageData.totals.percent_covered, 2)
                    Write-Host ""
                    Write-Info "Total coverage: $totalCoverage%"
                    
                    if ($totalCoverage -lt 70) {
                        Write-Warning "Coverage is below 70%"
                    } elseif ($totalCoverage -lt 85) {
                        Write-Warning "Coverage is below 85%"
                    } else {
                        Write-Success "Good coverage!"
                    }
                } catch {
                    # Ignore parsing errors
                }
            }
        }
    } else {
        Write-Error "Tests failed! ($($duration.TotalSeconds.ToString('F2'))s)"
        exit $exitCode
    }
    
} catch {
    Write-Error "Failed to run tests: $_"
    exit 1
}
