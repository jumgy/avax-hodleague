# api/routes/auth.py
from fastapi import APIRouter, HTTPException, Header, Depends
from pydantic import BaseModel, validator
from typing import Optional
import logging

from services.web3_auth_service import web3_auth_service

logger = logging.getLogger(__name__)
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
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 604800  # 7 дней
    user: dict

def verify_jwt_dependency(authorization: str = Header(...)):
    """Verify JWT token from Authorization header"""
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise HTTPException(status_code=401, detail="Invalid authentication scheme")
        
        payload = web3_auth_service.verify_jwt_token(token)
        if not payload:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
            
        return payload
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid authorization header format")
    except Exception:
        raise HTTPException(status_code=401, detail="Authentication failed")


@router.post("/nonce")
async def get_nonce(request: NonceRequest):
    """
    Generate nonce for wallet signature authentication
    
    Returns a message that should be signed by the user's wallet.
    """
    try:
        message = web3_auth_service.generate_nonce(request.wallet_address)
        return {
            "message": message,
            "wallet_address": request.wallet_address
        }
    except Exception as e:
        logger.error(f"Error generating nonce: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate nonce")

@router.post("/verify", response_model=AuthResponse)
async def verify_signature(request: VerifyRequest):
    """
    Verify wallet signature and authenticate user
    
    Validates the signed message and returns JWT access token.
    """
    try:
        is_valid = web3_auth_service.verify_signature(
            request.wallet_address, 
            request.signature
        )
        
        if not is_valid:
            raise HTTPException(status_code=401, detail="Invalid signature")
        
        user = web3_auth_service.create_or_get_user(
            wallet_address=request.wallet_address,
            nickname=request.nickname,
            avatar_url=request.avatar_url
        )
        
        access_token = web3_auth_service.create_jwt_token(user)
        
        return AuthResponse(
            access_token=access_token,
            user={
                "id": user.id,
                "wallet_address": user.wallet_address,
                "nickname": user.nickname,
                "referral_route": user.referral_route,
                "avatar_url": user.avatar_url,
                "created_at": user.created_at.isoformat()
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verifying signature: {e}")
        raise HTTPException(status_code=500, detail="Authentication failed")

@router.get("/me")
async def get_current_user(current_user: dict = Depends(verify_jwt_dependency)):
    """Get authenticated user information from JWT token"""
    return {
        "user_id": current_user["user_id"],
        "wallet_address": current_user["wallet_address"],  
        "nickname": current_user["nickname"]
    }

@router.post("/test-verify")
async def test_verify_without_signature(request: NonceRequest):
    """TEST ONLY: Create user and JWT without signature verification"""
    try:
        user = web3_auth_service.create_or_get_user(
            wallet_address=request.wallet_address,
            nickname=f"TestUser{request.wallet_address[2:8]}"
        )
        
        access_token = web3_auth_service.create_jwt_token(user)
        
        return AuthResponse(
            access_token=access_token,
            user={
                "id": user.id,
                "wallet_address": user.wallet_address,
                "nickname": user.nickname,
                "referral_route": user.referral_route,
                "avatar_url": user.avatar_url,
                "created_at": user.created_at.isoformat()
            }
        )
        
    except Exception as e:
        logger.error(f"Error in test verify: {e}")
        raise HTTPException(status_code=500, detail="Test authentication failed")
