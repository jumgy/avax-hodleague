from flask import Flask
from flask_cors import CORS
from config import Config
from api.routes import api_bp
import logging

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Enable CORS for all routes
    CORS(app)
    
    # Register API blueprint
    app.register_blueprint(api_bp, url_prefix='/api')
    
    # Setup logging
    logging.basicConfig(
        level=getattr(logging, Config.LOG_LEVEL),
        format='%(asctime)s %(levelname)s %(name)s %(message)s'
    )


    @app.route('/')
    def index():
        return {
            "message": "Fantasy Crypto Game API",
            "version": "1.0.0",
            "endpoints": [
                "GET /api/tokens - Get 30 game tokens for user selection",
                "GET /api/simulation-tokens - Get 100 tokens for simulation calculations",
                "GET /api/tournament - Get tournament information",
                "POST /api/lock-deck - Lock a deck of 5 tokens",
                "POST /api/simulate-session - Run simulation for locked deck",
                "GET /api/session/<session_id> - Get session details",
                "GET /api/session/<session_id>/results - Get simulation results",
                "GET /api/sessions - Get all sessions"
            ]
        }
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=5000)