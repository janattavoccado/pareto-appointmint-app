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
from knowledgebase_manager import KnowledgeBaseManager

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')

# Enable CORS for future API integrations (e.g., Chatwoot webhook)
CORS(app)

# Initialize database
db = DatabaseManager.get_instance()

# Initialize knowledge base
kb = KnowledgeBaseManager.get_instance()


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


def get_common_template_context():
    """Get common context data for all templates."""
    return {
        'config': kb._config,
        'restaurant_name': kb.get_restaurant_name()
    }


# ============================================================================
# Web Routes - Main Pages
# ============================================================================

@app.route('/')
def index():
    """Render the main chat interface."""
    session_id = get_or_create_session_id()
    restaurant_name = kb.get_restaurant_name()
    return render_template('index.html', 
                         restaurant_name=restaurant_name,
                         session_id=session_id)


@app.route('/about')
def about():
    """Render the About Us page."""
    context = get_common_template_context()
    context['about'] = kb.get_about_us()
    return render_template('about.html', **context)


@app.route('/menu')
def menu():
    """Render the Menu page."""
    context = get_common_template_context()
    context['menu'] = kb.get_menu()
    return render_template('menu.html', **context)


@app.route('/contact')
def contact():
    """Render the Contact page."""
    context = get_common_template_context()
    
    # Get operating hours as a dictionary for the template
    hours = kb.get_operating_hours()
    context['operating_hours'] = {
        day: {'open': h.open, 'close': h.close, 'is_closed': h.is_closed}
        for day, h in hours.items()
    }
    context['special_notes'] = kb._config.get('operating_hours', {}).get('special_notes', '')
    
    return render_template('contact.html', **context)


# ============================================================================
# Chat API Routes
# ============================================================================

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


# ============================================================================
# Reservation API Routes
# ============================================================================

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
# Knowledge Base API Routes
# ============================================================================

@app.route('/api/restaurant-info', methods=['GET'])
def get_restaurant_info():
    """Get restaurant information from knowledge base."""
    try:
        info = kb.get_restaurant_info_for_agent()
        return jsonify({
            'success': True,
            'data': info.model_dump()
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/operating-hours', methods=['GET'])
def get_operating_hours():
    """Get operating hours from knowledge base."""
    try:
        hours = kb.get_operating_hours()
        is_open, message = kb.is_restaurant_open()
        return jsonify({
            'success': True,
            'hours': {day: h.model_dump() for day, h in hours.items()},
            'is_currently_open': is_open,
            'status_message': message
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/menu', methods=['GET'])
def get_menu_api():
    """Get menu from knowledge base."""
    try:
        menu_data = kb.get_menu()
        return jsonify({
            'success': True,
            'menu': menu_data
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/menu/search', methods=['GET'])
def search_menu():
    """Search menu items."""
    try:
        query = request.args.get('q', '')
        if not query:
            return jsonify({
                'success': False,
                'error': 'Search query is required'
            }), 400
        
        results = kb.search_menu(query)
        return jsonify({
            'success': True,
            'query': query,
            'results': [item.model_dump() for item in results],
            'count': len(results)
        })
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
        'service': 'Restaurant Booking Agent',
        'restaurant': kb.get_restaurant_name()
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
    
    restaurant_name = kb.get_restaurant_name()
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║           Restaurant Booking Agent - Flask Server            ║
╠══════════════════════════════════════════════════════════════╣
║  Server running at: http://{host}:{port}                      
║  Debug mode: {debug}                                          
║  Restaurant: {restaurant_name}
║                                                              
║  Pages:                                                      
║    - Home/Chat: http://{host}:{port}/                        
║    - About Us:  http://{host}:{port}/about                   
║    - Menu:      http://{host}:{port}/menu                    
║    - Contact:   http://{host}:{port}/contact                 
╚══════════════════════════════════════════════════════════════╝
    """)
    
    app.run(host=host, port=port, debug=debug)
