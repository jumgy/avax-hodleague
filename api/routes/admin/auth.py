from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from pydantic import BaseModel

# Security setup
security = HTTPBearer()

# JWT Settings
JWT_SECRET_KEY = "fantasy-crypto-jwt-7x9K2mP8wQ5rN1vE3bA6yT4uS0nH8gF2cX7zL9pR5wM3qK6vB1nJ4hG8fD0sA5tY"
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 8

# Admin credentials - менее очевидные
ADMIN_USERNAME = "gamemaster_dev"
ADMIN_PASSWORD = "Fcg2025!Tkn$MgmT#Adm9x"

def create_access_token(data: dict) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=JWT_EXPIRE_HOURS)
    to_encode.update({"exp": expire})
    
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt

def verify_admin_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Verify JWT token and return payload"""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        username: str = payload.get("sub")
        if username is None or username != ADMIN_USERNAME:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Access denied",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access denied",
            headers={"WWW-Authenticate": "Bearer"},
        )

def authenticate_admin(username: str, password: str) -> bool:
    """Authenticate admin credentials"""
    return username == ADMIN_USERNAME and password == ADMIN_PASSWORD

# Pydantic models
class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = JWT_EXPIRE_HOURS * 3600

# Router с менее очевидным путем
router = APIRouter(prefix="/management", tags=["System Management"])

@router.post("/auth/signin", response_model=LoginResponse)
async def system_login(request: LoginRequest):
    """System authentication endpoint"""
    if not authenticate_admin(request.username, request.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed"
        )
    
    access_token = create_access_token(data={"sub": request.username, "role": "system_admin"})
    return LoginResponse(
        access_token=access_token,
        expires_in=JWT_EXPIRE_HOURS * 3600
    )

@router.get("/auth/status")
async def check_system_access(payload: dict = Depends(verify_admin_token)):
    """Check system access status"""
    return {
        "authenticated": True, 
        "user": payload.get("sub"),
        "role": payload.get("role"),
        "expires": payload.get("exp")
    }