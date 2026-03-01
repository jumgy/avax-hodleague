import logging
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, status, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from pydantic import BaseModel

from config import Config
from utils.rate_limit import limiter

# Setup
logger = logging.getLogger(__name__)
security = HTTPBearer()

# ===== Helpers =====

def create_access_token(data: dict) -> str:
    """Create JWT access token for admin"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=Config.ADMIN_JWT_EXPIRE_HOURS)
    to_encode.update({"exp": expire, "type": "admin"})  # Mark token type
    encoded_jwt = jwt.encode(
        to_encode, 
        Config.ADMIN_JWT_SECRET_KEY,
        algorithm="HS256"
    )
    return encoded_jwt


def verify_admin_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Verify JWT token and return payload"""
    try:
        payload = jwt.decode(
            credentials.credentials, 
            Config.ADMIN_JWT_SECRET_KEY,
            algorithms=["HS256"],
            options={"verify_signature": True} 
        )
        
        # Check token type
        if payload.get("type") != "admin":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type"
            )
        
        username: str = payload.get("sub")
        if username is None or not secrets.compare_digest(
            username.encode("utf-8"), Config.ADMIN_USERNAME.encode("utf-8")
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Access denied",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return payload
        
    except JWTError as e:
        logger.warning(f"Invalid admin token attempt: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access denied",
            headers={"WWW-Authenticate": "Bearer"},
        )


def authenticate_admin(username: str, password: str) -> bool:
    """Authenticate admin credentials. Uses constant-time comparison to prevent timing attacks."""
    expected_user = Config.ADMIN_USERNAME.encode("utf-8")
    expected_pass = Config.ADMIN_PASSWORD.encode("utf-8")
    return (
        secrets.compare_digest(username.encode("utf-8"), expected_user)
        and secrets.compare_digest(password.encode("utf-8"), expected_pass)
    )


# ===== PYDANTIC MODELS =====

class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


# ===== ROUTER =====

router = APIRouter(prefix="/panel")


@router.post("/auth/signin", response_model=LoginResponse)
@limiter.limit("5/minute")
@limiter.limit("20/hour")
async def system_login(request: Request, body: LoginRequest):
    """System authentication endpoint"""
    client_ip = request.client.host
    
    if not authenticate_admin(body.username, body.password):
        logger.warning(
            f"Failed admin login attempt: username={body.username}, ip={client_ip}"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed"
        )
    
    logger.info(f"Admin login successful: {body.username} from {client_ip}")
    
    access_token = create_access_token(
        data={
            "sub": body.username,
            "role": "system_admin",
            "ip": client_ip
        }
    )
    
    return LoginResponse(
        access_token=access_token,
        expires_in=Config.ADMIN_JWT_EXPIRE_HOURS * 3600
    )


@router.get("/auth/status")
async def check_system_access(payload: dict = Depends(verify_admin_token)):
    """Check system access status"""
    return {
        "authenticated": True, 
        "user": payload.get("sub"),
        "role": payload.get("role"),
        "expires": payload.get("exp"),
        "environment": Config.ENVIRONMENT
    }


@router.post("/auth/logout")
async def logout(payload: dict = Depends(verify_admin_token)):
    """Logout endpoint (token remains valid until expiry)."""
    logger.info(f"Admin logout: {payload.get('sub')}")
    return {"message": "Logged out successfully"}