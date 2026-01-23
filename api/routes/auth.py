from fastapi import APIRouter, HTTPException, Header, Depends, Response, Cookie, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from pydantic import BaseModel, validator
from typing import Optional
import logging

from slowapi import Limiter
from slowapi.util import get_remote_address

from models.database import get_async_db 
from sqlalchemy.ext.asyncio import AsyncSession
from services.web3_auth_service import web3_auth_service
from services.user_card_grant_service import user_card_grant_service
from services.user_pack_grant_service import user_pack_grant_service

from config import Config

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)

security_optional = HTTPBearer(auto_error=False)

router = APIRouter(prefix="/auth")


class NonceRequest(BaseModel):
    wallet_address: str

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


class AuthResponse(BaseModel):
    token_type: str = "bearer"
    expires_in: int = 604800  # 7 дней в секундах
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
    """Response model for test authentication (includes token in body)"""
    access_token: str  # ← Добавляем токен
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
    
    # 1. Пробуем Bearer header (Swagger)
    if credentials:
        token = credentials.credentials
    
    # 2. Если нет, пробуем cookie (фронт)
    if not token:
        token = access_token
    
    # 3. Если токена нет вообще - ошибка
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
async def get_nonce(request: Request, nonce_request: NonceRequest):
    """
    Generate nonce for wallet signature authentication
    Returns a message that should be signed by the user's wallet.
    """
    try:
        message = web3_auth_service.generate_nonce(nonce_request.wallet_address)
        return {
            "message": message,
            "wallet_address": request.wallet_address
        }
    except Exception as e:
        logger.error(f"Error generating nonce: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate nonce")


@router.post("/verify", response_model=AuthResponse)
@limiter.limit("5/minute")
async def verify_signature(
    http_request: Request,
    request: VerifyRequest,
    response: Response,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Verify wallet signature and authenticate user
    Validates the signed message and sets HTTP-only authentication cookie.
    """
    try:
        is_valid = await web3_auth_service.verify_signature(
            request.wallet_address, 
            request.signature
        )
        if not is_valid:
            raise HTTPException(status_code=401, detail="Invalid signature")
        
        # Проверяем, существует ли уже пользователь
        existing_user = await web3_auth_service.get_user_by_wallet(
            request.wallet_address, 
            db
        )
        is_new_user = existing_user is None
        
        user = await web3_auth_service.create_or_get_user(
            wallet_address=request.wallet_address,
            nickname=request.nickname,
            avatar_url=request.avatar_url,
            db=db
        )
        
        cards_granted_count = 0
        packs_granted_count = 0
        
        # Выдаем паки новым пользователям
        if is_new_user:
            try:
                granted_packs = await user_pack_grant_service.grant_all_active_packs_to_user(
                    user_id=user.id,
                    source="reward"
                )
                packs_granted_count = len(granted_packs)
                logger.info(f"Granted {packs_granted_count} starter packs to new user {user.id}")
            except Exception as pack_error:
                logger.error(f"Error granting starter packs to user {user.id}: {pack_error}")
                packs_granted_count = 0
        
        # Создаем JWT токен
        access_token = web3_auth_service.create_jwt_token(user)

        cookie_secure = Config.ENVIRONMENT == "production"  # True только на HTTPS
        cookie_samesite = "lax"
        
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,  # Защита от XSS
            secure=cookie_secure,  # True в production (требует HTTPS)
            samesite=cookie_samesite,  # "lax" защищает от CSRF для same-site
            max_age=604800,  # 7 дней
            path="/",
            domain=None  # Автоматически текущий домен
        )
        
        # Формируем ответ БЕЗ токена в body
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
        
        # Добавляем информацию о выданных паках для новых пользователей
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
    response.delete_cookie(key="access_token", path="/")
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
# DEV/UAT ONLY ROUTES - Условная регистрация
# ============================================

if Config.ENVIRONMENT != "production":
    
    @router.post("/test-verify", response_model=TestAuthResponse)
    async def test_verify_without_signature(
        request: NonceRequest,
        db: AsyncSession = Depends(get_async_db)
    ):
        """TEST ONLY: Create user and JWT without signature verification"""
        try:
            # Проверяем, существует ли уже пользователь
            existing_user = await web3_auth_service.get_user_by_wallet(
                request.wallet_address,
                db
            )
            is_new_user = existing_user is None
            
            user = await web3_auth_service.create_or_get_user(
                wallet_address=request.wallet_address,
                nickname=f"TestUser{request.wallet_address[2:8]}",
                db=db
            )
            
            cards_granted_count = 0
            packs_granted_count = 0
            
            # Выдаем паки новым пользователям
            if is_new_user:
                try:
                    granted_packs = await user_pack_grant_service.grant_all_active_packs_to_user(
                        user_id=user.id,
                        source="admin"
                    )
                    packs_granted_count = len(granted_packs)
                    logger.info(f"Granted {packs_granted_count} test packs to new user {user.id}")
                except Exception as pack_error:
                    logger.error(f"Error granting test packs to user {user.id}: {pack_error}")
                    packs_granted_count = 0
            
            # Создаем JWT токен
            access_token = web3_auth_service.create_jwt_token(user)
            
            # Формируем ответ с токеном в body (для тестов)
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
            
            # Добавляем информацию о выданных паках для новых пользователей
            if is_new_user:
                response_data["cards_granted"] = cards_granted_count
                response_data["packs_granted"] = packs_granted_count
            
            return TestAuthResponse(**response_data)
        except Exception as e:
            logger.error(f"Error in test verify: {e}")
            raise HTTPException(status_code=500, detail="Test authentication failed")

    
    @router.post("/grant-cards")
    async def grant_cards_to_user(
        target_user_id: int,
        current_user: dict = Depends(verify_jwt_dependency)
    ):
        """DEV ONLY: Manually grant all available cards to a user"""
        try:
            granted_cards = await user_card_grant_service.grant_all_active_cards_to_user(
                user_id=target_user_id,
                source="admin"
            )
            return {
                "success": True,
                "cards_granted": len(granted_cards),
                "message": f"Successfully granted {len(granted_cards)} cards to user {target_user_id}"
            }
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error(f"Error granting cards to user {target_user_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to grant cards")

    
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
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error(f"Error granting packs to user {target_user_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to grant packs")
