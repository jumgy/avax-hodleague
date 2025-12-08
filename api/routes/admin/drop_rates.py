from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_
from typing import List, Optional
from pydantic import BaseModel, validator
from decimal import Decimal
from datetime import datetime

from models.database import get_sync_db
from models.pack_probability_models import PackRarityConfig, CardWeight
from models.pack_models import PackType
from models.rarity_models import Rarity
from models.card_models import Card
from models.token_models import Token
from .auth import verify_admin_token

# --- Pydantic models ---

class PackRarityConfigCreate(BaseModel):
    pack_type_id: int
    rarity_id: int
    drop_rate: Decimal

    @validator('pack_type_id')
    def validate_pack_type_id(cls, v):
        if v is None or v <= 0:
            raise ValueError('Pack type ID is required and must be positive')
        return v

    @validator('rarity_id')
    def validate_rarity_id(cls, v):
        if v is None or v <= 0:
            raise ValueError('Rarity ID is required and must be positive')
        return v

    @validator('drop_rate')
    def validate_drop_rate(cls, v):
        if v < 0 or v > 1:
            raise ValueError("Drop rate must be between 0 and 1 (as a fraction)")
        return v

class PackRarityConfigUpdate(BaseModel):
    drop_rate: Decimal

    @validator('drop_rate')
    def validate_drop_rate(cls, v):
        if v < 0 or v > 1:
            raise ValueError("Drop rate must be between 0 and 1 (as a fraction)")
        return v

class PackRarityConfigResponse(BaseModel):
    id: int
    pack_type_id: int
    rarity_id: int
    drop_rate: Decimal
    created_at: datetime
    updated_at: datetime
    # Связанные данные для удобства
    pack_type_name: Optional[str] = None
    rarity_name: Optional[str] = None
    rarity_color: Optional[str] = None

    class Config:
        from_attributes = True

class PaginatedPackRarityConfigResponse(BaseModel):
    items: List[PackRarityConfigResponse]
    total: int
    skip: int
    limit: int
    has_next: bool
    has_prev: bool

class CardWeightCreate(BaseModel):
    card_id: int
    base_weight: Decimal
    current_multiplier: Decimal = Decimal("1.0000")

    @validator('card_id')
    def validate_card_id(cls, v):
        if v is None or v <= 0:
            raise ValueError('Card ID is required and must be positive')
        return v

    @validator('base_weight', 'current_multiplier')
    def validate_weights(cls, v):
        if v <= 0:
            raise ValueError("Weights must be positive")
        return v

class CardWeightUpdate(BaseModel):
    base_weight: Optional[Decimal] = None
    current_multiplier: Optional[Decimal] = None

    @validator('base_weight', 'current_multiplier')
    def validate_weights(cls, v):
        if v is not None and v <= 0:
            raise ValueError("Weights must be positive")
        return v

class CardWeightResponse(BaseModel):
    id: int
    card_id: int
    base_weight: Decimal
    current_multiplier: Decimal
    last_updated: datetime
    # Связанные данные для удобства
    card_design_type: Optional[str] = None
    token_name: Optional[str] = None
    token_symbol: Optional[str] = None
    rarity_name: Optional[str] = None
    rarity_color: Optional[str] = None
    final_weight: Optional[float] = None

    class Config:
        from_attributes = True

class PaginatedCardWeightResponse(BaseModel):
    items: List[CardWeightResponse]
    total: int
    skip: int
    limit: int
    has_next: bool
    has_prev: bool

# --- Routers ---

router = APIRouter(prefix="/management/pack-configs")

# --- PackRarityConfig Endpoints ---

@router.get("/pack-rarity-configs", response_model=PaginatedPackRarityConfigResponse)
async def get_pack_rarity_configs(
    # Пагинация
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=1000, description="Maximum number of records to return"),
    
    # Фильтры по основным полям
    id: Optional[int] = Query(None, description="Filter by config ID"),
    pack_type_id: Optional[int] = Query(None, description="Filter by pack type ID"),
    rarity_id: Optional[int] = Query(None, description="Filter by rarity ID"),
    drop_rate_from: Optional[Decimal] = Query(None, description="Minimum drop rate"),
    drop_rate_to: Optional[Decimal] = Query(None, description="Maximum drop rate"),
    
    # Фильтры по датам
    created_from: Optional[datetime] = Query(None, description="Filter configs created after this date"),
    created_to: Optional[datetime] = Query(None, description="Filter configs created before this date"),
    updated_from: Optional[datetime] = Query(None, description="Filter configs updated after this date"),
    updated_to: Optional[datetime] = Query(None, description="Filter configs updated before this date"),
    
    # Фильтры по связанным данным
    pack_type_name: Optional[str] = Query(None, description="Filter by pack type name (partial match)"),
    rarity_name: Optional[str] = Query(None, description="Filter by rarity name (partial match)"),
    
    # Сортировка
    sort_by: str = Query("id", regex="^(id|pack_type_id|rarity_id|drop_rate|created_at|updated_at)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    """
    Получить конфигурации редкости паков с фильтрацией, сортировкой и пагинацией
    Использует эффективную загрузку связанных данных без N+1 проблемы
    """
    
    # Базовый запрос с эффективной загрузкой связанных данных
    query = db.query(PackRarityConfig).options(
        joinedload(PackRarityConfig.pack_type),
        joinedload(PackRarityConfig.rarity)
    )
    
    # Применяем фильтры к основной таблице
    if id is not None:
        query = query.filter(PackRarityConfig.id == id)
    
    if pack_type_id is not None:
        query = query.filter(PackRarityConfig.pack_type_id == pack_type_id)
    
    if rarity_id is not None:
        query = query.filter(PackRarityConfig.rarity_id == rarity_id)
    
    if drop_rate_from is not None:
        query = query.filter(PackRarityConfig.drop_rate >= drop_rate_from)
    
    if drop_rate_to is not None:
        query = query.filter(PackRarityConfig.drop_rate <= drop_rate_to)
    
    # Фильтры по датам
    if created_from:
        query = query.filter(PackRarityConfig.created_at >= created_from)
    if created_to:
        query = query.filter(PackRarityConfig.created_at <= created_to)
    if updated_from:
        query = query.filter(PackRarityConfig.updated_at >= updated_from)
    if updated_to:
        query = query.filter(PackRarityConfig.updated_at <= updated_to)
    
    # Фильтры по связанным данным (используем уже загруженные отношения)
    if pack_type_name:
        query = query.filter(PackType.name.ilike(f"%{pack_type_name.strip()}%"))
    
    if rarity_name:
        query = query.filter(Rarity.name.ilike(f"%{rarity_name.strip()}%"))
    
    # Подсчитываем общее количество с учетом всех фильтров
    total = query.count()
    
    # Применяем сортировку
    sort_column = getattr(PackRarityConfig, sort_by)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())
    
    # Применяем пагинацию и выполняем запрос
    configs = query.offset(skip).limit(limit).all()
    
    # Формируем результат (связанные данные уже загружены благодаря joinedload)
    result = []
    for config in configs:
        config_data = PackRarityConfigResponse.model_validate(config)
        
        # Добавляем данные связанных объектов
        if config.pack_type:
            config_data.pack_type_name = config.pack_type.name
        
        if config.rarity:
            config_data.rarity_name = config.rarity.name
            config_data.rarity_color = config.rarity.color
        
        result.append(config_data)
    
    return PaginatedPackRarityConfigResponse(
        items=result,
        total=total,
        skip=skip,
        limit=limit,
        has_next=(skip + limit) < total,
        has_prev=skip > 0
    )

@router.get("/pack-rarity-configs/{config_id}", response_model=PackRarityConfigResponse)
async def get_pack_rarity_config(
    config_id: int,
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    """Получить конкретную конфигурацию редкости пака по ID с связанными данными"""
    
    config = db.query(PackRarityConfig).options(
        joinedload(PackRarityConfig.pack_type),
        joinedload(PackRarityConfig.rarity)
    ).filter(PackRarityConfig.id == config_id).first()
    
    if not config:
        raise HTTPException(
            status_code=404, 
            detail=f"Pack rarity config with ID {config_id} not found"
        )
    
    # Формируем ответ с связанными данными
    config_data = PackRarityConfigResponse.model_validate(config)
    
    if config.pack_type:
        config_data.pack_type_name = config.pack_type.name
    
    if config.rarity:
        config_data.rarity_name = config.rarity.name
        config_data.rarity_color = config.rarity.color
    
    return config_data


# --- CardWeight Endpoints ---

@router.get("/card-weights", response_model=PaginatedCardWeightResponse)
async def get_card_weights(
    # Пагинация
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(50, ge=1, le=1000, description="Maximum number of records to return"),
    
    # Фильтры по основным полям
    id: Optional[int] = Query(None, description="Filter by weight ID"),
    card_id: Optional[int] = Query(None, description="Filter by card ID"),
    base_weight_from: Optional[Decimal] = Query(None, description="Minimum base weight"),
    base_weight_to: Optional[Decimal] = Query(None, description="Maximum base weight"),
    multiplier_from: Optional[Decimal] = Query(None, description="Minimum multiplier"),
    multiplier_to: Optional[Decimal] = Query(None, description="Maximum multiplier"),
    
    # Фильтры по датам
    last_updated_from: Optional[datetime] = Query(None, description="Filter weights updated after this date"),
    last_updated_to: Optional[datetime] = Query(None, description="Filter weights updated before this date"),
    
    # Фильтры по связанным данным
    design_type: Optional[str] = Query(None, description="Filter by card design type (partial match)"),
    token_name: Optional[str] = Query(None, description="Filter by token name (partial match)"),
    token_symbol: Optional[str] = Query(None, description="Filter by token symbol (partial match)"),
    rarity_name: Optional[str] = Query(None, description="Filter by rarity name (partial match)"),
    
    # Сортировка
    sort_by: str = Query("id", regex="^(id|card_id|base_weight|current_multiplier|last_updated)$"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    """
    Получить веса карточек с фильтрацией, сортировкой и пагинацией
    Использует эффективную загрузку связанных данных без N+1 проблемы
    """
    
    # Базовый запрос с эффективной загрузкой всех связанных данных
    query = db.query(CardWeight).options(
        joinedload(CardWeight.card).joinedload(Card.token),
        joinedload(CardWeight.card).joinedload(Card.rarity)
    )
    
    # Применяем фильтры к основной таблице
    if id is not None:
        query = query.filter(CardWeight.id == id)
    
    if card_id is not None:
        query = query.filter(CardWeight.card_id == card_id)
    
    if base_weight_from is not None:
        query = query.filter(CardWeight.base_weight >= base_weight_from)
    
    if base_weight_to is not None:
        query = query.filter(CardWeight.base_weight <= base_weight_to)
    
    if multiplier_from is not None:
        query = query.filter(CardWeight.current_multiplier >= multiplier_from)
    
    if multiplier_to is not None:
        query = query.filter(CardWeight.current_multiplier <= multiplier_to)
    
    # Фильтры по датам
    if last_updated_from:
        query = query.filter(CardWeight.last_updated >= last_updated_from)
    if last_updated_to:
        query = query.filter(CardWeight.last_updated <= last_updated_to)
    
    # Фильтры по связанным данным
    if design_type:
        query = query.filter(Card.design_type.ilike(f"%{design_type.strip()}%"))
    
    if token_name:
        query = query.filter(Token.name.ilike(f"%{token_name.strip()}%"))
    
    if token_symbol:
        query = query.filter(Token.symbol.ilike(f"%{token_symbol.strip()}%"))
    
    if rarity_name:
        query = query.filter(Rarity.name.ilike(f"%{rarity_name.strip()}%"))
    
    # Подсчитываем общее количество с учетом всех фильтров
    total = query.count()
    
    # Применяем сортировку
    sort_column = getattr(CardWeight, sort_by)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())
    
    # Применяем пагинацию и выполняем запрос
    weights = query.offset(skip).limit(limit).all()
    
    # Формируем результат (связанные данные уже загружены благодаря joinedload)
    result = []
    for weight in weights:
        weight_data = CardWeightResponse.model_validate(weight)
        
        # Вычисляем финальный вес
        weight_data.final_weight = float(weight.base_weight) * float(weight.current_multiplier)
        
        # Добавляем данные связанных объектов
        if weight.card:
            weight_data.card_design_type = weight.card.design_type
            
            if weight.card.token:
                weight_data.token_name = weight.card.token.name
                weight_data.token_symbol = weight.card.token.symbol
            
            if weight.card.rarity:
                weight_data.rarity_name = weight.card.rarity.name
                weight_data.rarity_color = weight.card.rarity.color
        
        result.append(weight_data)
    
    return PaginatedCardWeightResponse(
        items=result,
        total=total,
        skip=skip,
        limit=limit,
        has_next=(skip + limit) < total,
        has_prev=skip > 0
    )

@router.get("/card-weights/{weight_id}", response_model=CardWeightResponse)
async def get_card_weight(
    weight_id: int,
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    """Получить конкретный вес карточки по ID с связанными данными"""
    
    weight = db.query(CardWeight).options(
        joinedload(CardWeight.card).joinedload(Card.token),
        joinedload(CardWeight.card).joinedload(Card.rarity)
    ).filter(CardWeight.id == weight_id).first()
    
    if not weight:
        raise HTTPException(
            status_code=404, 
            detail=f"Card weight with ID {weight_id} not found"
        )
    
    # Формируем ответ с связанными данными
    weight_data = CardWeightResponse.model_validate(weight)
    weight_data.final_weight = float(weight.base_weight) * float(weight.current_multiplier)
    
    if weight.card:
        weight_data.card_design_type = weight.card.design_type
        
        if weight.card.token:
            weight_data.token_name = weight.card.token.name
            weight_data.token_symbol = weight.card.token.symbol
        
        if weight.card.rarity:
            weight_data.rarity_name = weight.card.rarity.name
            weight_data.rarity_color = weight.card.rarity.color
    
    return weight_data


@router.get("/stats/summary")
async def get_pack_configs_stats(
    db: Session = Depends(get_sync_db),
    admin: dict = Depends(verify_admin_token)
):
    """Получить статистику конфигураций паков"""
    
    try:
        # Статистика PackRarityConfig
        total_pack_configs = db.query(PackRarityConfig).count()
        
        # Статистика CardWeight
        total_card_weights = db.query(CardWeight).count()
        configured_cards = db.query(Card).filter(
            Card.id.in_(
                db.query(CardWeight.card_id).subquery()
            ),
            Card.is_active == True
        ).count()
        
        total_active_cards = db.query(Card).filter(Card.is_active == True).count()
        unconfigured_cards = total_active_cards - configured_cards
        
        # Средние значения весов
        avg_base_weight = db.query(CardWeight.base_weight).all()
        avg_multiplier = db.query(CardWeight.current_multiplier).all()
        
        avg_base_weight_value = sum(float(w[0]) for w in avg_base_weight) / len(avg_base_weight) if avg_base_weight else 0
        avg_multiplier_value = sum(float(m[0]) for m in avg_multiplier) / len(avg_multiplier) if avg_multiplier else 0
        
        return {
            "pack_rarity_configs": {
                "total_configs": total_pack_configs
            },
            "card_weights": {
                "total_weights": total_card_weights,
                "configured_cards": configured_cards,
                "unconfigured_cards": unconfigured_cards,
                "total_active_cards": total_active_cards,
                "avg_base_weight": round(avg_base_weight_value, 4),
                "avg_multiplier": round(avg_multiplier_value, 4)
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch pack configs statistics: {str(e)}"
        )