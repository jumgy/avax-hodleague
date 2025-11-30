# api/routes/admin/users.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, validator
from datetime import datetime

from models.database import get_sync_db
from models.user_models import User
from .auth import verify_admin_token

# Pydantic models
class UserUpdate(BaseModel):
    nickname: Optional[str] = None
    referral_route: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: Optional[bool] = None
    
    @validator('nickname')
    def validate_nickname(cls, v):
        if v is not None:
            v = v.strip()
            if len(v) < 2 or len(v) > 50:
                raise ValueError('Nickname must be between 2 and 50 characters')
        return v
    
    @validator('referral_route')
    def validate_referral_route(cls, v):
        if v is not None:
            v = v.strip()
            if len(v) < 4 or len(v) > 20:
                raise ValueError('Referral route must be between 4 and 20 characters')
        return v
    
    @validator('avatar_url')
    def validate_avatar_url(cls, v):
        if v is not None:
            v = v.strip()
            if not v.startswith(('http://', 'https://')):
                raise ValueError('Avatar URL must start with http:// or https://')
        return v

class UserResponse(BaseModel):
    id: int
    wallet_address: str
    nickname: str
    referral_route: str
    avatar_url: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    # Computed fields
    wallet_short: str
    days_since_registration: int
    
    class Config:
        from_attributes = True

# Router
router = APIRouter(prefix="/panel/users")

@router.get("/", response_model=List[UserResponse])
async def get_all_users(
    active_only: bool = Query(False, description="Filter only active users"),
    search: Optional[str] = Query(None, description="Search by nickname or wallet address"),
    limit: int = Query(100, le=1000, description="Limit results (max 1000)"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    """Get all users for admin panel with filtering and pagination"""
    query = db.query(User)
    
    if active_only:
        query = query.filter(User.is_active == True)
    
    if search:
        search_term = f"%{search.lower()}%"
        query = query.filter(
            User.nickname.ilike(search_term) | 
            User.wallet_address.ilike(search_term) |
            User.referral_route.ilike(search_term)
        )
    
    # Get total count for pagination info
    total_count = query.count()
    
    # Apply pagination
    users = query.order_by(User.created_at.desc()).offset(offset).limit(limit).all()
    
    # Add computed fields
    result = []
    for user in users:
        days_since_registration = (datetime.utcnow() - user.created_at).days
        
        user_dict = {
            "id": user.id,
            "wallet_address": user.wallet_address,
            "nickname": user.nickname,
            "referral_route": user.referral_route,
            "avatar_url": user.avatar_url,
            "is_active": user.is_active,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
            "wallet_short": f"{user.wallet_address[:6]}...{user.wallet_address[-4:]}",
            "days_since_registration": days_since_registration
        }
        result.append(UserResponse(**user_dict))
    
    # Add pagination metadata to response headers (можно также вернуть в теле)
    return result

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    """Get specific user by ID"""
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    days_since_registration = (datetime.utcnow() - user.created_at).days
    
    user_dict = {
        "id": user.id,
        "wallet_address": user.wallet_address,
        "nickname": user.nickname,
        "referral_route": user.referral_route,
        "avatar_url": user.avatar_url,
        "is_active": user.is_active,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "wallet_short": f"{user.wallet_address[:6]}...{user.wallet_address[-4:]}",
        "days_since_registration": days_since_registration
    }
    
    return UserResponse(**user_dict)

@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    """Update existing user (wallet_address cannot be changed)"""
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check nickname uniqueness if being updated
    if user_data.nickname and user_data.nickname != user.nickname:
        existing = db.query(User).filter(User.nickname == user_data.nickname).first()
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"User with nickname '{user_data.nickname}' already exists"
            )
    
    # Check referral_route uniqueness if being updated
    if user_data.referral_route and user_data.referral_route != user.referral_route:
        existing = db.query(User).filter(User.referral_route == user_data.referral_route).first()
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Referral route '{user_data.referral_route}' already exists"
            )
    
    # Update fields (wallet_address is readonly)
    update_data = user_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)
    
    user.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(user)
    
    # Return with computed fields
    days_since_registration = (datetime.utcnow() - user.created_at).days
    
    user_dict = {
        "id": user.id,
        "wallet_address": user.wallet_address,
        "nickname": user.nickname,
        "referral_route": user.referral_route,
        "avatar_url": user.avatar_url,
        "is_active": user.is_active,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "wallet_short": f"{user.wallet_address[:6]}...{user.wallet_address[-4:]}",
        "days_since_registration": days_since_registration
    }
    
    return UserResponse(**user_dict)

@router.get("/stats/summary", tags=["User Statistics"])
async def get_users_summary(
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    """Get users statistics summary"""
    total_users = db.query(User).count()
    active_users = db.query(User).filter(User.is_active == True).count()
    inactive_users = total_users - active_users
    
    # Последние 7 дней регистраций
    from datetime import timedelta
    week_ago = datetime.utcnow() - timedelta(days=7)
    recent_registrations = db.query(User).filter(User.created_at >= week_ago).count()
    
    # Последние 24 часа регистраций
    day_ago = datetime.utcnow() - timedelta(days=1)
    daily_registrations = db.query(User).filter(User.created_at >= day_ago).count()
    
    # Самые популярные начала никнеймов
    popular_nickname_prefixes = db.execute("""
        SELECT LEFT(nickname, 3) as prefix, COUNT(*) as count 
        FROM users 
        WHERE is_active = true 
        GROUP BY LEFT(nickname, 3) 
        ORDER BY count DESC 
        LIMIT 5
    """).fetchall()
    
    return {
        "total_users": total_users,
        "active_users": active_users,
        "inactive_users": inactive_users,
        "recent_registrations_7d": recent_registrations,
        "recent_registrations_24h": daily_registrations,
        "popular_nickname_prefixes": [
            {"prefix": row[0], "count": row[1]} 
            for row in popular_nickname_prefixes
        ]
    }

@router.get("/search/duplicates", tags=["User Management"])
async def find_duplicate_patterns(
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    """Find users with similar nicknames or potential duplicates"""
    
    # Находим пользователей с похожими nickname паттернами
    similar_nicknames = db.execute("""
        SELECT nickname, COUNT(*) as count
        FROM users 
        WHERE nickname SIMILAR TO 'Player[0-9]+' OR nickname SIMILAR TO 'TestUser[0-9]+'
        GROUP BY nickname 
        HAVING COUNT(*) > 1
        ORDER BY count DESC
        LIMIT 10
    """).fetchall()
    
    # Находим пользователей, созданных в одну минуту (подозрительно)
    suspicious_registrations = db.execute("""
        SELECT DATE_TRUNC('minute', created_at) as minute_created, 
               COUNT(*) as count,
               ARRAY_AGG(nickname) as nicknames
        FROM users 
        GROUP BY DATE_TRUNC('minute', created_at)
        HAVING COUNT(*) > 5
        ORDER BY count DESC
        LIMIT 5
    """).fetchall()
    
    return {
        "duplicate_nicknames": [
            {"nickname": row[0], "count": row[1]} 
            for row in similar_nicknames
        ],
        "suspicious_mass_registrations": [
            {
                "minute": row[0].isoformat() if row[0] else None,
                "count": row[1],
                "sample_nicknames": row[2][:5] if row[2] else []
            }
            for row in suspicious_registrations
        ]
    }