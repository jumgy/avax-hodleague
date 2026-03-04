# Manage docker-compose dev environment
# Usage: .\scripts\docker_dev.ps1 [start|stop|restart|logs|status|rebuild]

param(
    [Parameter(Mandatory=$false, Position=0)]
    [ValidateSet("start", "stop", "restart", "logs", "status", "rebuild", "clean")]
    [string]$Action = "status",
    
    [Parameter(Mandatory=$false)]
    [switch]$Follow,
    
    [Parameter(Mandatory=$false)]
    [string]$Service
)

$ErrorActionPreference = "Stop"

# Color output functions
function Write-Success { param($msg) Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Error { param($msg) Write-Host "[ERROR] $msg" -ForegroundColor Red }
function Write-Info { param($msg) Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Write-Warning { param($msg) Write-Host "[WARN] $msg" -ForegroundColor Yellow }

Write-Info "Docker Dev Environment Manager"
Write-Host ""

# Check if docker-compose is available
if (-not (Get-Command "docker-compose" -ErrorAction SilentlyContinue)) {
    Write-Error "docker-compose not found. Install Docker Desktop first."
    exit 1
}

# Check if docker-compose.yml exists
if (-not (Test-Path "docker-compose.yml")) {
    Write-Error "docker-compose.yml not found in current directory"
    exit 1
}

# Execute action
switch ($Action) {
    "start" {
        Write-Info "Starting dev environment..."
        try {
            docker-compose up -d
            if ($LASTEXITCODE -eq 0) {
                Write-Success "Dev environment started"
                Write-Host ""
                Write-Info "Services:"
                docker-compose ps
                Write-Host ""
                Write-Info "View logs with: .\scripts\docker_dev.ps1 logs -Follow"
            } else {
                Write-Error "Failed to start dev environment"
                exit 1
            }
        } catch {
            Write-Error "Error starting dev environment: $_"
            exit 1
        }
    }
    
    "stop" {
        Write-Info "Stopping dev environment..."
        try {
            docker-compose down
            if ($LASTEXITCODE -eq 0) {
                Write-Success "Dev environment stopped"
            } else {
                Write-Error "Failed to stop dev environment"
                exit 1
            }
        } catch {
            Write-Error "Error stopping dev environment: $_"
            exit 1
        }
    }
    
    "restart" {
        Write-Info "Restarting dev environment..."
        try {
            if ($Service) {
                docker-compose restart $Service
                Write-Success "Service '$Service' restarted"
            } else {
                docker-compose restart
                Write-Success "All services restarted"
            }
        } catch {
            Write-Error "Error restarting: $_"
            exit 1
        }
    }
    
    "logs" {
        Write-Info "Showing logs..."
        try {
            $args = @("logs", "--tail=100")
            if ($Follow) {
                $args += "-f"
            }
            if ($Service) {
                $args += $Service
            }
            
            & docker-compose @args
        } catch {
            Write-Error "Error showing logs: $_"
            exit 1
        }
    }
    
    "status" {
        Write-Info "Dev environment status:"
        Write-Host ""
        try {
            docker-compose ps
            Write-Host ""
            
            # Check if services are running
            $output = docker-compose ps --format json 2>&1 | ConvertFrom-Json
            if ($output.Count -eq 0) {
                Write-Warning "No services running"
                Write-Info "Start with: .\scripts\docker_dev.ps1 start"
            } else {
                $running = ($output | Where-Object { $_.State -eq "running" }).Count
                $total = $output.Count
                
                if ($running -eq $total) {
                    Write-Success "All services running ($running/$total)"
                } else {
                    Write-Warning "Some services not running ($running/$total)"
                }
            }
        } catch {
            Write-Warning "No services found or error checking status"
            Write-Info "Start with: .\scripts\docker_dev.ps1 start"
        }
    }
    
    "rebuild" {
        Write-Warning "Rebuilding dev environment (this will recreate containers)..."
        $confirm = Read-Host "Continue? (yes/no)"
        if ($confirm -ne "yes") {
            Write-Info "Aborted"
            exit 0
        }
        
        try {
            Write-Info "Stopping services..."
            docker-compose down
            
            Write-Info "Rebuilding images..."
            docker-compose build --no-cache
            
            Write-Info "Starting services..."
            docker-compose up -d
            
            if ($LASTEXITCODE -eq 0) {
                Write-Success "Dev environment rebuilt successfully"
                Write-Host ""
                docker-compose ps
            } else {
                Write-Error "Failed to rebuild"
                exit 1
            }
        } catch {
            Write-Error "Error rebuilding: $_"
            exit 1
        }
    }
    
    "clean" {
        Write-Warning "This will stop all services and remove volumes (DATABASE WILL BE LOST)"
        $confirm = Read-Host "Continue? (yes/no)"
        if ($confirm -ne "yes") {
            Write-Info "Aborted"
            exit 0
        }
        
        try {
            Write-Info "Stopping services and removing volumes..."
            docker-compose down -v
            
            Write-Success "Dev environment cleaned"
            Write-Warning "Database data has been removed"
        } catch {
            Write-Error "Error cleaning: $_"
            exit 1
        }
    }
}
