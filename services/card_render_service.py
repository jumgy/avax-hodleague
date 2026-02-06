import os
import logging
from datetime import datetime
from typing import Optional
from PIL import Image, ImageDraw, ImageFont
from decimal import Decimal
from models.database import DatabaseSession
from sqlalchemy import select, and_, text
from models.card_models import Card
from models.token_models import Token, TokenPrice
from config import Config
import tempfile
import requests
from services.r2_storage import r2_storage

logger = logging.getLogger(__name__)


class CardRenderService:
    """Service for rendering card images with dynamic text overlay"""
    
    FONTS_DIR = "/app/static/fonts"
    
    # Card dimensions (4x scale from Figma)
    CARD_WIDTH = 666
    CARD_HEIGHT = 1044

    OUTPUT_WIDTH = 444
    OUTPUT_HEIGHT = 696
    
    # Font paths
    FONT_INSTRUMENT_SANS_SEMIBOLD = os.path.join(FONTS_DIR, "InstrumentSans-SemiBold.ttf")
    FONT_LEAGUE_GOTHIC = os.path.join(FONTS_DIR, "LeagueGothic-Regular.ttf")
    FONT_LEAGUE_GOTHIC_CONDENSED = os.path.join(FONTS_DIR, "LeagueGothic-Condensed.ttf")
    
    # Text opacity
    TEXT_OPACITY = 0.8  # 80%
    
    def __init__(self):
        pass
    
    def _get_weight_text(self, weight: int) -> str:
        """Convert weight number to text: Low/Medium/High"""
        if weight in [8, 9, 10]:
            return "HIGH"
        elif weight in [4, 5, 6, 7]:
            return "MEDIUM"
        elif weight in [1, 2, 3]:
            return "LOW"
        else:
            return "MEDIUM"
    
    def _format_market_cap(self, market_cap: Optional[int]) -> str:
        """Format market cap to readable string: $353B (without decimals)"""
        if not market_cap or market_cap == 0:
            return "$0"
        
        if market_cap >= 1_000_000_000:
            value = market_cap / 1_000_000_000
            return f"${int(round(value))}B"
        elif market_cap >= 1_000_000:
            value = market_cap / 1_000_000
            return f"${int(round(value))}M"
        elif market_cap >= 1_000:
            value = market_cap / 1_000
            return f"${int(round(value))}K"
        else:
            return f"${int(market_cap)}"
    
    def _load_fonts(self):
        """Load fonts with exact Figma specifications"""
        try:
            font_small = ImageFont.truetype(self.FONT_INSTRUMENT_SANS_SEMIBOLD, size=20)
            
            if os.path.exists(self.FONT_LEAGUE_GOTHIC_CONDENSED):
                font_large = ImageFont.truetype(self.FONT_LEAGUE_GOTHIC_CONDENSED, size=105)
            else:
                font_large = ImageFont.truetype(self.FONT_LEAGUE_GOTHIC, size=105)
            
            return font_small, font_large
        except Exception as e:
            logger.error(f"Failed to load fonts: {e}")
            default = ImageFont.load_default()
            return default, default
    
    def _draw_condensed_number(self, draw, text, position, font, fill, anchor="lb", squeeze_factor=0.75):
        """
        Рисует число с эффектом сжатия по горизонтали (condensed).
        """
        bbox = draw.textbbox((0, 0), text, font=font, anchor="lt")
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        temp_size = (int(text_width * 1.5), int(text_height * 1.5))
        temp_layer = Image.new('RGBA', temp_size, (255, 255, 255, 0))
        temp_draw = ImageDraw.Draw(temp_layer)
        
        temp_draw.text(
            (text_width // 4, text_height // 4),
            text,
            font=font,
            fill=fill,
            anchor="lt"
        )
        
        new_width = int(temp_size[0] * squeeze_factor)
        condensed = temp_layer.resize((new_width, temp_size[1]), Image.Resampling.LANCZOS)
        
        x, y = position
        if anchor == "lb":
            paste_x = int(x)
            paste_y = int(y - temp_size[1] + text_height // 4)
        else:
            paste_x = int(x)
            paste_y = int(y)
        
        return condensed, (paste_x, paste_y)
    
    def render_card(
        self,
        template_path: str,
        output_path: str,
        market_cap: Optional[int],
        weight: int
    ) -> bool:
        """
        Render a card by overlaying text on template image.
        
        Args:
            template_path: путь к локальному файлу темплейта (временный файл)
            output_path: путь для сохранения результата (временный файл)
            market_cap: капитализация
            weight: вес карты
        """
        try:
            if not os.path.exists(template_path):
                logger.error(f"Template not found: {template_path}")
                return False
            
            img = Image.open(template_path).convert("RGBA")
            text_layer = Image.new('RGBA', img.size, (255, 255, 255, 0))
            draw = ImageDraw.Draw(text_layer)
            
            font_small, font_large = self._load_fonts()
            
            market_cap_text = self._format_market_cap(market_cap)
            weight_text = self._get_weight_text(weight)
            weight_number = str(weight)
            
            # === MARKET CAP LABEL ===
            draw.text(
                (59, self.CARD_HEIGHT - 101 - 22),
                "MARKET CAP",
                font=font_small,
                fill=(0, 0, 0, 255),
                anchor="lt"
            )
            
            # === MARKET CAP VALUE ===
            draw.text(
                (59, self.CARD_HEIGHT - 68 - 22),
                market_cap_text,
                font=font_small,
                fill=(0, 0, 0, 255),
                anchor="lt"
            )
            
            # === WEIGHT LABEL ===
            draw.text(
                (268, self.CARD_HEIGHT - 101 - 22),
                "WEIGHT",
                font=font_small,
                fill=(0, 0, 0, 255),
                anchor="lt"
            )
            
            # === WEIGHT TEXT (HIGH/MEDIUM/LOW) ===
            draw.text(
                (268, self.CARD_HEIGHT - 68 - 22),
                weight_text,
                font=font_small,
                fill=(0, 0, 0, 255),
                anchor="lt"
            )
            
            # === WEIGHT NUMBER (большое, condensed) ===
            number_layer, number_pos = self._draw_condensed_number(
                draw,
                weight_number,
                (578, self.CARD_HEIGHT - 52),
                font_large,
                (0, 0, 0, 255),
                anchor="lb",
                squeeze_factor=0.70
            )
            
            # Применяем прозрачность
            alpha = text_layer.split()[3]
            alpha = alpha.point(lambda p: int(p * self.TEXT_OPACITY))
            text_layer.putalpha(alpha)
            
            img = Image.alpha_composite(img, text_layer)
            
            number_alpha = number_layer.split()[3]
            number_alpha = number_alpha.point(lambda p: int(p * self.TEXT_OPACITY))
            number_layer.putalpha(number_alpha)
            
            img.paste(number_layer, number_pos, number_layer)
            
            # Конвертируем RGBA → RGB
            if img.mode == "RGBA":
                rgb_img = Image.new("RGB", img.size, (255, 255, 255))
                rgb_img.paste(img, mask=img.split()[3])
                img = rgb_img
            
            # ⬇️ УМЕНЬШАЕМ РАЗРЕШЕНИЕ В 2 РАЗА
            img = img.resize(
                (self.OUTPUT_WIDTH, self.OUTPUT_HEIGHT),
                Image.Resampling.LANCZOS  # Лучший алгоритм для downscale
            )
            
            # ⬇️ СОХРАНЯЕМ В WebP
            output_path = output_path.replace('.png', '.webp')
            img.save(
                output_path,
                "WebP",
                quality=85,      # Можешь попробовать 80 для ещё меньшего размера
                method=6,        # Максимальное сжатие
                optimize=True
            )
            
            logger.info(f"📊 Image saved: {img.size}, mode: {img.mode}")
            
            # Log file size
            file_size_kb = os.path.getsize(output_path) / 1024
            logger.info(f"✅ Card rendered: {os.path.basename(output_path)} ({file_size_kb:.1f} KB)")
            
            return True
        
        except Exception as e:
            logger.error(f"❌ Failed to render card: {e}", exc_info=True)
            return False
    
    async def render_card_by_id(self, card_id: int) -> Optional[str]:
        """
        Рендерит карту и загружает результат в R2.
        
        Returns:
            CDN URL отрендеренной картинки или None при ошибке
        """
        template_temp_path = None
        output_temp_path = None
        
        try:
            async with DatabaseSession() as db:
                result = await db.execute(
                    select(Card, Token)
                    .join(Token, Card.token_id == Token.id)
                    .where(Card.id == card_id)
                )
                row = result.first()
                
                if not row:
                    logger.error(f"Card {card_id} not found")
                    return None
                
                card, token = row
                
                price_result = await db.execute(
                    select(TokenPrice)
                    .where(TokenPrice.token_id == token.id)
                    .order_by(TokenPrice.timestamp.desc())
                    .limit(1)
                )
                price = price_result.scalar_one_or_none()
                
                template_url = card.template_image_url
                
                # ⬇️ ДОБАВЛЕНО: Быстрый skip для placeholder и невалидных URL
                if not template_url or not template_url.startswith('http'):
                    logger.warning(f"⚠️ Skipping card {card_id}: invalid URL '{template_url}'")
                    return None
                
                if 'placeholder' in template_url.lower():
                    logger.warning(f"⚠️ Skipping card {card_id}: placeholder template")
                    return None
                
                # ⬇️ ИЗМЕНЕНО: Добавлен timeout 5 секунд
                logger.info(f"📥 Downloading template from: {template_url}")
                
                try:
                    response = requests.get(template_url, timeout=5)  # ⬅️ timeout!
                    response.raise_for_status()
                except requests.exceptions.Timeout:
                    logger.error(f"❌ Card {card_id}: template download timeout ({template_url})")
                    return None
                except requests.exceptions.RequestException as e:
                    logger.error(f"❌ Card {card_id}: failed to download template - {e}")
                    return None
                
                # Сохраняем темплейт во временный файл
                with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as f:
                    f.write(response.content)
                    template_temp_path = f.name
                
                # Создаём временный файл для результата
                output_temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.webp')
                output_temp_path = output_temp_file.name
                output_temp_file.close()
                
                # Рендерим карту
                success = self.render_card(
                    template_path=template_temp_path,
                    output_path=output_temp_path,
                    market_cap=price.market_cap if price else None,
                    weight=token.weight
                )
                
                if not success:
                    return None

                # ⬇️ ИЗМЕНЕНО: Загружаем результат в R2
                timestamp = int(datetime.utcnow().timestamp())
                output_filename = f"card_{card.id}_{timestamp}.webp"
                object_key = f"card_renders/{output_filename}"

                # Логируем размер перед загрузкой
                file_size_kb = os.path.getsize(output_temp_path) / 1024
                logger.info(f"📦 Uploading to R2: {output_filename} ({file_size_kb:.1f} KB)")

                rendered_url = r2_storage.upload_file(
                    output_temp_path,
                    object_key,
                    content_type="image/webp"
                )
                
                old_rendered_url = card.rendered_image_url
                
                # Обновляем БД
                card.rendered_image_url = rendered_url
                card.last_rendered_at = datetime.utcnow()
                await db.commit()
                
                logger.info(f"✅ Card {card_id} rendered and uploaded to R2: {rendered_url}")
                
                # ⬇️ ИЗМЕНЕНО: Удаляем старый рендер из R2 (если он был)
                if old_rendered_url and old_rendered_url != rendered_url:
                    # Проверяем что старый URL из нашего R2
                    if r2_storage.public_url in old_rendered_url:
                        # Проверяем что этот URL больше не используется другими картами
                        in_use = await db.execute(
                            select(Card.id).where(
                                Card.rendered_image_url == old_rendered_url,
                                Card.id != card.id
                            )
                        )
                        
                        if not in_use.first():
                            # Извлекаем object_key из URL
                            old_object_key = old_rendered_url.replace(f"{r2_storage.public_url}/", "")
                            
                            try:
                                r2_storage.delete_file(old_object_key)
                                logger.info(f"🗑️ Удалён старый рендер из R2: {old_object_key}")
                            except Exception as e:
                                logger.warning(f"⚠️ Не удалось удалить старый рендер {old_object_key}: {e}")
                
                return rendered_url
        
        except Exception as e:
            logger.error(f"❌ Failed to render card {card_id}: {e}", exc_info=True)
            return None
        
        finally:
            # Удаляем временные файлы
            if template_temp_path and os.path.exists(template_temp_path):
                try:
                    os.remove(template_temp_path)
                except Exception as e:
                    logger.warning(f"⚠️ Failed to delete temp template: {e}")
            
            if output_temp_path and os.path.exists(output_temp_path):
                try:
                    os.remove(output_temp_path)
                except Exception as e:
                    logger.warning(f"⚠️ Failed to delete temp output: {e}")
    
    async def render_all_active_cards(self) -> dict:
        """Render all active cards"""
        try:
            async with DatabaseSession() as db:
                result = await db.execute(
                    select(Card.id).where(Card.is_active == True)
                )
                card_ids = [row[0] for row in result.all()]
            
            logger.info(f"🎨 Starting render for {len(card_ids)} active cards...")
            
            success_count = 0
            failed_count = 0
            
            for card_id in card_ids:
                result = await self.render_card_by_id(card_id)
                if result:
                    success_count += 1
                else:
                    failed_count += 1
            
            logger.info("🔄 Refreshing materialized view active_cards_with_score...")
            try:
                async with DatabaseSession() as db:
                    await db.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY active_cards_with_score"))
                    await db.commit()
                logger.info("✅ Materialized view refreshed successfully")
            except Exception as view_error:
                logger.error(f"❌ Failed to refresh materialized view: {view_error}", exc_info=True)
            
            logger.info(f"✅ Complete: {success_count} success, {failed_count} failed")
            
            return {
                "total": len(card_ids),
                "success": success_count,
                "failed": failed_count
            }
        
        except Exception as e:
            logger.error(f"❌ Failed to render cards: {e}", exc_info=True)
            return {"total": 0, "success": 0, "failed": 0}


# Singleton instance
card_render_service = CardRenderService()