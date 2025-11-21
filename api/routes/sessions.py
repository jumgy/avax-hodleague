# api/routes/sessions.py
from fastapi import APIRouter, HTTPException, status
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime, timedelta
import uuid
import logging
import json
import os

from services.coinmarketcap_service import CoinMarketCapService
from data.game_tokens import get_token_weight, validate_deck_weight, get_weight_distribution
from models.simulation import CryptoSimulator, FantasyCryptoRankSystem, run_fantasy_simulation

logger = logging.getLogger(__name__)

# Create router
router = APIRouter()

# Initialize services
cmc_service = CoinMarketCapService()

SESSIONS_FILE = 'sessions.json'

def load_sessions():
    if os.path.isfile(SESSIONS_FILE):
        with open(SESSIONS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_sessions(sessions):
    with open(SESSIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(sessions, f, ensure_ascii=False, indent=2)

game_sessions = load_sessions()

# Pydantic models
class LockDeckRequest(BaseModel):
    wallet_address: str
    selected_tokens: List[str]
    session_id: Optional[str] = None

class SimulateSessionRequest(BaseModel):
    wallet_address: str
    selected_tokens: List[str]
    session_id: Optional[str] = None

class SessionResponse(BaseModel):
    success: bool
    data: Dict[str, Any]
    message: Optional[str] = None

class SessionsListResponse(BaseModel):
    success: bool
    data: Dict[str, Any]
    message: Optional[str] = None


@router.post("/lock-deck",
            response_model=SessionResponse,
            summary="Lock deck",
            description="Lock a deck of 5 selected tokens for simulation")
async def lock_deck(request: LockDeckRequest):
    """Lock a deck of 5 selected tokens for simulation"""
    try:
        wallet_address = request.wallet_address
        selected_tokens = request.selected_tokens
        session_id = request.session_id

        if not wallet_address:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="wallet_address is required"
            )

        if not isinstance(selected_tokens, list) or len(selected_tokens) != 5:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="selected_tokens must be an array of exactly 5 token symbols"
            )

        # Normalize token symbols
        selected_tokens = [symbol.upper() for symbol in selected_tokens]

        # Check for duplicates
        if len(set(selected_tokens)) != len(selected_tokens):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="All 5 tokens must be unique"
            )

        # Get current available tokens
        available_tokens = cmc_service.get_available_game_tokens()
        available_symbols = {token['symbol'] for token in available_tokens}

        # Check if all selected tokens are available
        invalid_tokens = [symbol for symbol in selected_tokens if symbol not in available_symbols]
        if invalid_tokens:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"The following tokens are not available: {', '.join(invalid_tokens)}"
            )

        # Check tournament weight limit
        total_weight, is_valid_weight = validate_deck_weight(selected_tokens)
        if not is_valid_weight:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Total deck weight ({total_weight}) exceeds tournament limit (28)"
            )

        # Get selected token details with starting prices and market caps
        selected_token_details = []
        for symbol in selected_tokens:
            token = next(t for t in available_tokens if t['symbol'] == symbol)
            selected_token_details.append({
                'symbol': token['symbol'],
                'name': token['name'],
                'starting_price': token['current_price'],
                'starting_market_cap': token['market_cap'],
                'starting_market_cap_formatted': token['market_cap_formatted'],
                'cmc_rank': token['cmc_rank'],
                'logo_url': token['logo_url'],
                'tournament_weight': token['tournament_weight']
            })

        # Create unique session ID
        if not session_id:
            session_id = str(uuid.uuid4())

        # Create game session
        now = datetime.utcnow()
        expires_at = now + timedelta(days=7)

        game_session_data = {
            "session_id": session_id,
            "wallet_address": wallet_address,
            "selected_tokens": selected_token_details,
            "total_tokens": len(selected_token_details),
            "total_weight": total_weight,
            "weight_limit": 28,
            "weight_remaining": 28 - total_weight,
            "locked_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "status": "locked"
        }

        # Save session (using session_id as key to allow multiple decks per wallet)
        game_sessions[session_id] = game_session_data
        save_sessions(game_sessions)

        return SessionResponse(
            success=True,
            data=game_session_data,
            message="Deck successfully locked! Simulation can begin."
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in lock_deck: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/session/{session_id}",
           response_model=SessionResponse,
           summary="Get session",
           description="Get information about a specific game session")
async def get_session(session_id: str):
    """Get information about a specific game session"""
    try:
        session = game_sessions.get(session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No session found with ID: {session_id}"
            )

        return SessionResponse(
            success=True,
            data=session,
            message="Successfully retrieved session data"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/sessions",
           response_model=SessionsListResponse,
           summary="Get all sessions",
           description="Get all game sessions (for testing/admin purposes)")
async def get_all_sessions():
    """Get all game sessions (for testing/admin purposes)"""
    try:
        return SessionsListResponse(
            success=True,
            data={
                "sessions": list(game_sessions.values()),
                "total_count": len(game_sessions)
            },
            message=f"Successfully retrieved {len(game_sessions)} sessions"
        )

    except Exception as e:
        logger.error(f"Error in get_all_sessions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/simulate-session",
            response_model=SessionResponse,
            summary="Simulate session",
            description="Lock deck and run simulation in one step")
async def simulate_session(request: SimulateSessionRequest):
    """Lock deck and run simulation in one step"""
    try:
        logger.info(f"=== SIMULATE SESSION START ===")
        logger.info(f"Raw request data: {request.dict()}")

        wallet_address = request.wallet_address
        selected_tokens = request.selected_tokens
        session_id = request.session_id

        logger.info(f"Parsed data - wallet: {wallet_address}, tokens: {selected_tokens}, session_id: {session_id}")

        if not wallet_address:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="wallet_address is required"
            )

        if not isinstance(selected_tokens, list) or len(selected_tokens) != 5:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="selected_tokens must be an array of exactly 5 token symbols"
            )

        # Normalize token symbols
        original_tokens = selected_tokens.copy()
        selected_tokens = [symbol.upper() for symbol in selected_tokens]
        logger.info(f"Token normalization - original: {original_tokens}, normalized: {selected_tokens}")

        # Check for duplicates
        if len(set(selected_tokens)) != len(selected_tokens):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="All 5 tokens must be unique"
            )

        # Create unique session ID if not provided
        if not session_id:
            session_id = str(uuid.uuid4())
            logger.info(f"Generated new session_id: {session_id}")

        # Check if session already exists and is completed
        if session_id in game_sessions:
            existing_session = game_sessions[session_id]
            logger.info(f"Found existing session {session_id}")
            logger.info(f"Existing session data: {existing_session}")

            if existing_session.get('simulation_completed'):
                logger.info(f"Session {session_id} already completed, returning error")
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This session has already been simulated"
                )
            else:
                logger.info(f"Session {session_id} exists but not completed, proceeding")

        # Get current available tokens
        logger.info(f"Getting available tokens...")
        available_tokens = cmc_service.get_available_game_tokens()
        available_symbols = {token['symbol'] for token in available_tokens}
        logger.info(f"Available tokens count: {len(available_tokens)}")
        logger.info(f"Available symbols (first 20): {list(available_symbols)[:20]}")

        # Check if all selected tokens are available
        invalid_tokens = [symbol for symbol in selected_tokens if symbol not in available_symbols]
        if invalid_tokens:
            logger.error(f"Invalid tokens found: {invalid_tokens}")
            logger.error(f"Selected tokens: {selected_tokens}")
            logger.error(f"All available symbols: {sorted(list(available_symbols))}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"The following tokens are not available: {', '.join(invalid_tokens)}"
            )

        logger.info(f"All selected tokens are valid: {selected_tokens}")

        # Check tournament weight limit
        total_weight, is_valid_weight = validate_deck_weight(selected_tokens)
        logger.info(f"Weight validation - total: {total_weight}, is_valid: {is_valid_weight}")

        if not is_valid_weight:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Total deck weight ({total_weight}) exceeds tournament limit (28)"
            )

        # Get selected token details
        logger.info(f"Getting token details for: {selected_tokens}")
        selected_token_details = []
        for i, symbol in enumerate(selected_tokens):
            logger.info(f"Processing token {i+1}/5: {symbol}")
            try:
                token = next(t for t in available_tokens if t['symbol'] == symbol)
                logger.info(f"Found token {symbol}: {token['name']}")
                selected_token_details.append({
                    'symbol': token['symbol'],
                    'name': token['name'],
                    'starting_price': token['current_price'],
                    'starting_market_cap': token['market_cap'],
                    'starting_market_cap_formatted': token['market_cap_formatted'],
                    'cmc_rank': token['cmc_rank'],
                    'logo_url': token['logo_url'],
                    'tournament_weight': token['tournament_weight']
                })
            except StopIteration:
                logger.error(f"CRITICAL ERROR: Token {symbol} not found in available_tokens!")
                logger.error(f"Available token symbols: {[t['symbol'] for t in available_tokens]}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Token {symbol} is not available"
                )

        logger.info(f"Successfully got details for {len(selected_token_details)} tokens")

        # Create/update session data
        now = datetime.utcnow()
        expires_at = now + timedelta(days=7)

        game_session_data = {
            "session_id": session_id,
            "wallet_address": wallet_address,
            "selected_tokens": selected_token_details,
            "total_tokens": len(selected_token_details),
            "total_weight": total_weight,
            "weight_limit": 28,
            "weight_remaining": 28 - total_weight,
            "locked_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "status": "locked"
        }

        logger.info(f"Created session data for: {[t['symbol'] for t in selected_token_details]}")

        # Get all simulation tokens
        logger.info(f"Getting simulation tokens...")
        simulation_tokens = cmc_service.get_simulation_tokens()
        if len(simulation_tokens) < 100:
            logger.warning(f"Only {len(simulation_tokens)} simulation tokens available, expected 100")

        logger.info(f"Got {len(simulation_tokens)} simulation tokens")
        logger.info(f"Starting simulation with selected tokens: {[t['symbol'] for t in selected_token_details]}")

        # Run simulation
        results = run_fantasy_simulation(selected_token_details, simulation_tokens)
        logger.info(f"Simulation completed - final score: {results['final_score']}")

        # Prepare simulation results
        simulation_results = {
            'session_id': session_id,
            'wallet_address': wallet_address,
            'simulation_date': now.isoformat(),
            'daily_scores': [
                {
                    'day': d.day,
                    'score': d.score,
                    'market_position': d.market_position,
                    'market_sentiment': {
                        'status': d.market_sentiment['status'],
                        'description': d.market_sentiment['description'],
                        'market_change_pct': d.market_sentiment['market_change_pct'],
                        'actual_market_change_pct': d.market_sentiment.get('actual_market_change_pct', 0),
                        'trend': d.market_sentiment['trend']
                    },
                    'tokens_performance': d.tokens_performance
                } for d in results["daily_scores"]
            ],
            'final_score': results['final_score'],
            'final_market_position': results['final_position'],
            'market_overview': results['market_analysis']['daily_sentiments'],
            'all_tokens_final': results.get('all_tokens_final', {})
        }

        # Update session with simulation results
        game_session_data['simulation_results'] = simulation_results
        game_session_data['simulation_completed'] = True
        game_session_data['final_score'] = results['final_score']
        game_session_data['status'] = 'completed'

        # Save session
        game_sessions[session_id] = game_session_data
        save_sessions(game_sessions)

        logger.info(f"=== SIMULATE SESSION SUCCESS === Session: {session_id}, Score: {results['final_score']}")

        return SessionResponse(
            success=True,
            data={
                "session": game_session_data,
                "simulation": simulation_results
            },
            message=f"Deck locked and simulation completed! Final score: {results['final_score']}"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"=== SIMULATE SESSION ERROR === Exception: {e}")
        logger.error(f"Exception type: {type(e).__name__}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/session/{session_id}/results",
           response_model=SessionResponse,
           summary="Get session results",
           description="Get detailed simulation results for a session")
async def get_session_results(session_id: str):
    """Get detailed simulation results for a session"""
    try:
        if session_id not in game_sessions:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No session found with ID: {session_id}"
            )

        session = game_sessions[session_id]

        if not session.get('simulation_completed'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Simulation not completed - Run simulation first using POST /api/simulate-session"
            )

        return SessionResponse(
            success=True,
            data=session.get('simulation_results', {}),
            message="Successfully retrieved simulation results"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_session_results: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )