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
    
    # Card dimensions
    CARD_WIDTH = 666
    CARD_HEIGHT = 1044
    
    # Font paths
    FONT_INSTRUMENT_SANS = os.path.join(FONTS_DIR, "InstrumentSans-SemiBold.ttf")
    FONT_LEAGUE_GOTHIC = os.path.join(FONTS_DIR, "LeagueGothic-Regular.ttf")
    
    # Text color (black 80%)
    TEXT_COLOR = (0, 0, 0, 204)  # RGBA
    
    def __init__(self):
        # Ensure directories exist
        os.makedirs(self.RENDERS_DIR, exist_ok=True)
        
    def _get_weight_text(self, weight: int) -> str:
        """Convert weight number to text: Low/Medium/High"""
        if weight in [8, 9, 10]:
            return "High"
        elif weight in [4, 5, 6, 7]:
            return "Medium"
        elif weight in [1, 2, 3]:
            return "Low"
        else:
            return "Medium"  # Default
    
    def _format_market_cap(self, market_cap: Optional[int]) -> str:
        """
        Format market cap to readable string: $353.0B
        Always rounds to 1 decimal place.
        """
        if not market_cap or market_cap == 0:
            return "$0.0"
        
        # Billions
        if market_cap >= 1_000_000_000:
            value = market_cap / 1_000_000_000
            return f"${value:.1f}B"
        
        # Millions
        elif market_cap >= 1_000_000:
            value = market_cap / 1_000_000
            return f"${value:.1f}M"
        
        # Thousands
        elif market_cap >= 1_000:
            value = market_cap / 1_000
            return f"${value:.1f}K"
        
        else:
            return f"${market_cap:.1f}"
    
    def _load_fonts(self):
        """Load fonts for rendering"""
        try:
            # Small font for labels (4.9pt ≈ 6.5px at 96 DPI)
            font_small = ImageFont.truetype(self.FONT_INSTRUMENT_SANS, size=int(4.9 * 1.33))
            
            # Large font for weight number (26.13pt ≈ 35px at 96 DPI)
            font_large = ImageFont.truetype(self.FONT_LEAGUE_GOTHIC, size=int(26.13 * 1.33))
            
            return font_small, font_large
        
        except Exception as e:
            logger.error(f"Failed to load fonts: {e}")
            # Fallback to default font
            return ImageFont.load_default(), ImageFont.load_default()
    
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
            template_path: Path to template image
            output_path: Path to save rendered image
            market_cap: Market cap value (in dollars)
            weight: Token weight (1-10)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Load template image
            if not os.path.exists(template_path):
                logger.error(f"Template not found: {template_path}")
                return False
            
            img = Image.open(template_path).convert("RGBA")
            
            # Create drawing context
            draw = ImageDraw.Draw(img)
            
            # Load fonts
            font_small, font_large = self._load_fonts()
            
            # Prepare text
            market_cap_text = self._format_market_cap(market_cap)
            weight_text = self._get_weight_text(weight)
            weight_number = str(weight)
            
            # Calculate positions (from bottom)
            # "MARKET CAP" label
            draw.text(
                (14.7, self.CARD_HEIGHT - 22.74),
                "MARKET CAP",
                font=font_small,
                fill=self.TEXT_COLOR,
                anchor="ls"  # left-baseline
            )
            
            # Market cap value
            draw.text(
                (14.7, self.CARD_HEIGHT - 14.57),
                market_cap_text,
                font=font_small,
                fill=self.TEXT_COLOR,
                anchor="ls"
            )
            
            # "WEIGHT" label
            draw.text(
                (66.96, self.CARD_HEIGHT - 22.74),
                "WEIGHT",
                font=font_small,
                fill=self.TEXT_COLOR,
                anchor="ls"
            )
            
            # Weight text (Low/Medium/High)
            draw.text(
                (66.55, self.CARD_HEIGHT - 15.39),
                weight_text,
                font=font_small,
                fill=self.TEXT_COLOR,
                anchor="ls"
            )
            
            # Weight number (big)
            draw.text(
                (144.61, self.CARD_HEIGHT - 17.65),
                weight_number,
                font=font_large,
                fill=self.TEXT_COLOR,
                anchor="lt"  # left-top
            )
            
            # Save rendered image
            img.convert("RGB").save(output_path, "PNG", quality=95)
            
            logger.info(f"✅ Card rendered: {os.path.basename(output_path)}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to render card: {e}", exc_info=True)
            return False
    
    async def render_card_by_id(self, card_id: int) -> Optional[str]:
        """
        Render a card by its database ID.
        
        Args:
            card_id: Card database ID
        
        Returns:
            URL of rendered image if successful, None otherwise
        """
        try:
            async with DatabaseSession() as db:
                # Fetch card with token
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
                
                # Fetch latest price separately
                price_result = await db.execute(
                    select(TokenPrice)
                    .where(TokenPrice.token_id == token.id)
                    .order_by(TokenPrice.timestamp.desc())
                    .limit(1)
                )
                price = price_result.scalar_one_or_none()
                
                # Extract template filename from URL
                template_filename = card.template_image_url.split('/')[-1]
                template_path = os.path.join(self.TEMPLATES_DIR, template_filename)
                
                # Generate output filename
                output_filename = f"card_{card.id}.png"
                output_path = os.path.join(self.RENDERS_DIR, output_filename)
                
                # Render card
                success = self.render_card(
                    template_path=template_path,
                    output_path=output_path,
                    market_cap=price.market_cap if price else None,
                    weight=token.weight
                )
                
                if not success:
                    return None
                
                # Generate URL
                base_url = os.getenv("STATIC_BASE_URL", "http://localhost:8080")
                rendered_url = f"{base_url}/static/card_renders/{output_filename}"
                
                # Update card in database
                card.background_image_url = rendered_url
                card.last_rendered_at = datetime.utcnow()
                await db.commit()
                
                logger.info(f"✅ Card {card_id} rendered and updated in DB")
                return rendered_url
                
        except Exception as e:
            logger.error(f"❌ Failed to render card {card_id}: {e}", exc_info=True)
            return None
    
    async def render_all_active_cards(self) -> dict:
        """
        Render all active cards.
        
        Returns:
            Dict with success/failure counts
        """
        try:
            async with DatabaseSession() as db:
                # Get all active cards
                result = await db.execute(
                    select(Card.id)
                    .where(Card.is_active == True)
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
            
            logger.info(f"✅ Rendering complete: {success_count} success, {failed_count} failed")
            
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