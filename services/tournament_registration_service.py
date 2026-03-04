import asyncio
import hashlib
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import Config
from models.card_models import Card
from models.rarity_models import Rarity
from models.token_models import Token
from models.tournament_deck_models import TournamentDeck
from models.tournament_models import Tournament
from models.user_card_models import UserCard
from services.web3_verification_service import Web3VerificationService

logger = logging.getLogger(__name__)


class TournamentRegistrationService:
    """Service for tournament registration with blockchain verification."""

    @staticmethod
    def generate_deck_hash(tournament_id: int, user_id: int, deck_composition: list[int]) -> str:
        """Generate SHA256 hash of the deck."""
        sorted_deck = sorted(deck_composition)
        hash_string = f"{tournament_id}:{user_id}:{':'.join(map(str, sorted_deck))}"
        return hashlib.sha256(hash_string.encode()).hexdigest()

    @staticmethod
    async def _validate_deck_common(
        db: AsyncSession, tournament_id: int, user_id: int, deck_composition: list[int]
    ) -> tuple:
        """Common deck validation (used for preview and final registration).

        Returns:
            Tuple of (tournament, cards_result, total_weight).
        """
        # 1. Exactly 5 cards
        if len(deck_composition) != 5:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Deck must contain exactly 5 cards")

        # 2. No duplicate user_card_id
        if len(set(deck_composition)) != 5:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Deck cannot contain duplicate cards")

        # 3. Tournament exists and status is "registration"
        tournament_query = select(Tournament).where(Tournament.id == tournament_id)
        tournament = (await db.execute(tournament_query)).scalar_one_or_none()

        if not tournament:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tournament not found")

        if tournament.status != "registration":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tournament registration is closed. Current status: {tournament.status}",
            )

        # 4. User not already registered
        existing_deck_query = select(TournamentDeck).where(
            and_(
                TournamentDeck.tournament_id == tournament_id,
                TournamentDeck.user_id == user_id,
                TournamentDeck.is_active == True,
            )
        )
        existing_deck = (await db.execute(existing_deck_query)).scalar_one_or_none()

        if existing_deck:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="You are already registered for this tournament"
            )

        # 5. Get cards with join to Card and Token
        cards_query = (
            select(UserCard, Card, Token, Rarity)
            .join(Card, UserCard.card_id == Card.id)
            .join(Token, Card.token_id == Token.id)
            .join(Rarity, Card.rarity_id == Rarity.id)
            .where(and_(UserCard.id.in_(deck_composition), UserCard.user_id == user_id))
        )
        cards_result = (await db.execute(cards_query)).all()

        # 6. All cards belong to user
        if len(cards_result) != 5:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="One or more cards do not belong to you"
            )

        # 7. No two cards of the same token
        token_ids = [token.id for _, _, token, _ in cards_result]
        if len(set(token_ids)) != 5:
            # Find duplicates for error message
            from collections import Counter

            token_counts = Counter(token_ids)
            duplicate_tokens = [token.name for _, _, token, _ in cards_result if token_counts[token.id] > 1]
            duplicate_tokens_unique = list(set(duplicate_tokens))

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Deck cannot contain multiple cards of the same token. Duplicate token(s): {', '.join(duplicate_tokens_unique)}",
            )

        # 8. Validate status and sum weight
        total_weight = 0.0
        now = datetime.now(UTC)

        for user_card, card, token, rarity in cards_result:
            # Check expires_at
            if user_card.expires_at and user_card.expires_at <= now:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Card #{user_card.id} ({token.name} - {rarity.name}) has expired",
                )

            # Check status
            if user_card.status != "available":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Card #{user_card.id} ({token.name} - {rarity.name}) is not available. Status: {user_card.status}",
                )

            # Check is_active
            if not user_card.is_active:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Card #{user_card.id} ({token.name} - {rarity.name}) is not active",
                )

            # Sum weight
            total_weight += float(token.weight)

        # 9. Check weight limit
        if total_weight > float(tournament.weight_limit):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Deck weight {total_weight:.2f} exceeds tournament limit {float(tournament.weight_limit):.2f}",
            )

        return tournament, cards_result, total_weight

    @staticmethod
    async def validate_deck_preview(
        db: AsyncSession, tournament_id: int, user_id: int, deck_composition: list[int]
    ) -> dict:
        """Pre-validate deck without writing to DB.

        Used by frontend before calling the smart contract.
        Returns deck_hash to pass to the contract.

        Returns:
            Dict with valid, deck_hash, total_weight, weight_limit, cards.
        """

        # Run all checks (no DB write)
        tournament, cards_result, total_weight = await TournamentRegistrationService._validate_deck_common(
            db, tournament_id, user_id, deck_composition
        )

        # Generate deck_hash
        deck_hash = TournamentRegistrationService.generate_deck_hash(tournament_id, user_id, deck_composition)

        # Build response
        cards_info = [
            {"user_card_id": uc.id, "card_name": token.name, "rarity": rarity.name, "weight": float(token.weight)}
            for uc, card, token, rarity in cards_result
        ]

        return {
            "valid": True,
            "deck_hash": f"0x{deck_hash}",  # 0x prefix for contract
            "total_weight": total_weight,
            "weight_limit": float(tournament.weight_limit),
            "cards": cards_info,
            "message": "Deck is valid. You can now register on-chain with this deck_hash.",
        }

    @staticmethod
    def get_network_info_for_chain_id(chain_id: int | None) -> dict[str, Any] | None:
        """Return network info for unregister by chain_id (from tournament_decks.registration_chain_id).

        Avalanche only: returns chain_id and contract_address for the frontend to call unregister.
        """
        if chain_id is None:
            return None
        if chain_id == Config.AVALANCHE_CHAIN_ID and Config.TOURNAMENT_CONTRACT_ADDRESS:
            return {
                "network": "avalanche",
                "chain_id": Config.AVALANCHE_CHAIN_ID,
                "contract_address": Config.TOURNAMENT_CONTRACT_ADDRESS,
            }
        logger.warning("Unknown registration_chain_id=%s, cannot map to network", chain_id)
        return None

    @staticmethod
    def _get_avalanche_web3_config() -> tuple[str, str, int]:
        """Return (provider_url, contract_address, chain_id) for Avalanche C-Chain."""
        if not Config.WEB3_PROVIDER_URL or not Config.TOURNAMENT_CONTRACT_ADDRESS:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Avalanche is not configured (WEB3_PROVIDER_URL or TOURNAMENT_CONTRACT_ADDRESS missing).",
            )
        return (
            Config.WEB3_PROVIDER_URL,
            Config.TOURNAMENT_CONTRACT_ADDRESS,
            Config.AVALANCHE_CHAIN_ID,
        )

    @staticmethod
    async def detect_onchain_registration(
        tournament_id: int,
        wallet_address: str,
        timeout_seconds: float = 1.0,
    ) -> dict[str, Any]:
        """Quick check of registration directly in the smart contract on Avalanche."""
        wallet = (wallet_address or "").strip()
        if not wallet:
            logger.warning("detect_onchain_registration: empty wallet_address, skipping on-chain check")
            return {"is_registered": False}

        try:
            provider_url, contract_address, chain_id = TournamentRegistrationService._get_avalanche_web3_config()
        except HTTPException:
            return {"is_registered": False}

        try:
            web3_service = Web3VerificationService(
                web3_provider_url=provider_url,
                contract_address=contract_address,
                contract_abi=Config.TOURNAMENT_CONTRACT_ABI,
            )

            def _call() -> dict[str, Any]:
                return web3_service.check_registration_onchain(
                    tournament_id=tournament_id,
                    user_wallet=wallet,
                )

            result: dict[str, Any] = await asyncio.wait_for(
                asyncio.to_thread(_call),
                timeout=timeout_seconds,
            )

            if result.get("is_registered"):
                logger.info(
                    "On-chain registration detected for tournament_id=%s, wallet=%s",
                    tournament_id,
                    wallet,
                )
                return {
                    "is_registered": True,
                    "network": "avalanche",
                    "chain_id": chain_id,
                    "contract_address": contract_address,
                    "deck_hash": result.get("deck_hash"),
                }
        except asyncio.TimeoutError:
            logger.warning(
                "detect_onchain_registration: timeout for tournament_id=%s",
                tournament_id,
            )
        except Exception as e:
            logger.error(
                "detect_onchain_registration: error for tournament_id=%s: %s",
                tournament_id,
                e,
            )

        return {"is_registered": False}

    @staticmethod
    async def register_deck_with_verification(
        db: AsyncSession,
        tournament_id: int,
        user_id: int,
        user_wallet: str,
        deck_composition: list[int],
        tx_hash: str,
    ) -> TournamentDeck:
        """Final registration with blockchain transaction verification on Avalanche.

        Called after the user has signed the transaction in the contract.

        Returns:
            TournamentDeck.
        """
        # 1. Basic deck validation
        tournament, cards_result, total_weight = await TournamentRegistrationService._validate_deck_common(
            db, tournament_id, user_id, deck_composition
        )

        # 2. Generate deck_hash
        deck_hash = TournamentRegistrationService.generate_deck_hash(tournament_id, user_id, deck_composition)

        # 3. Verify blockchain transaction on Avalanche
        provider_url, contract_address, chain_id = TournamentRegistrationService._get_avalanche_web3_config()
        logger.info(
            "Verifying transaction %s on Avalanche (provider=%s, contract=%s, chain_id=%s)",
            tx_hash,
            provider_url,
            contract_address,
            chain_id,
        )

        web3_service = Web3VerificationService(
            web3_provider_url=provider_url,
            contract_address=contract_address,
            contract_abi=Config.TOURNAMENT_CONTRACT_ABI,
        )

        verification = await web3_service.verify_register_transaction(
            tx_hash=tx_hash, tournament_id=tournament_id, expected_deck_hash=deck_hash, user_wallet=user_wallet
        )

        if not verification["valid"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Transaction verification failed: {verification['error']}",
            )

        # 4. Create TournamentDeck (store chain_id for audit)
        tournament_deck = TournamentDeck(
            tournament_id=tournament_id,
            user_id=user_id,
            deck_composition=deck_composition,
            deck_hash=deck_hash,
            transaction_hash=tx_hash,
            total_weight=total_weight,
            is_valid=True,
            is_active=True,
            registration_chain_id=chain_id,
        )

        db.add(tournament_deck)

        # 5. Lock cards
        for user_card, card, token, rarity in cards_result:
            user_card.status = "locked"

        await db.commit()
        await db.refresh(tournament_deck)

        return tournament_deck

    @staticmethod
    async def unregister_deck_with_verification(
        db: AsyncSession,
        tournament_id: int,
        user_id: int,
        user_wallet: str,
        tx_hash: str,
    ) -> dict:
        """Unregister with blockchain transaction verification on Avalanche.

        User must call unregisterDeck in the contract, then pass tx_hash here to unlock cards.

        Returns:
            Dict with success, cards_unlocked, tx_hash.
        """
        # 1. Ensure tournament is in registration status
        tournament_query = select(Tournament).where(Tournament.id == tournament_id)
        tournament = (await db.execute(tournament_query)).scalar_one_or_none()

        if not tournament:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tournament not found")

        if tournament.status != "registration":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot unregister after registration closed"
            )

        # 2. Find active deck
        deck_query = select(TournamentDeck).where(
            and_(
                TournamentDeck.tournament_id == tournament_id,
                TournamentDeck.user_id == user_id,
                TournamentDeck.is_active == True,
            )
        )
        deck = (await db.execute(deck_query)).scalar_one_or_none()

        if not deck:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not registered in this tournament")

        # 3. Verify UNREGISTER transaction on Avalanche
        provider_url, contract_address, _ = TournamentRegistrationService._get_avalanche_web3_config()
        web3_service = Web3VerificationService(
            web3_provider_url=provider_url,
            contract_address=contract_address,
            contract_abi=Config.TOURNAMENT_CONTRACT_ABI,
        )

        verification = await web3_service.verify_unregister_transaction(
            tx_hash=tx_hash, tournament_id=tournament_id, user_wallet=user_wallet
        )

        if not verification["valid"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unregister verification failed: {verification['error']}",
            )

        # 4. Unlock cards
        cards_query = select(UserCard).where(UserCard.id.in_(deck.deck_composition))
        cards = (await db.execute(cards_query)).scalars().all()

        unlocked_count = 0
        for card in cards:
            if card.status == "locked":
                card.status = "available"
                unlocked_count += 1

        # 5. Deactivate deck
        deck.is_active = False

        await db.commit()

        return {
            "success": True,
            "cards_unlocked": unlocked_count,
            "tx_hash": tx_hash,
            "message": f"Successfully unregistered from tournament. {unlocked_count} cards unlocked.",
        }
