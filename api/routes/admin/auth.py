from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, status, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from pydantic import BaseModel
import logging

from config import Config

from slowapi import Limiter
from slowapi.util import get_remote_address

# Setup
logger = logging.getLogger(__name__)
security = HTTPBearer()
limiter = Limiter(key_func=get_remote_address)

# ===== ФУНКЦИИ =====

def create_access_token(data: dict) -> str:
    """Create JWT access token for admin"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=Config.ADMIN_JWT_EXPIRE_HOURS)
    to_encode.update({"exp": expire, "type": "admin"})  # Помечаем тип токена
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
        
        # Проверяем тип токена
        if payload.get("type") != "admin":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type"
            )
        
        username: str = payload.get("sub")
        if username is None or username != Config.ADMIN_USERNAME:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Access denied",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return payload
        
    except JWTError as e:
        logger.warning(f"🚨 Invalid admin token attempt: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access denied",
            headers={"WWW-Authenticate": "Bearer"},
        )


def authenticate_admin(username: str, password: str) -> bool:
    """Authenticate admin credentials"""
    return (
        username == Config.ADMIN_USERNAME and
        password == Config.ADMIN_PASSWORD 
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
async def system_login(request: LoginRequest, req: Request):
    """System authentication endpoint"""
    
    client_ip = req.client.host
    
    # Аутентификация
    if not authenticate_admin(request.username, request.password):
        # Логируем неудачную попытку
        logger.warning(
            f"🚨 Failed admin login attempt: username={request.username}, ip={client_ip}"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed"
        )
    
    # Успешная аутентификация
    logger.info(f"✅ Admin login successful: {request.username} from {client_ip}")
    
    access_token = create_access_token(
        data={
            "sub": request.username, 
            "role": "system_admin",
            "ip": client_ip  # Записываем IP в токен
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
    """Logout endpoint (для симметрии, токен остается валидным до истечения)"""
    logger.info(f"Admin logout: {payload.get('sub')}")
    return {"message": "Logged out successfully"}