"""
Flask Application for Restaurant Booking Agent.
Provides web interface for interacting with the OpenAI-powered booking agent.
"""

import os
import asyncio
import uuid
from datetime import datetime
from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import the booking agent
from booking_agent import run_booking_agent, booking_agent
from models import DatabaseManager

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')

# Enable CORS for future API integrations (e.g., Chatwoot webhook)
CORS(app)

# Initialize database
db = DatabaseManager.get_instance()


# ============================================================================
# Helper Functions
# ============================================================================

def get_or_create_session_id():
    """Get existing session ID or create a new one."""
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    return session['session_id']


def get_conversation_history():
    """Get conversation history from session."""
    if 'conversation_history' not in session:
        session['conversation_history'] = []
    return session['conversation_history']


def save_conversation_history(history):
    """Save conversation history to session."""
    session['conversation_history'] = history
    session.modified = True


# ============================================================================
# Web Routes
# ============================================================================

@app.route('/')
def index():
    """Render the main chat interface."""
    session_id = get_or_create_session_id()
    restaurant_name = os.getenv('RESTAURANT_NAME', 'Our Restaurant')
    return render_template('index.html', 
                         restaurant_name=restaurant_name,
                         session_id=session_id)


@app.route('/chat', methods=['POST'])
def chat():
    """Handle chat messages from the web interface."""
    try:
        data = request.get_json()
        user_message = data.get('message', '').strip()
        
        if not user_message:
            return jsonify({
                'success': False,
                'error': 'Message cannot be empty'
            }), 400
        
        # Get session info
        session_id = get_or_create_session_id()
        conversation_history = get_conversation_history()
        
        # Run the booking agent
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            agent_response, updated_history = loop.run_until_complete(
                run_booking_agent(user_message, conversation_history)
            )
        finally:
            loop.close()
        
        # Save updated conversation history
        save_conversation_history(updated_history)
        
        return jsonify({
            'success': True,
            'response': agent_response,
            'session_id': session_id
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/reset', methods=['POST'])
def reset_conversation():
    """Reset the conversation history."""
    session['conversation_history'] = []
    session['session_id'] = str(uuid.uuid4())
    session.modified = True
    
    return jsonify({
        'success': True,
        'message': 'Conversation reset successfully',
        'session_id': session['session_id']
    })


@app.route('/reservations', methods=['GET'])
def get_reservations():
    """Get all reservations (admin endpoint)."""
    try:
        reservations = db.get_all_reservations()
        return jsonify({
            'success': True,
            'reservations': [r.to_dict() for r in reservations],
            'count': len(reservations)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/reservations/<int:reservation_id>', methods=['GET'])
def get_single_reservation(reservation_id):
    """Get a single reservation by ID."""
    try:
        reservation = db.get_reservation_by_id(reservation_id)
        if reservation:
            return jsonify({
                'success': True,
                'reservation': reservation.to_dict()
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Reservation not found'
            }), 404
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================================================
# Future: Chatwoot Webhook Endpoint
# ============================================================================

@app.route('/webhook/chatwoot', methods=['POST'])
def chatwoot_webhook():
    """
    Webhook endpoint for Chatwoot integration.
    This will be implemented when connecting to Chatwoot inbox.
    """
    # TODO: Implement Chatwoot webhook handling
    # 1. Verify webhook signature
    # 2. Parse incoming message
    # 3. Process with booking agent
    # 4. Send response back to Chatwoot
    
    try:
        data = request.get_json()
        
        # Log incoming webhook for debugging
        print(f"Received Chatwoot webhook: {data}")
        
        # Placeholder response
        return jsonify({
            'success': True,
            'message': 'Webhook received - Chatwoot integration pending'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================================================
# Health Check
# ============================================================================

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'service': 'Restaurant Booking Agent'
    })


# ============================================================================
# Error Handlers
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return jsonify({
        'success': False,
        'error': 'Resource not found'
    }), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    return jsonify({
        'success': False,
        'error': 'Internal server error'
    }), 500


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == '__main__':
    # Get configuration from environment
    debug = os.getenv('FLASK_DEBUG', 'True').lower() == 'true'
    host = os.getenv('FLASK_HOST', '127.0.0.1')
    port = int(os.getenv('FLASK_PORT', 5000))
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║           Restaurant Booking Agent - Flask Server            ║
╠══════════════════════════════════════════════════════════════╣
║  Server running at: http://{host}:{port}                      
║  Debug mode: {debug}                                          
║  Restaurant: {os.getenv('RESTAURANT_NAME', 'Our Restaurant')}
╚══════════════════════════════════════════════════════════════╝
    """)
    
    app.run(host=host, port=port, debug=debug)
