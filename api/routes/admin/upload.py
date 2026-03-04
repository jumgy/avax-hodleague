# api/routes/admin/upload.py
import os
import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Form, Depends
from .auth import verify_admin_token
from fastapi.responses import JSONResponse
from config import Config
import uuid
import re
import tempfile
from services.r2_storage import r2_storage
from services.card_render_service import card_render_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/panel/upload")

# Allowed image formats
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
    text = re.sub(r'[^\w\s-]', '', text.lower())
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
    Upload a card template image to Cloudflare R2.
    Returns CDN URL that can be used in template_image_url field.
    
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
        
        # Generate filename
        file_ext = get_file_extension(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Sanitize inputs
        token_clean = sanitize_filename(token_symbol)
        design_clean = sanitize_filename(design_type)
        rarity_clean = sanitize_filename(rarity)
        
        # Build filename
        filename = f"{token_clean}_{design_clean}_{rarity_clean}_{timestamp}{file_ext}"
        
        # Write to temp file then upload to R2
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as temp_file:
            temp_file.write(content)
            temp_path = temp_file.name
        
        try:
            # Upload to R2 under card_templates/
            object_key = f"card_templates/{filename}"
            file_url = r2_storage.upload_file(
                temp_path,
                object_key,
                content_type=f"image/{file_ext[1:]}"  # image/png, image/jpeg
            )
            
            logger.info(f"Template uploaded to R2: {filename} ({file_size / 1024:.2f} KB)")
            
            return {
                "success": True,
                "filename": filename,
                "url": file_url,
                "size_kb": round(file_size / 1024, 2),
                "token_symbol": token_symbol,
                "design_type": design_type,
                "rarity": rarity,
                "message": "Template uploaded successfully to CDN. Use this URL in template_image_url field."
            }
        
        finally:
            # Remove temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Upload failed")
    
from typing import List

@router.post("/card-templates-bulk")
async def upload_card_templates_bulk(
    files: List[UploadFile] = File(...),
    design_type: str = Form("classic"),
    rarity: str = Form("common"),
    admin: dict = Depends(verify_admin_token)
):
    """
    Bulk upload card templates.
    Token symbol is extracted from filename (btc.png → BTC).
    
    Example:
        Upload files: btc.png, eth.png, sol.png
        All will get design_type=classic, rarity=common
    """
    results = []
    errors = []
    
    for file in files:
        try:
            # Validate file
            if not file.filename:
                errors.append({
                    "filename": "unknown",
                    "error": "No filename"
                })
                continue
                
            if not is_allowed_file(file.filename):
                errors.append({
                    "filename": file.filename,
                    "error": f"Invalid file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
                })
                continue
            
            # Extract token symbol from filename (e.g. btc.png -> btc, BTC_template.png -> btc)
            filename_without_ext = os.path.splitext(file.filename)[0]
            token_symbol = re.split(r'[_\-\s]', filename_without_ext)[0].upper()
            
            if not token_symbol:
                errors.append({
                    "filename": file.filename,
                    "error": "Cannot extract token symbol from filename"
                })
                continue
            
            logger.info(f"Processing: {file.filename} -> Token: {token_symbol}")
            
            content = await file.read()
            file_size = len(content)
            
            if file_size > MAX_FILE_SIZE:
                errors.append({
                    "filename": file.filename,
                    "error": f"File too large: {file_size/1024/1024:.1f}MB (max 5MB)"
                })
                continue
            
            # Generate filename
            file_ext = get_file_extension(file.filename)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            token_clean = sanitize_filename(token_symbol)
            design_clean = sanitize_filename(design_type)
            rarity_clean = sanitize_filename(rarity)
            
            new_filename = f"{token_clean}_{design_clean}_{rarity_clean}_{timestamp}{file_ext}"
            
            # Write to temp file
            with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as temp_file:
                temp_file.write(content)
                temp_path = temp_file.name
            
            try:
                # Upload to R2
                object_key = f"card_templates/{new_filename}"
                file_url = r2_storage.upload_file(
                    temp_path,
                    object_key,
                    content_type=f"image/{file_ext[1:]}"
                )
                
                logger.info(f"Uploaded: {new_filename} ({file_size/1024:.1f}KB)")
                
                results.append({
                    "original_filename": file.filename,
                    "uploaded_filename": new_filename,
                    "token_symbol": token_symbol,
                    "url": file_url,
                    "size_kb": round(file_size / 1024, 2)
                })
                
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                    
        except Exception as e:
            logger.error(f"Failed to upload {file.filename}: {e}")
            errors.append({
                "filename": file.filename,
                "error": str(e)
            })
    
    return {
        "success": len(errors) == 0,
        "uploaded": len(results),
        "failed": len(errors),
        "design_type": design_type,
        "rarity": rarity,
        "results": results,
        "errors": errors if errors else None,
        "message": f"Uploaded {len(results)} templates. {len(errors)} failed." if errors else f"Successfully uploaded {len(results)} templates."
    }


@router.get("/templates")
async def list_templates(
    admin: dict = Depends(verify_admin_token)
):
    """
    List all uploaded card templates from R2.
    """
    try:
        # List objects in R2
        response = r2_storage.client.list_objects_v2(
            Bucket=r2_storage.bucket_name,
            Prefix="card_templates/"
        )
        
        templates = []
        
        if 'Contents' in response:
            for obj in response['Contents']:
                filename = obj['Key'].replace('card_templates/', '')
                
                # Skip folder placeholder
                if not filename:
                    continue
                
                file_url = f"{r2_storage.public_url}/{obj['Key']}"
                file_size = obj['Size']
                
                # Parse filename to extract info
                parts = filename.rsplit('.', 1)[0].split('_')
                info = {
                    "filename": filename,
                    "url": file_url,
                    "size_kb": round(file_size / 1024, 2),
                    "last_modified": obj['LastModified'].isoformat()
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
        logger.error(f"Failed to list templates: {e}")
        raise HTTPException(status_code=500, detail="Failed to list templates")


@router.delete("/template/{filename}")
async def delete_template(
    filename: str,
    admin: dict = Depends(verify_admin_token)
):
    """
    Delete a template from R2.
    """
    try:
        # Reject path traversal
        if '..' in filename or '/' in filename or '\\' in filename:
            raise HTTPException(400, "Invalid filename: path traversal detected")
        
        # Only allowed extensions
        if not is_allowed_file(filename):
            raise HTTPException(400, "Invalid file type")
        
        object_key = f"card_templates/{filename}"
        
        if not r2_storage.file_exists(object_key):
            raise HTTPException(404, "Template not found")
        
        success = r2_storage.delete_file(object_key)
        
        if success:
            logger.info(f"Template deleted from R2 by {admin.get('sub', 'admin')}: {filename}")
            return {
                "success": True,
                "message": f"Template {filename} deleted successfully from CDN"
            }
        else:
            raise HTTPException(500, "Failed to delete from CDN")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete template: {e}")
        raise HTTPException(500, "Failed to delete template")


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
        logger.info(f"Manual render requested for card {card_id}")
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
        logger.error(f"Manual render failed: {e}")
        raise HTTPException(status_code=500, detail="Rendering failed")


@router.post("/render-all-cards")
async def render_all_cards_manually(
    admin: dict = Depends(verify_admin_token)
):
    """
    Manually trigger rendering for all active cards.
    Use with caution - may take a while!
    """
    try:
        logger.info("Manual render requested for ALL cards")
        result = await card_render_service.render_all_active_cards()
        
        return {
            "success": True,
            "total": result["total"],
            "success_count": result["success"],
            "failed_count": result["failed"],
            "message": f"Rendered {result['success']} out of {result['total']} cards"
        }
    
    except Exception as e:
        logger.error(f"Batch render failed: {e}")
        raise HTTPException(status_code=500, detail="Batch render failed")