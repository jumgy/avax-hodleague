# api/routes/admin_upload.py

import os
import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Form, Depends
from .auth import verify_admin_token
from fastapi.responses import JSONResponse
from config import Config
import aiofiles
import uuid
import re
import os.path

from services.card_render_service import card_render_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/panel/upload")

# Путь к папке с шаблонами
TEMPLATES_DIR = "/app/static/card_templates"
RENDERS_DIR = "/app/static/card_renders"

# Создаём папки если их нет
os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(RENDERS_DIR, exist_ok=True)

# Разрешённые форматы
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

def get_file_extension(filename: str) -> str:
    """Get file extension"""
    return os.path.splitext(filename)[1].lower()

def is_allowed_file(filename: str) -> bool:
    """Check if file extension is allowed"""
    return get_file_extension(filename) in ALLOWED_EXTENSIONS

def sanitize_filename(text: str) -> str:
    """
    Sanitize text for use in filename.
    Removes special characters, converts to lowercase.
    Example: "Bitcoin (BTC)" -> "bitcoin_btc"
    """
    # Remove special characters, keep only alphanumeric and spaces
    text = re.sub(r'[^\w\s-]', '', text.lower())
    # Replace spaces with underscores
    text = re.sub(r'[\s_]+', '_', text)
    return text.strip('_')

@router.post("/card-template")
async def upload_card_template(
    file: UploadFile = File(...),
    token_symbol: str = Form(...),
    design_type: str = Form(...),
    rarity: str = Form(...),
    admin: dict = Depends(verify_admin_token)

):
    """
    Upload a card template image (base design without text).
    
    Returns URL that can be used in template_image_url field when creating a card.
    
    Example:
        curl -X POST http://localhost:6000/panel/upload/card-template \
          -F "file=@template.png" \
          -F "token_symbol=BTC" \
          -F "design_type=classic" \
          -F "rarity=rare"
    
    Filename format: {token_symbol}_{design_type}_{rarity}_{timestamp}.png
    Example: btc_classic_rare_20241229_143022.png
    """
    try:
        # Validate file
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")
        
        if not is_allowed_file(file.filename):
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
            )
        
        # Validate required fields
        if not token_symbol or not design_type or not rarity:
            raise HTTPException(
                status_code=400,
                detail="token_symbol, design_type, and rarity are required"
            )
        
        # Read file content
        content = await file.read()
        file_size = len(content)
        
        if file_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Max size: {MAX_FILE_SIZE / 1024 / 1024}MB"
            )
        
        # Generate filename: token_design_rarity_timestamp.png
        file_ext = get_file_extension(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Sanitize inputs
        token_clean = sanitize_filename(token_symbol)
        design_clean = sanitize_filename(design_type)
        rarity_clean = sanitize_filename(rarity)
        
        # Build filename
        filename = f"{token_clean}_{design_clean}_{rarity_clean}_{timestamp}{file_ext}"
        file_path = os.path.join(TEMPLATES_DIR, filename)
        
        # Save file
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(content)
        
        # Generate URL
        base_url = os.getenv("STATIC_BASE_URL", "http://localhost:8080")
        file_url = f"{base_url}/static/card_templates/{filename}"
        
        logger.info(f"✅ Template uploaded: {filename} ({file_size / 1024:.2f} KB)")
        
        return {
            "success": True,
            "filename": filename,
            "url": file_url,
            "size_kb": round(file_size / 1024, 2),
            "token_symbol": token_symbol,
            "design_type": design_type,
            "rarity": rarity,
            "message": "Template uploaded successfully. Use this URL in template_image_url field."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Upload failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.get("/templates")
async def list_templates(
    admin: dict = Depends(verify_admin_token)
):
    """
    List all uploaded card templates.
    Useful for seeing what templates are available.
    """
    try:
        templates = []
        base_url = os.getenv("STATIC_BASE_URL", "http://localhost:8080")
        
        for filename in os.listdir(TEMPLATES_DIR):
            if is_allowed_file(filename):
                file_path = os.path.join(TEMPLATES_DIR, filename)
                file_size = os.path.getsize(file_path)
                file_url = f"{base_url}/static/card_templates/{filename}"
                
                # Parse filename to extract info
                # Format: token_design_rarity_timestamp.png
                parts = filename.rsplit('.', 1)[0].split('_')
                
                info = {
                    "filename": filename,
                    "url": file_url,
                    "size_kb": round(file_size / 1024, 2)
                }
                
                # Try to parse metadata from filename
                if len(parts) >= 3:
                    info["token_symbol"] = parts[0].upper()
                    info["design_type"] = parts[1]
                    info["rarity"] = parts[2]
                
                templates.append(info)
        
        return {
            "success": True,
            "total": len(templates),
            "templates": sorted(templates, key=lambda x: x['filename'])
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to list templates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/template/{filename}")
async def delete_template(
    filename: str,
    admin: dict = Depends(verify_admin_token)
):
    try:
        # ✅ Проверка 1: Запретить path traversal символы
        if '..' in filename or '/' in filename or '\\' in filename:
            raise HTTPException(400, "Invalid filename: path traversal detected")
        
        # ✅ Проверка 2: Только разрешённые расширения
        if not is_allowed_file(filename):
            raise HTTPException(400, "Invalid file type")
        
        # ✅ Проверка 3: Построить полный путь
        file_path = os.path.join(TEMPLATES_DIR, filename)
        
        # ✅ Проверка 4: Убедиться что путь внутри TEMPLATES_DIR
        real_path = os.path.realpath(file_path)
        real_templates_dir = os.path.realpath(TEMPLATES_DIR)
        
        if not real_path.startswith(real_templates_dir):
            logger.warning(f"⚠️ Path traversal attempt blocked: {filename}")
            raise HTTPException(403, "Access denied")
        
        # ✅ Проверка 5: Файл существует
        if not os.path.exists(real_path):
            raise HTTPException(404, "Template not found")
        
        # ✅ Безопасное удаление
        os.remove(real_path)
        logger.info(f"🗑️ Template deleted by {admin['username']}: {filename}")
        
        return {
            "success": True,
            "message": f"Template {filename} deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to delete template: {e}")
        raise HTTPException(500, f"Failed to delete: {str(e)}")


@router.post("/render-card/{card_id}")
async def render_card_manually(
    card_id: int,
    admin: dict = Depends(verify_admin_token)
):
    """
    Manually trigger rendering for a specific card.
    Useful for testing.
    """
    try:
        logger.info(f"🎨 Manual render requested for card {card_id}")
        
        result_url = await card_render_service.render_card_by_id(card_id)
        
        if result_url:
            return {
                "success": True,
                "card_id": card_id,
                "rendered_url": result_url,
                "message": "Card rendered successfully"
            }
        else:
            raise HTTPException(status_code=500, detail="Rendering failed")
            
    except Exception as e:
        logger.error(f"❌ Manual render failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/render-all-cards")
async def render_all_cards_manually(
    admin: dict = Depends(verify_admin_token)
):
    """
    Manually trigger rendering for all active cards.
    Use with caution - may take a while!
    """
    try:
        logger.info("🎨 Manual render requested for ALL cards")
        
        result = await card_render_service.render_all_active_cards()
        
        return {
            "success": True,
            "total": result["total"],
            "success_count": result["success"],
            "failed_count": result["failed"],
            "message": f"Rendered {result['success']} out of {result['total']} cards"
        }
            
    except Exception as e:
        logger.error(f"❌ Batch render failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))