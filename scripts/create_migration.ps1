# Create new Alembic migration with validation
# Usage: .\scripts\create_migration.ps1

param(
    [Parameter(Mandatory=$false)]
    [string]$Message
)

$ErrorActionPreference = "Stop"

# Color output functions
function Write-Success { param($msg) Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Error { param($msg) Write-Host "[ERROR] $msg" -ForegroundColor Red }
function Write-Info { param($msg) Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Write-Warning { param($msg) Write-Host "[WARN] $msg" -ForegroundColor Yellow }

Write-Info "Alembic Migration Creator"
Write-Host ""

# Check if alembic is available
if (-not (Get-Command "alembic" -ErrorAction SilentlyContinue)) {
    Write-Error "Alembic not found. Install it with: pip install alembic"
    exit 1
}

# Prompt for migration message if not provided
if (-not $Message) {
    $Message = Read-Host "Enter migration message (e.g., 'add user notifications table')"
}

if (-not $Message) {
    Write-Error "Migration message is required"
    exit 1
}

# Sanitize message for filename
$sanitized = $Message.ToLower() -replace '[^a-z0-9_]+', '_'
$sanitized = $sanitized -replace '^_+|_+$', ''

Write-Info "Message: $Message"
Write-Info "Filename slug: $sanitized"
Write-Host ""

# Show current migration status
Write-Info "Current migration status:"
try {
    alembic current 2>&1 | ForEach-Object { Write-Host "  $_" }
} catch {
    Write-Warning "Failed to get current migration status"
}
Write-Host ""

# Check if database is up to date
Write-Info "Checking if database is up to date..."
$headOutput = alembic heads 2>&1 | Out-String
$currentOutput = alembic current 2>&1 | Out-String

if ($currentOutput -notmatch $headOutput.Trim()) {
    Write-Warning "Database is NOT at the latest migration!"
    Write-Warning "Consider running 'alembic upgrade head' first"
    Write-Host ""
    $continue = Read-Host "Continue anyway? (yes/no)"
    if ($continue -ne "yes") {
        Write-Info "Aborted"
        exit 0
    }
}

# Create migration
Write-Info "Creating migration..."
try {
    $output = alembic revision --autogenerate -m $Message 2>&1
    $output | ForEach-Object { Write-Host $_ }
    
    # Extract migration file path
    $migrationFile = $output | Select-String -Pattern "Generating (.+\.py)" | ForEach-Object { $_.Matches.Groups[1].Value }
    
    if ($migrationFile) {
        Write-Host ""
        Write-Success "Migration created: $migrationFile"
        
        # Show migration preview
        Write-Host ""
        Write-Info "Migration preview (first 30 lines):"
        Write-Host "─" * 80
        Get-Content $migrationFile -TotalCount 30 | ForEach-Object { Write-Host $_ }
        Write-Host "─" * 80
        Write-Host ""
        
        # Warnings
        Write-Warning "IMPORTANT:"
        Write-Host "  1. Review the migration file carefully"
        Write-Host "  2. Check for data loss operations (DROP, DELETE, etc.)"
        Write-Host "  3. Add data migration logic if needed"
        Write-Host "  4. Test migration on dev database first"
        Write-Host ""
        
        # Ask if user wants to apply migration
        $apply = Read-Host "Apply migration now? (yes/no)"
        if ($apply -eq "yes") {
            Write-Info "Applying migration..."
            alembic upgrade head
            Write-Success "Migration applied successfully"
        } else {
            Write-Info "Migration created but not applied"
            Write-Info "Apply later with: alembic upgrade head"
        }
        
    } else {
        Write-Warning "Migration file path not found in output"
        Write-Info "Check migrations/versions/ folder manually"
    }
    
} catch {
    Write-Error "Failed to create migration: $_"
    exit 1
}

Write-Host ""
Write-Success "Done!"
