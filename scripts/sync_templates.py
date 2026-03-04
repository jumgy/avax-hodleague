# scripts/sync_templates.py
"""
Sync card templates from R2 to database.

1. List files in R2 (card_templates/)
2. Extract ticker from filename
3. Find token in DB by symbol
4. Update template_image_url for all cards of that token

Usage:
    python scripts/sync_templates.py
    python scripts/sync_templates.py --dry-run  # no DB changes
"""

import asyncio
import sys
import os
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from models.database import DatabaseSession
from models.card_models import Card
from models.token_models import Token
from sqlalchemy import select
from services.r2_storage import r2_storage

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


async def sync_templates(dry_run: bool = False):
    """Sync templates from R2 to database.

    Args:
        dry_run: If True, show planned changes without modifying DB.
    """
    try:
        logger.info("Fetching templates from R2...")

        # List files in R2
        response = r2_storage.client.list_objects_v2(
            Bucket=r2_storage.bucket_name,
            Prefix="card_templates/"
        )
        
        if 'Contents' not in response:
            logger.warning("No templates found in R2")
            return
        
        # Group files by token: { 'BTC': ['btc_classic_rare_123.png', ...], ... }
        templates_by_token = {}
        
        for obj in response['Contents']:
            filename = obj['Key'].replace('card_templates/', '')
            if not filename:  # Skip folder entry
                continue
            
            # Extract ticker from filename: btc_classic_rare_20240203.png -> BTC
            token_symbol = filename.split('_')[0].upper()
            
            file_url = f"{r2_storage.public_url}/{obj['Key']}"
            file_size = obj['Size']
            
            if token_symbol not in templates_by_token:
                templates_by_token[token_symbol] = []
            
            templates_by_token[token_symbol].append({
                'filename': filename,
                'url': file_url,
                'size_kb': round(file_size / 1024, 2)
            })
        
        logger.info(f"Found templates for {len(templates_by_token)} tokens")

        # Database update
        async with DatabaseSession() as db:
            updated_count = 0
            skipped_count = 0
            not_found_tokens = []
            
            for token_symbol, files in templates_by_token.items():
                # Sort by filename (last = latest by timestamp)
                files.sort(key=lambda x: x['filename'], reverse=True)
                latest_file = files[0]
                
                logger.info(f"\nToken: {token_symbol}")
                logger.info(f"   Latest template: {latest_file['filename']} ({latest_file['size_kb']}KB)")

                if len(files) > 1:
                    logger.info(f"   Found {len(files)} templates, using latest")

                # Find token in DB
                result = await db.execute(
                    select(Token).where(Token.symbol == token_symbol)
                )
                token = result.scalar_one_or_none()
                
                if not token:
                    logger.warning(f"   Token {token_symbol} not found in DB")
                    not_found_tokens.append(token_symbol)
                    skipped_count += 1
                    continue
                
                # Find all cards for this token
                result = await db.execute(
                    select(Card).where(Card.token_id == token.id)
                )
                cards = result.scalars().all()
                
                if not cards:
                    logger.warning(f"   No cards found for token {token_symbol}")
                    skipped_count += 1
                    continue
                
                logger.info(f"   Found {len(cards)} card(s)")
                
                # Update template_image_url
                for card in cards:
                    old_url = card.template_image_url
                    new_url = latest_file['url']
                    
                    if old_url == new_url:
                        logger.info(f"   Card {card.id} already has correct URL")
                        continue
                    
                    if dry_run:
                        logger.info(f"   [DRY RUN] Would update card {card.id}:")
                        logger.info(f"      OLD: {old_url}")
                        logger.info(f"      NEW: {new_url}")
                    else:
                        card.template_image_url = new_url
                        logger.info(f"   Updated card {card.id}")
                        logger.info(f"      OLD: {old_url}")
                        logger.info(f"      NEW: {new_url}")
                    
                    updated_count += 1
            
            # Commit changes
            if not dry_run and updated_count > 0:
                await db.commit()
                logger.info("\nChanges committed to database")
            elif dry_run:
                logger.info(f"\n[DRY RUN] No changes made to database")
            
            # Summary
            logger.info(f"\n{'='*60}")
            logger.info("Summary:")
            logger.info(f"   Tokens processed: {len(templates_by_token)}")
            logger.info(f"   Cards updated: {updated_count}")
            logger.info(f"   Skipped: {skipped_count}")
            
            if not_found_tokens:
                logger.info("\nTokens not found in DB:")
                for sym in not_found_tokens:
                    logger.info(f"   - {sym}")
            
            logger.info(f"{'='*60}")
            
            if dry_run:
                logger.info("\nRun without --dry-run to apply changes")

    except Exception as e:
        logger.error(f"Sync failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Sync card templates from R2 to database")
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without making changes'
    )
    args = parser.parse_args()
    
    logger.info("Starting template synchronization...")
    if args.dry_run:
        logger.info("DRY RUN MODE - no changes will be made")

    asyncio.run(sync_templates(dry_run=args.dry_run))

    logger.info("Done.")