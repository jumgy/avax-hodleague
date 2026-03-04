from fastapi import APIRouter, HTTPException, Header, Depends, Response, Cookie, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from pydantic import BaseModel, validator
from typing import Optional
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import Config
from models.database import get_async_db
from models.pack_models import PackType
from models.user_pack_models import UserPack, PackSource
from services.web3_auth_service import web3_auth_service
from services.user_pack_grant_service import user_pack_grant_service
from utils.rate_limit import limiter

logger = logging.getLogger(__name__)

security_optional = HTTPBearer(auto_error=False)

router = APIRouter(prefix="/auth")


class NonceRequest(BaseModel):
    wallet_address: str
    referral_code: Optional[str] = None

    @validator('wallet_address')
    def validate_wallet_address(cls, v):
        if not v:
            raise ValueError('Wallet address is required')
        v = v.strip().lower()
        if not v.startswith('0x') or len(v) != 42:
            raise ValueError('Invalid Ethereum wallet address format')
        try:
            int(v[2:], 16)
        except ValueError:
            raise ValueError('Wallet address contains invalid characters')
        return v


class VerifyRequest(BaseModel):
    wallet_address: str
    signature: str
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    referral_code: Optional[str] = None

    @validator('wallet_address')
    def validate_wallet_address(cls, v):
        if not v:
            raise ValueError('Wallet address is required')
        return v.strip().lower()

    @validator('signature')
    def validate_signature(cls, v):
        if not v:
            raise ValueError('Signature is required')
        return v.strip()

    @validator('nickname')
    def validate_nickname(cls, v):
        if v is not None:
            v = v.strip()
            if len(v) < 2 or len(v) > 30:
                raise ValueError('Nickname must be between 2 and 30 characters')
        return v
    
    @validator('referral_code')
    def validate_referral_code(cls, v):
        if v is not None:
            v = v.strip()
            if len(v) < 3 or len(v) > 100:
                raise ValueError('Invalid referral code format')
        return v


class AuthResponse(BaseModel):
    token_type: str = "bearer"
    expires_in: int = 604800  # 7 days in seconds
    user: dict
    cards_granted: Optional[int] = None
    packs_granted: Optional[int] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "token_type": "bearer",
                "expires_in": 604800,
                "user": {
                    "id": 1,
                    "wallet_address": "0x1234...",
                    "nickname": "Player123",
                    "referral_route": "Player1230001",
                    "avatar_url": "https://...",
                    "created_at": "2026-01-22T10:00:00"
                },
                "packs_granted": 3
            }
        }

class TestAuthResponse(BaseModel):
    """Response model for test authentication (includes token in body)."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 604800
    user: dict
    cards_granted: Optional[int] = None
    packs_granted: Optional[int] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "expires_in": 604800,
                "user": {
                    "id": 1,
                    "wallet_address": "0x1234...",
                    "nickname": "TestUser123",
                    "referral_route": "TestUser1230001",
                    "avatar_url": "https://...",
                    "created_at": "2026-01-22T10:00:00"
                },
                "packs_granted": 3
            }
        }



def verify_jwt_dependency(
    request: Request,
    access_token: Optional[str] = Cookie(None),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional)
):
    """Verify JWT token from cookie OR Bearer header"""
    token = None
    
    # 1. Try Bearer header (Swagger)
    if credentials:
        token = credentials.credentials
    
    # 2. Else try cookie (frontend)
    if not token:
        token = access_token
    
    # 3. No token means auth required
    if not token:
        raise HTTPException(
            status_code=401, 
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    try:
        payload = web3_auth_service.verify_jwt_token(token)
        if not payload:
            raise HTTPException(
                status_code=401, 
                detail="Invalid or expired token"
            )
        return payload
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        raise HTTPException(
            status_code=401, 
            detail="Authentication failed"
        )


@router.post("/nonce")
@limiter.limit("10/minute")
async def get_nonce(request: Request, body: NonceRequest):
    """
    Generate nonce for wallet signature authentication
    Returns a message that should be signed by the user's wallet.
    """
    try:
        message = web3_auth_service.generate_nonce(body.wallet_address)
        return {
            "message": message,
            "wallet_address": body.wallet_address
        }
    except Exception as e:
        logger.error(f"Error generating nonce: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate nonce")


@router.post("/verify", response_model=AuthResponse)
@limiter.limit("5/minute")
async def verify_signature(
    request: Request,
    body: VerifyRequest,
    response: Response,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Verify wallet signature and authenticate user
    Validates the signed message and sets HTTP-only authentication cookie.
    """
    try:
        is_valid = await web3_auth_service.verify_signature(
            body.wallet_address,
            body.signature
        )
        
        if not is_valid:
            raise HTTPException(status_code=401, detail="Invalid signature")
        
        # Check if user already exists
        existing_user = await web3_auth_service.get_user_by_wallet(
            body.wallet_address,
            db
        )
        is_new_user = existing_user is None
        
        user = await web3_auth_service.create_or_get_user(
            wallet_address=body.wallet_address,
            nickname=body.nickname,
            avatar_url=body.avatar_url,
            referral_code=body.referral_code,
            db=db
        )
        
        cards_granted_count = 0
        packs_granted_count = 0
        
        # Grant starter packs to new users: off-chain only (UserPack rows, no on-chain mint).
        if is_new_user:
            try:
                granted_packs = await user_pack_grant_service.grant_all_active_packs_to_user(
                    user_id=user.id,
                    source="reward",
                )
                packs_granted_count = len(granted_packs)
                logger.info(
                    "Granted %s starter packs (off-chain) to new user %s",
                    packs_granted_count,
                    user.id,
                )
            except Exception as pack_error:
                logger.error("Error granting starter packs to user %s: %s", user.id, pack_error)
        
        # Create JWT
        access_token = web3_auth_service.create_jwt_token(user)
        
        # UAT: SameSite=None for cross-origin; production: SameSite=lax for same-site
        if Config.ENVIRONMENT == "production":
            cookie_secure = True
            cookie_samesite = "lax"
        else:
            cookie_secure = True  # UAT uses HTTPS
            cookie_samesite = "none"  # Allow cross-origin
        
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,  # XSS protection
            secure=cookie_secure,
            samesite=cookie_samesite,
            max_age=604800,  # 7 days
            path="/",
            domain=None
        )
        
        # Response without token in body (token in cookie only)
        response_data = {
            "user": {
                "id": user.id,
                "wallet_address": user.wallet_address,
                "nickname": user.nickname,
                "referral_route": user.referral_route,
                "avatar_url": user.avatar_url,
                "created_at": user.created_at.isoformat()
            }
        }
        
        # Include granted packs info for new users
        if is_new_user:
            response_data["cards_granted"] = cards_granted_count
            response_data["packs_granted"] = packs_granted_count
        
        return AuthResponse(**response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying signature: {e}")
        raise HTTPException(status_code=500, detail="Authentication failed")

@router.post("/logout")
async def logout(response: Response):
    """Clear authentication cookie"""
    if Config.ENVIRONMENT == "production":
        cookie_secure = True
        cookie_samesite = "lax"
    else:
        cookie_secure = True  # When HTTPS is used
        cookie_samesite = "none"
    response.delete_cookie(
        key="access_token",
        path="/",
        domain=None,
        samesite=cookie_samesite,
        secure=cookie_secure
    )
    return {"success": True, "message": "Logged out successfully"}

@router.get("/me")
async def get_current_user(current_user: dict = Depends(verify_jwt_dependency)):
    """Get authenticated user information from JWT token"""
    return {
        "user_id": current_user["user_id"],
        "wallet_address": current_user["wallet_address"],  
        "nickname": current_user["nickname"]
    }

# ============================================
# DEV/UAT ONLY ROUTES - Conditional registration
# ============================================

if Config.ENVIRONMENT != "production":
    
    @router.post("/test-verify", response_model=TestAuthResponse)
    async def test_verify_without_signature(
        request: NonceRequest,
        db: AsyncSession = Depends(get_async_db)
    ):
        """TEST ONLY: Create user and JWT without signature verification"""
        try:
            # Check if user already exists
            existing_user = await web3_auth_service.get_user_by_wallet(
                request.wallet_address,
                db
            )
            is_new_user = existing_user is None
            
            user = await web3_auth_service.create_or_get_user(
                wallet_address=request.wallet_address,
                nickname=f"TestUser{request.wallet_address[2:8]}",
                referral_code=request.referral_code,
                db=db
            )
            
            cards_granted_count = 0
            packs_granted_count = 0
            
            # Grant starter packs to new users: off-chain only (UserPack rows).
            if is_new_user:
                try:
                    granted_packs = await user_pack_grant_service.grant_all_active_packs_to_user(
                        user_id=user.id,
                        source="admin",
                    )
                    packs_granted_count = len(granted_packs)
                    logger.info(
                        "Granted %s test packs (off-chain) to new user %s",
                        packs_granted_count,
                        user.id,
                    )
                except Exception as pack_error:
                    logger.error(
                        "Error granting test packs to user %s: %s",
                        user.id,
                        pack_error,
                    )
            
            # Create JWT
            access_token = web3_auth_service.create_jwt_token(user)
            
            # Return token in body (for tests)
            response_data = {
                "access_token": access_token,
                "token_type": "bearer",
                "expires_in": 604800,
                "user": {
                    "id": user.id,
                    "wallet_address": user.wallet_address,
                    "nickname": user.nickname,
                    "referral_route": user.referral_route,
                    "avatar_url": user.avatar_url,
                    "created_at": user.created_at.isoformat()
                }
            }
            
            # Include granted packs for new users
            if is_new_user:
                response_data["cards_granted"] = cards_granted_count
                response_data["packs_granted"] = packs_granted_count
            
            return TestAuthResponse(**response_data)
        except Exception as e:
            logger.error(f"Error in test verify: {e}")
            raise HTTPException(status_code=500, detail="Test authentication failed")

    
    @router.post("/grant-packs")
    async def grant_packs_to_user(
        target_user_id: int,
        current_user: dict = Depends(verify_jwt_dependency)
    ):
        """DEV ONLY: Manually grant all available packs to a user"""
        try:
            granted_packs = await user_pack_grant_service.grant_all_active_packs_to_user(
                user_id=target_user_id,
                source="admin"
            )
            return {
                "success": True,
                "packs_granted": len(granted_packs),
                "message": f"Successfully granted {len(granted_packs)} packs to user {target_user_id}"
            }
        except ValueError:
            raise HTTPException(status_code=404, detail="Not found")
        except Exception as e:
            logger.error(f"Error granting packs to user {target_user_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to grant packs")
