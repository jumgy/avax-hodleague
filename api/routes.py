from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
import uuid
import logging
from services.coinmarketcap_service import CoinMarketCapService
from data.game_tokens import get_token_weight, validate_deck_weight, get_weight_distribution
from models.simulation import CryptoSimulator, FantasyCryptoRankSystem, run_fantasy_simulation
import json
import os

logger = logging.getLogger(__name__)
api_bp = Blueprint('api', __name__)


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

@api_bp.route('/tokens', methods=['GET'])
def get_tokens():
    """Get all available game tokens from top-100"""
    try:
        # Get game tokens that are available in current top-100
        available_tokens = cmc_service.get_available_game_tokens()
        
        if not available_tokens:
            return jsonify({
                "success": False,
                "error": "No tokens available",
                "message": "Could not fetch token data from CoinMarketCap"
            }), 503
        
        return jsonify({
            "success": True,
            "data": {
                "tokens": available_tokens,
                "total_count": len(available_tokens),
                "last_updated": datetime.utcnow().isoformat()
            },
            "message": f"Successfully retrieved {len(available_tokens)} available tokens"
        })
        
    except Exception as e:
        logger.error(f"Error in get_tokens: {e}")
        return jsonify({
            "success": False,
            "error": "Internal server error",
            "message": str(e)
        }), 500

@api_bp.route('/tokens/<symbol>', methods=['GET'])
def get_token_details(symbol):
    """Get detailed information about a specific token"""
    try:
        symbol = symbol.upper()
        
        # Get all available tokens and find the requested one
        available_tokens = cmc_service.get_available_game_tokens()
        token = next((t for t in available_tokens if t['symbol'] == symbol), None)
        
        if not token:
            return jsonify({
                "success": False,
                "error": "Token not found",
                "message": f"Token {symbol} not found in available game tokens"
            }), 404
        
        return jsonify({
            "success": True,
            "data": token,
            "message": f"Successfully retrieved details for {symbol}"
        })
        
    except Exception as e:
        logger.error(f"Error in get_token_details: {e}")
        return jsonify({
            "success": False,
            "error": "Internal server error",
            "message": str(e)
        }), 500

@api_bp.route('/tournament', methods=['GET'])
def get_tournament_info():
    """Get current tournament information"""
    try:
        weight_stats = get_weight_distribution()
        
        tournament_info = {
            "tournament_id": "simulation_001",
            "name": "Crypto Fantasy Tournament",
            "status": "active",
            "rules": {
                "deck_size": 5,
                "weight_limit": 28,
                "duration_days": 7
            },
            "weight_tiers": {
                "giants_80_100": weight_stats['tier_1'],
                "major_60_79": weight_stats['tier_2'], 
                "mid_40_59": weight_stats['tier_3'],
                "emerging_25_39": weight_stats['tier_4'],
                "speculative_15_24": weight_stats['tier_5']
            },
            "example_strategies": [
                "Conservative: 1 Giant + 4 Mid/Small = BTC(100) + 4x(37avg)",
                "Balanced: 2 Major + 3 Small = SOL(75) + DOGE(70) + 3x(35avg)", 
                "Risky: 5 Speculative = 5x(50avg)"
            ]
        }
        
        return jsonify({
            "success": True,
            "data": tournament_info,
            "message": "Tournament info retrieved"
        })
        
    except Exception as e:
        logger.error(f"Error in get_tournament_info: {e}")
        return jsonify({
            "success": False,
            "error": "Internal server error",
            "message": str(e)
        }), 500

@api_bp.route('/lock-deck', methods=['POST'])
def lock_deck():
    """Lock a deck of 5 selected tokens for simulation"""
    try:
        data = request.get_json()
        
        # Validation
        if not data:
            return jsonify({
                "success": False,
                "error": "No data provided",
                "message": "Request body is required"
            }), 400
        
        wallet_address = data.get('wallet_address')
        selected_tokens = data.get('selected_tokens', [])
        session_id = data.get('session_id')  # Optional additional identifier
        
        if not wallet_address:
            return jsonify({
                "success": False,
                "error": "Missing wallet_address",
                "message": "wallet_address is required"
            }), 400
        
        if not isinstance(selected_tokens, list) or len(selected_tokens) != 5:
            return jsonify({
                "success": False,
                "error": "Invalid selected_tokens",
                "message": "selected_tokens must be an array of exactly 5 token symbols"
            }), 400
        
        # Normalize token symbols
        selected_tokens = [symbol.upper() for symbol in selected_tokens]
        
        # Check for duplicates
        if len(set(selected_tokens)) != len(selected_tokens):
            return jsonify({
                "success": False,
                "error": "Duplicate tokens",
                "message": "All 5 tokens must be unique"
            }), 400
        
        # Get current available tokens
        available_tokens = cmc_service.get_available_game_tokens()
        available_symbols = {token['symbol'] for token in available_tokens}
        
        # Check if all selected tokens are available
        invalid_tokens = [symbol for symbol in selected_tokens if symbol not in available_symbols]
        
        if invalid_tokens:
            return jsonify({
                "success": False,
                "error": "Invalid tokens",
                "message": f"The following tokens are not available: {', '.join(invalid_tokens)}"
            }), 400
        
        # Check tournament weight limit
        total_weight, is_valid_weight = validate_deck_weight(selected_tokens)
        
        if not is_valid_weight:
            return jsonify({
                "success": False,
                "error": "Deck exceeds weight limit",
                "message": f"Total deck weight ({total_weight}) exceeds tournament limit (28)"
            }), 400
        
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
        
        return jsonify({
            "success": True,
            "data": game_session_data,
            "message": "Deck successfully locked! Simulation can begin."
        })
        
    except Exception as e:
        logger.error(f"Error in lock_deck: {e}")
        return jsonify({
            "success": False,
            "error": "Internal server error",
            "message": str(e)
        }), 500

@api_bp.route('/session/<session_id>', methods=['GET'])
def get_session(session_id):
    """Get information about a specific game session"""
    try:
        session = game_sessions.get(session_id)
        
        if not session:
            return jsonify({
                "success": False,
                "error": "Session not found",
                "message": f"No session found with ID: {session_id}"
            }), 404
        
        return jsonify({
            "success": True,
            "data": session,
            "message": "Successfully retrieved session data"
        })
        
    except Exception as e:
        logger.error(f"Error in get_session: {e}")
        return jsonify({
            "success": False,
            "error": "Internal server error",
            "message": str(e)
        }), 500

@api_bp.route('/sessions', methods=['GET'])
def get_all_sessions():
    """Get all game sessions (for testing/admin purposes)"""
    try:
        return jsonify({
            "success": True,
            "data": {
                "sessions": list(game_sessions.values()),
                "total_count": len(game_sessions)
            },
            "message": f"Successfully retrieved {len(game_sessions)} sessions"
        })
        
    except Exception as e:
        logger.error(f"Error in get_all_sessions: {e}")
        return jsonify({
            "success": False,
            "error": "Internal server error",
            "message": str(e)
        }), 500
        
@api_bp.route('/simulation-tokens', methods=['GET'])
def get_simulation_tokens():
    """Get all 100 tokens used for simulation calculations"""
    try:
        # Get simulation tokens (100 total, includes 30 game tokens + 70 others)
        simulation_tokens = cmc_service.get_simulation_tokens()
        
        if not simulation_tokens:
            return jsonify({
                "success": False,
                "error": "No simulation tokens available",
                "message": "Could not fetch simulation token data from CoinMarketCap"
            }), 503
        
        # Separate stats
        game_tokens_count = len([t for t in simulation_tokens if t['is_game_token']])
        other_tokens_count = len(simulation_tokens) - game_tokens_count
        
        return jsonify({
            "success": True,
            "data": {
                "tokens": simulation_tokens,
                "total_count": len(simulation_tokens),
                "game_tokens_count": game_tokens_count,
                "other_tokens_count": other_tokens_count,
                "last_updated": datetime.utcnow().isoformat()
            },
            "message": f"Successfully retrieved {len(simulation_tokens)} simulation tokens ({game_tokens_count} game + {other_tokens_count} others)"
        })
        
    except Exception as e:
        logger.error(f"Error in get_simulation_tokens: {e}")
        return jsonify({
            "success": False,
            "error": "Internal server error",
            "message": str(e)
        }), 500

@api_bp.route('/tokens-stats', methods=['GET'])
def get_tokens_stats():
    """Get statistics about available tokens"""
    try:
        game_tokens, simulation_tokens = cmc_service.get_all_tokens_data()
        
        stats = {
            "game_tokens": {
                "count": len(game_tokens),
                "target": 30
            },
            "simulation_tokens": {
                "count": len(simulation_tokens),
                "target": 100,
                "game_tokens_included": len([t for t in simulation_tokens if t['is_game_token']]),
                "other_tokens_included": len([t for t in simulation_tokens if not t['is_game_token']])
            },
            "last_updated": datetime.utcnow().isoformat()
        }
        
        return jsonify({
            "success": True,
            "data": stats,
            "message": "Successfully retrieved token statistics"
        })
        
    except Exception as e:
        logger.error(f"Error in get_tokens_stats: {e}")
        return jsonify({
            "success": False,
            "error": "Internal server error",
            "message": str(e)
        }), 500
        
@api_bp.route('/validate-deck', methods=['POST'])
def validate_deck():
    """Validate if a deck meets tournament requirements"""
    try:
        data = request.get_json()
        
        if not data or 'selected_tokens' not in data:
            return jsonify({
                "success": False,
                "error": "Missing selected_tokens",
                "message": "selected_tokens array is required"
            }), 400
        
        selected_tokens = data['selected_tokens']
        
        if not isinstance(selected_tokens, list):
            return jsonify({
                "success": False,
                "error": "Invalid format",
                "message": "selected_tokens must be an array"
            }), 400
        
        # Normalize symbols
        selected_tokens = [token.upper() for token in selected_tokens]
        
        # Validate deck size
        if len(selected_tokens) != 5:
            return jsonify({
                "success": False,
                "error": "Invalid deck size",
                "message": f"Deck must contain exactly 5 tokens, got {len(selected_tokens)}"
            }), 400
        
        # Check for duplicates
        if len(set(selected_tokens)) != len(selected_tokens):
            return jsonify({
                "success": False,
                "error": "Duplicate tokens",
                "message": "All tokens in deck must be unique"
            }), 400
        
        # Validate token availability
        available_symbols = {token['symbol'] for token in cmc_service.get_available_game_tokens()}
        invalid_tokens = [token for token in selected_tokens if token not in available_symbols]
        
        if invalid_tokens:
            return jsonify({
                "success": False,
                "error": "Invalid tokens",
                "message": f"These tokens are not available: {', '.join(invalid_tokens)}"
            }), 400
        
        # Calculate weights and validate
        token_weights = []
        total_weight = 0
        
        for token in selected_tokens:
            weight = get_token_weight(token)
            token_weights.append({
                'symbol': token,
                'weight': weight
            })
            total_weight += weight
        
        # Check weight limit
        is_valid_weight = total_weight <= 28
        
        validation_result = {
            "is_valid": is_valid_weight and len(selected_tokens) == 5,
            "deck_analysis": {
                "total_tokens": len(selected_tokens),
                "total_weight": total_weight,
                "weight_limit": 28,
                "weight_remaining": 28 - total_weight,
                "weight_utilization": round((total_weight / 28) * 100, 1)
            },
            "token_breakdown": token_weights,
            "validation_checks": {
                "correct_size": len(selected_tokens) == 5,
                "no_duplicates": len(set(selected_tokens)) == len(selected_tokens),
                "valid_tokens": len(invalid_tokens) == 0,
                "within_weight_limit": is_valid_weight
            }
        }
        
        message = "Deck is valid and ready for tournament!" if validation_result["is_valid"] else "Deck validation failed - check requirements"
        
        return jsonify({
            "success": True,
            "data": validation_result,
            "message": message
        })
        
    except Exception as e:
        logger.error(f"Error in validate_deck: {e}")
        return jsonify({
            "success": False,
            "error": "Internal server error", 
            "message": str(e)
        }), 500
        
@api_bp.route('/simulate-session', methods=['POST'])
def simulate_session():
    """Lock deck and run simulation in one step"""
    try:
        data = request.get_json()
        logger.info(f"=== SIMULATE SESSION START ===")
        logger.info(f"Raw request data: {data}")

        # Основные проверки
        if not data:
            return jsonify({
                "success": False,
                "error": "No data provided",
                "message": "Request body is required"
            }), 400

        wallet_address = data.get('wallet_address')
        selected_tokens = data.get('selected_tokens', [])
        session_id = data.get('session_id')

        logger.info(f"Parsed data - wallet: {wallet_address}, tokens: {selected_tokens}, session_id: {session_id}")

        if not wallet_address:
            return jsonify({
                "success": False,
                "error": "Missing wallet_address",
                "message": "wallet_address is required"
            }), 400

        if not isinstance(selected_tokens, list) or len(selected_tokens) != 5:
            return jsonify({
                "success": False,
                "error": "Invalid selected_tokens",
                "message": "selected_tokens must be an array of exactly 5 token symbols"
            }), 400

        # Normalize token symbols
        original_tokens = selected_tokens.copy()
        selected_tokens = [symbol.upper() for symbol in selected_tokens]
        logger.info(f"Token normalization - original: {original_tokens}, normalized: {selected_tokens}")

        # Check for duplicates
        if len(set(selected_tokens)) != len(selected_tokens):
            return jsonify({
                "success": False,
                "error": "Duplicate tokens",
                "message": "All 5 tokens must be unique"
            }), 400

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
                return jsonify({
                    "success": False,
                    "error": "Already simulated",
                    "message": "This session has already been simulated"
                }), 409
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
            return jsonify({
                "success": False,
                "error": "Invalid tokens",
                "message": f"The following tokens are not available: {', '.join(invalid_tokens)}"
            }), 400

        logger.info(f"All selected tokens are valid: {selected_tokens}")

        # Check tournament weight limit
        total_weight, is_valid_weight = validate_deck_weight(selected_tokens)
        logger.info(f"Weight validation - total: {total_weight}, is_valid: {is_valid_weight}")
        
        if not is_valid_weight:
            return jsonify({
                "success": False,
                "error": "Deck exceeds weight limit",
                "message": f"Total deck weight ({total_weight}) exceeds tournament limit (28)"
            }), 400

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
                return jsonify({
                    "success": False,
                    "error": "Token not found",
                    "message": f"Token {symbol} is not available"
                }), 400

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
            'market_overview': results['market_analysis']['daily_sentiments']
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

        return jsonify({
            "success": True,
            "data": {
                "session": game_session_data,
                "simulation": simulation_results
            },
            "message": f"Deck locked and simulation completed! Final score: {results['final_score']}"
        })

    except Exception as e:
        logger.error(f"=== SIMULATE SESSION ERROR === Exception: {e}")
        logger.error(f"Exception type: {type(e).__name__}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        return jsonify({
            "success": False,
            "error": "Internal server error",
            "message": str(e)
        }), 500
        
@api_bp.route('/session/<session_id>/results', methods=['GET'])
def get_session_results(session_id):
    """Get detailed simulation results for a session"""
    try:
        if session_id not in game_sessions:
            return jsonify({
                "success": False,
                "error": "Session not found",
                "message": f"No session found with ID: {session_id}"
            }), 404
        
        session = game_sessions[session_id]
        
        if not session.get('simulation_completed'):
            return jsonify({
                "success": False,
                "error": "Simulation not completed",
                "message": "Run simulation first using POST /api/simulate-session"
            }), 400
        
        return jsonify({
            "success": True,
            "data": session.get('simulation_results', {}),
            "message": "Successfully retrieved simulation results"
        })
        
    except Exception as e:
        logger.error(f"Error in get_session_results: {e}")
        return jsonify({
            "success": False,
            "error": "Internal server error",
            "message": str(e)
        }), 500