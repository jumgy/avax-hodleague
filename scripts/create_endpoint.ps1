# Create new API endpoint with router, service, schemas, and test
# Usage: .\scripts\create_endpoint.ps1

param(
    [Parameter(Mandatory=$false)]
    [string]$Name
)

$ErrorActionPreference = "Stop"

# Color output functions
function Write-Success { param($msg) Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Error { param($msg) Write-Host "[ERROR] $msg" -ForegroundColor Red }
function Write-Info { param($msg) Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Write-Warning { param($msg) Write-Host "[WARN] $msg" -ForegroundColor Yellow }

Write-Info "Create New API Endpoint Generator"
Write-Host ""

# Prompt for resource name if not provided
if (-not $Name) {
    $Name = Read-Host "Enter resource name (singular, e.g., 'notification')"
}

if (-not $Name) {
    Write-Error "Resource name is required"
    exit 1
}

# Convert to proper case formats
$ResourceSingular = $Name.ToLower()
$ResourcePlural = "${ResourceSingular}s"
$ClassSingular = (Get-Culture).TextInfo.ToTitleCase($ResourceSingular)
$ClassPlural = "${ClassSingular}s"
$ServiceClass = "${ClassSingular}Service"

Write-Info "Resource: $ResourceSingular -> $ResourcePlural"
Write-Info "Classes: $ClassSingular, $ServiceClass"
Write-Host ""

# Define file paths
$RouterPath = "api/routes/${ResourcePlural}.py"
$ServicePath = "services/${ResourceSingular}_service.py"
$TestPath = "tests/test_${ResourceSingular}.py"

# Check if files already exist
$existingFiles = @()
if (Test-Path $RouterPath) { $existingFiles += $RouterPath }
if (Test-Path $ServicePath) { $existingFiles += $ServicePath }
if (Test-Path $TestPath) { $existingFiles += $TestPath }

if ($existingFiles.Count -gt 0) {
    Write-Warning "Following files already exist:"
    $existingFiles | ForEach-Object { Write-Host "  - $_" }
    $confirm = Read-Host "Overwrite? (yes/no)"
    if ($confirm -ne "yes") {
        Write-Info "Aborted"
        exit 0
    }
}

Write-Info "Creating files..."

# ==================== Router Template ====================
$routerContent = @"
# api/routes/${ResourcePlural}.py

from fastapi import APIRouter, HTTPException, status, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from datetime import datetime
import logging

from models.database import get_async_db
from services.${ResourceSingular}_service import ${ServiceClass}
from services.web3_auth_service import web3_auth_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/${ResourcePlural}")
security_optional = HTTPBearer(auto_error=False)


# ==================== Schemas ====================

class ${ClassSingular}CreateRequest(BaseModel):
    """Request model for creating ${ResourceSingular}"""
    name: str
    # Add your fields here


class ${ClassSingular}Response(BaseModel):
    """Response model for ${ResourceSingular}"""
    id: int
    name: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ${ClassSingular}ListResponse(BaseModel):
    """Response model for ${ResourceSingular} list"""
    success: bool
    data: List[${ClassSingular}Response]
    total: int


# ==================== Auth Dependencies ====================

def get_current_user_required(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional)
) -> dict:
    """Required auth: cookie OR Bearer header"""
    token = None
    
    if credentials:
        token = credentials.credentials
    if not token:
        token = request.cookies.get("access_token")
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    try:
        user = web3_auth_service.verify_jwt_token(token)
        return user
    except Exception as e:
        logger.error(f"❌ Token verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )


# ==================== Endpoints ====================

@router.get("", response_model=${ClassSingular}ListResponse)
async def list_${ResourcePlural}(
    db: AsyncSession = Depends(get_async_db)
):
    """List all ${ResourcePlural}"""
    try:
        service = ${ServiceClass}()
        items = await service.list_all(db)
        
        return {
            "success": True,
            "data": items,
            "total": len(items)
        }
    except Exception as e:
        logger.error(f"❌ Failed to list ${ResourcePlural}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch ${ResourcePlural}"
        )


@router.get("/{${ResourceSingular}_id}", response_model=${ClassSingular}Response)
async def get_${ResourceSingular}(
    ${ResourceSingular}_id: int,
    db: AsyncSession = Depends(get_async_db)
):
    """Get single ${ResourceSingular} by ID"""
    try:
        service = ${ServiceClass}()
        item = await service.get_by_id(${ResourceSingular}_id, db)
        
        if not item:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="${ClassSingular} not found"
            )
        
        return item
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get ${ResourceSingular}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch ${ResourceSingular}"
        )


@router.post("", response_model=${ClassSingular}Response, status_code=status.HTTP_201_CREATED)
async def create_${ResourceSingular}(
    request: ${ClassSingular}CreateRequest,
    user: dict = Depends(get_current_user_required),
    db: AsyncSession = Depends(get_async_db)
):
    """Create new ${ResourceSingular} (authenticated)"""
    try:
        service = ${ServiceClass}()
        item = await service.create(request.dict(), db)
        
        logger.info(f"✅ ${ClassSingular} created: {item.id} by user {user['wallet_address']}")
        return item
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"❌ Failed to create ${ResourceSingular}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create ${ResourceSingular}"
        )


@router.delete("/{${ResourceSingular}_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_${ResourceSingular}(
    ${ResourceSingular}_id: int,
    user: dict = Depends(get_current_user_required),
    db: AsyncSession = Depends(get_async_db)
):
    """Delete ${ResourceSingular} (authenticated)"""
    try:
        service = ${ServiceClass}()
        success = await service.delete(${ResourceSingular}_id, db)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="${ClassSingular} not found"
            )
        
        logger.info(f"✅ ${ClassSingular} deleted: {${ResourceSingular}_id} by user {user['wallet_address']}")
        return None
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to delete ${ResourceSingular}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete ${ResourceSingular}"
        )
"@

# ==================== Service Template ====================
$serviceContent = @"
# services/${ResourceSingular}_service.py

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
import logging

# TODO: Import your model
# from models.${ResourceSingular}_models import ${ClassSingular}

logger = logging.getLogger(__name__)


class ${ServiceClass}:
    """Service for managing ${ResourceSingular} operations"""

    async def list_all(self, db: AsyncSession) -> List:
        """Get all ${ResourcePlural}"""
        try:
            # TODO: Replace with your model
            # result = await db.execute(select(${ClassSingular}))
            # items = result.scalars().all()
            items = []  # Placeholder
            
            logger.info(f"✅ Listed {len(items)} ${ResourcePlural}")
            return items
        except Exception as e:
            logger.error(f"❌ Failed to list ${ResourcePlural}: {e}")
            raise

    async def get_by_id(self, ${ResourceSingular}_id: int, db: AsyncSession) -> Optional:
        """Get single ${ResourceSingular} by ID"""
        try:
            # TODO: Replace with your model
            # result = await db.execute(
            #     select(${ClassSingular}).where(${ClassSingular}.id == ${ResourceSingular}_id)
            # )
            # item = result.scalar_one_or_none()
            item = None  # Placeholder
            
            if item:
                logger.info(f"✅ Found ${ResourceSingular}: {${ResourceSingular}_id}")
            else:
                logger.warning(f"⚠️  ${ClassSingular} not found: {${ResourceSingular}_id}")
            
            return item
        except Exception as e:
            logger.error(f"❌ Failed to get ${ResourceSingular}: {e}")
            raise

    async def create(self, data: dict, db: AsyncSession):
        """Create new ${ResourceSingular}"""
        try:
            # TODO: Replace with your model
            # item = ${ClassSingular}(**data)
            # db.add(item)
            # await db.commit()
            # await db.refresh(item)
            
            logger.info(f"✅ ${ClassSingular} created successfully")
            # return item
            raise NotImplementedError("Implement model creation")
        except Exception as e:
            await db.rollback()
            logger.error(f"❌ Failed to create ${ResourceSingular}: {e}")
            raise

    async def delete(self, ${ResourceSingular}_id: int, db: AsyncSession) -> bool:
        """Delete ${ResourceSingular}"""
        try:
            # TODO: Replace with your model
            # result = await db.execute(
            #     select(${ClassSingular}).where(${ClassSingular}.id == ${ResourceSingular}_id)
            # )
            # item = result.scalar_one_or_none()
            
            # if not item:
            #     return False
            
            # await db.delete(item)
            # await db.commit()
            
            logger.info(f"✅ ${ClassSingular} deleted: {${ResourceSingular}_id}")
            # return True
            return False  # Placeholder
        except Exception as e:
            await db.rollback()
            logger.error(f"❌ Failed to delete ${ResourceSingular}: {e}")
            raise
"@

# ==================== Test Template ====================
$testContent = @"
# tests/test_${ResourceSingular}.py

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# TODO: Import your models
# from models.${ResourceSingular}_models import ${ClassSingular}


@pytest.mark.asyncio
async def test_list_${ResourcePlural}_empty(async_client: AsyncClient):
    """Test listing ${ResourcePlural} when empty"""
    response = await async_client.get("/${ResourcePlural}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["total"] == 0
    assert len(data["data"]) == 0


@pytest.mark.asyncio
async def test_get_${ResourceSingular}_not_found(async_client: AsyncClient):
    """Test getting non-existent ${ResourceSingular}"""
    response = await async_client.get("/${ResourcePlural}/999999")
    
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_${ResourceSingular}_unauthenticated(async_client: AsyncClient):
    """Test creating ${ResourceSingular} without auth"""
    response = await async_client.post(
        "/${ResourcePlural}",
        json={"name": "Test ${ClassSingular}"}
    )
    
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_${ResourceSingular}_success(
    async_client: AsyncClient,
    auth_headers: dict
):
    """Test successful ${ResourceSingular} creation"""
    response = await async_client.post(
        "/${ResourcePlural}",
        json={"name": "Test ${ClassSingular}"},
        headers=auth_headers
    )
    
    # TODO: Update assertion when model is implemented
    assert response.status_code in [201, 500]  # 500 expected until model is implemented


@pytest.mark.asyncio
async def test_delete_${ResourceSingular}_not_found(
    async_client: AsyncClient,
    auth_headers: dict
):
    """Test deleting non-existent ${ResourceSingular}"""
    response = await async_client.delete(
        "/${ResourcePlural}/999999",
        headers=auth_headers
    )
    
    assert response.status_code == 404


# TODO: Add more tests:
# - test_create_${ResourceSingular}_validation_errors
# - test_update_${ResourceSingular}_success
# - test_list_${ResourcePlural}_pagination
"@

# Write files
try {
    New-Item -ItemType Directory -Force -Path (Split-Path $RouterPath) | Out-Null
    New-Item -ItemType Directory -Force -Path (Split-Path $ServicePath) | Out-Null
    New-Item -ItemType Directory -Force -Path (Split-Path $TestPath) | Out-Null
    
    [System.IO.File]::WriteAllText((Join-Path $PWD $RouterPath), $routerContent, [System.Text.Encoding]::UTF8)
    Write-Success "Created router: $RouterPath"
    
    [System.IO.File]::WriteAllText((Join-Path $PWD $ServicePath), $serviceContent, [System.Text.Encoding]::UTF8)
    Write-Success "Created service: $ServicePath"
    
    [System.IO.File]::WriteAllText((Join-Path $PWD $TestPath), $testContent, [System.Text.Encoding]::UTF8)
    Write-Success "Created test: $TestPath"
    
    Write-Host ""
    Write-Success "Endpoint created successfully!"
    Write-Host ""
    Write-Warning "Next steps:"
    Write-Host "  1. Create model in models/${ResourceSingular}_models.py"
    Write-Host "  2. Update service to use real model"
    Write-Host "  3. Register router in main.py:"
    Write-Host "     from api.routes import ${ResourcePlural}"
    Write-Host "     app.include_router(${ResourcePlural}.router, tags=['${ResourcePlural}'])"
    Write-Host "  4. Create Alembic migration for the model"
    Write-Host "  5. Run tests: pytest tests/test_${ResourceSingular}.py -v"
    
} catch {
    Write-Error "Failed to create files: $_"
    exit 1
}
