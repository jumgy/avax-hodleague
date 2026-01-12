import os
import logging
from datetime import datetime
from typing import Optional
from PIL import Image, ImageDraw, ImageFont
from decimal import Decimal
from models.database import DatabaseSession
from sqlalchemy import select, and_
from models.card_models import Card
from models.token_models import Token, TokenPrice
from config import Config

logger = logging.getLogger(__name__)

class CardRenderService:
    """Service for rendering card images with dynamic text overlay"""
    
    # Paths
    TEMPLATES_DIR = "/app/static/card_templates"
    RENDERS_DIR = "/app/static/card_renders"
    FONTS_DIR = "/app/static/fonts"
    
    # Card dimensions (4x scale from Figma)
    CARD_WIDTH = 666
    CARD_HEIGHT = 1044
    
    # Font paths
    FONT_INSTRUMENT_SANS_SEMIBOLD = os.path.join(FONTS_DIR, "InstrumentSans-SemiBold.ttf")
    FONT_LEAGUE_GOTHIC = os.path.join(FONTS_DIR, "LeagueGothic-Regular.ttf")
    FONT_LEAGUE_GOTHIC_CONDENSED = os.path.join(FONTS_DIR, "LeagueGothic-Condensed.ttf")
    
    # Text opacity
    TEXT_OPACITY = 0.8  # 80%

    def __init__(self):
        os.makedirs(self.RENDERS_DIR, exist_ok=True)

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
            return f"${int(round(value))}B"  # Округляем до целого
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
            # Все мелкие тексты: Instrument Sans Semibold, 19.6px (~20px)
            font_small = ImageFont.truetype(self.FONT_INSTRUMENT_SANS_SEMIBOLD, size=20)
            
            # Большое число: пробуем сначала Condensed версию, если нет - обычную
            if os.path.exists(self.FONT_LEAGUE_GOTHIC_CONDENSED):
                font_large = ImageFont.truetype(self.FONT_LEAGUE_GOTHIC_CONDENSED, size=105)
            else:
                # Если Condensed нет, берём обычную, но будем сжимать
                font_large = ImageFont.truetype(self.FONT_LEAGUE_GOTHIC, size=105)
            
            return font_small, font_large
            
        except Exception as e:
            logger.error(f"Failed to load fonts: {e}")
            default = ImageFont.load_default()
            return default, default

    def _draw_condensed_number(self, draw, text, position, font, fill, anchor="lb", squeeze_factor=0.75):
        """
        Рисует число с эффектом сжатия по горизонтали (condensed).
        
        Args:
            draw: ImageDraw object
            text: текст для отрисовки
            position: (x, y) координаты
            font: шрифт
            fill: цвет
            anchor: тип якоря
            squeeze_factor: коэффициент сжатия (0.75 = 75% ширины, более узкий)
        """
        # Создаём временный слой для числа
        bbox = draw.textbbox((0, 0), text, font=font, anchor="lt")
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        # Добавляем padding
        temp_size = (int(text_width * 1.5), int(text_height * 1.5))
        temp_layer = Image.new('RGBA', temp_size, (255, 255, 255, 0))
        temp_draw = ImageDraw.Draw(temp_layer)
        
        # Рисуем текст на временном слое
        temp_draw.text(
            (text_width // 4, text_height // 4),
            text,
            font=font,
            fill=fill,
            anchor="lt"
        )
        
        # Сжимаем по горизонтали
        new_width = int(temp_size[0] * squeeze_factor)
        condensed = temp_layer.resize((new_width, temp_size[1]), Image.Resampling.LANCZOS)
        
        # Вычисляем позицию для вставки
        x, y = position
        if anchor == "lb":  # left-baseline
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
        
        Coordinates based on Figma 4x export (666 × 1044):
        - "MARKET CAP": left 59px, bottom 101px
        - Market cap value: left 59px, bottom 68px (rounded to integer)
        - "WEIGHT": left 268px, bottom 101px
        - Weight text (HIGH/MEDIUM/LOW): left 268px, bottom 68px
        - Weight number (large): left 578px, bottom 52px (condensed)
        All text: 80% opacity
        """
        try:
            if not os.path.exists(template_path):
                logger.error(f"Template not found: {template_path}")
                return False
            
            img = Image.open(template_path).convert("RGBA")
            
            # Создаём отдельный прозрачный слой для текста
            text_layer = Image.new('RGBA', img.size, (255, 255, 255, 0))
            draw = ImageDraw.Draw(text_layer)
            
            # Load fonts
            font_small, font_large = self._load_fonts()
            
            # Prepare text
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
            # Создаём сжатое число на отдельном слое
            number_layer, number_pos = self._draw_condensed_number(
                draw,
                weight_number,
                (578, self.CARD_HEIGHT - 52),
                font_large,
                (0, 0, 0, 255),
                anchor="lb",
                squeeze_factor=0.70  # Сжимаем до 70% ширины
            )
            
            # Применяем 80% прозрачность ко всему текстовому слою
            alpha = text_layer.split()[3]
            alpha = alpha.point(lambda p: int(p * self.TEXT_OPACITY))
            text_layer.putalpha(alpha)
            
            # Накладываем текст на основное изображение
            img = Image.alpha_composite(img, text_layer)
            
            # Накладываем сжатое число (оно уже отдельно)
            number_alpha = number_layer.split()[3]
            number_alpha = number_alpha.point(lambda p: int(p * self.TEXT_OPACITY))
            number_layer.putalpha(number_alpha)
            
            img.paste(number_layer, number_pos, number_layer)
            
            # Save rendered image
            img.convert("RGB").save(output_path, "PNG", quality=95)
            logger.info(f"✅ Card rendered: {os.path.basename(output_path)}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to render card: {e}", exc_info=True)
            return False

    async def render_card_by_id(self, card_id: int) -> Optional[str]:
        """Render a card by its database ID"""
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
                
                template_filename = card.template_image_url.split('/')[-1]
                template_path = os.path.join(self.TEMPLATES_DIR, template_filename)
                
                output_filename = f"card_{card.id}.png"
                output_path = os.path.join(self.RENDERS_DIR, output_filename)
                
                success = self.render_card(
                    template_path=template_path,
                    output_path=output_path,
                    market_cap=price.market_cap if price else None,
                    weight=token.weight
                )
                
                if not success:
                    return None
                
                base_url = os.getenv("STATIC_BASE_URL", "http://localhost:8080")
                rendered_url = f"{base_url}/static/card_renders/{output_filename}"
                
                card.rendered_image_url = rendered_url
                card.last_rendered_at = datetime.utcnow()
                await db.commit()
                
                logger.info(f"✅ Card {card_id} rendered: {rendered_url}")
                return rendered_url
                
        except Exception as e:
            logger.error(f"❌ Failed to render card {card_id}: {e}", exc_info=True)
            return None

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