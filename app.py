"""
Flask Application for Restaurant Booking Agent.
Provides web interface for interacting with the OpenAI-powered booking agent.
Includes Chatwoot webhook integration for WhatsApp messaging.
"""

import os
import uuid
import logging
import tempfile
from datetime import datetime
from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import the booking agent (using Responses API - synchronous)
from booking_agent import process_booking_message, get_or_create_history, update_history
from models import DatabaseManager
from knowledgebase_manager import KnowledgeBaseManager

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')

# Enable CORS for API integrations (e.g., Chatwoot webhook)
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
        
        # Run the booking agent (synchronous - using Responses API)
        agent_response, updated_history = process_booking_message(
            message=user_message,
            user_id=session_id,
            conversation_history=conversation_history
        )
        
        # Save updated conversation history
        save_conversation_history(updated_history)
        
        return jsonify({
            'success': True,
            'response': agent_response,
            'session_id': session_id
        })
        
    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
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


@app.route('/chat/audio', methods=['POST'])
def chat_audio():
    """
    Handle audio messages from the web interface.
    Transcribes audio using OpenAI Whisper and processes with booking agent.
    """
    try:
        # Check if audio file is in the request
        if 'audio' not in request.files:
            return jsonify({
                'success': False,
                'error': 'No audio file provided'
            }), 400
        
        audio_file = request.files['audio']
        
        if audio_file.filename == '':
            return jsonify({
                'success': False,
                'error': 'No audio file selected'
            }), 400
        
        # Get session info
        session_id = get_or_create_session_id()
        conversation_history = get_conversation_history()
        
        # Save audio to a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as temp_audio:
            audio_file.save(temp_audio.name)
            temp_audio_path = temp_audio.name
        
        try:
            # Initialize OpenAI client
            client = OpenAI()
            
            # Supported languages for transcription
            # Whisper will auto-detect the language from this list
            # Croatian (hr) is default, but also supports: English (en), German (de), Italian (it), Spanish (es)
            SUPPORTED_LANGUAGES = ['hr', 'en', 'de', 'it', 'es']
            
            # First, try to transcribe without specifying language (auto-detect)
            # Whisper is very good at detecting language automatically
            with open(temp_audio_path, 'rb') as audio:
                transcription = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio,
                    # Not specifying language allows Whisper to auto-detect
                    # Supported: Croatian, English, German, Italian, Spanish
                    # If you want to force a specific language, uncomment below:
                    # language="hr"  # Force Croatian
                )
            
            transcribed_text = transcription.text.strip()
            
            # Log detected language info
            logger.info(f"Audio transcribed (auto-detected language): {transcribed_text}")
            
            if not transcribed_text:
                return jsonify({
                    'success': False,
                    'error': 'Could not transcribe audio. Please try again or type your message.'
                }), 400
            
            # Process with booking agent
            agent_response, updated_history = process_booking_message(
                message=transcribed_text,
                user_id=session_id,
                conversation_history=conversation_history
            )
            
            # Save updated conversation history
            save_conversation_history(updated_history)
            
            return jsonify({
                'success': True,
                'transcribed_text': transcribed_text,
                'response': agent_response,
                'session_id': session_id
            })
            
        finally:
            # Clean up temporary file
            if os.path.exists(temp_audio_path):
                os.remove(temp_audio_path)
        
    except Exception as e:
        logger.error(f"Audio chat error: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


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
def get_operating_hours_api():
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
# Chatwoot Webhook Endpoint
# ============================================================================

@app.route('/api/chatwoot/webhook', methods=['POST'])
def chatwoot_webhook():
    """
    Webhook endpoint for Chatwoot integration.
    Handles incoming messages from WhatsApp via Chatwoot.
    
    URL: https://your-app.herokuapp.com/api/chatwoot/webhook
    """
    try:
        payload = request.get_json()
        
        if not payload:
            logger.warning("Empty Chatwoot webhook payload received")
            return jsonify({"error": "Empty payload"}), 400
        
        # Import and use the webhook handler
        from chatwoot_handler import webhook_handler
        
        # Process the webhook
        result = webhook_handler(payload)
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Chatwoot webhook error: {e}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


# Legacy webhook endpoint (for backwards compatibility)
@app.route('/webhook/chatwoot', methods=['POST'])
def chatwoot_webhook_legacy():
    """Legacy webhook endpoint - redirects to new endpoint."""
    return chatwoot_webhook()


# ============================================================================
# Widget API Endpoints (Embeddable Chat Widget)
# ============================================================================

# In-memory storage for widget sessions (use Redis in production for scaling)
widget_sessions = {}

@app.route('/widget/embed.js', methods=['GET'])
def widget_embed_js():
    """
    Serve the embeddable widget JavaScript file.
    Usage: <script src="https://your-app.herokuapp.com/widget/embed.js"></script>
    """
    try:
        widget_path = os.path.join(app.static_folder, 'widget', 'embed.js')
        with open(widget_path, 'r') as f:
            js_content = f.read()
        
        response = app.make_response(js_content)
        response.headers['Content-Type'] = 'application/javascript'
        response.headers['Cache-Control'] = 'public, max-age=3600'  # Cache for 1 hour
        return response
    except Exception as e:
        logger.error(f"Widget JS error: {e}")
        return 'console.error("ParetoBooking: Failed to load widget");', 500


@app.route('/widget/chat', methods=['POST'])
def widget_chat():
    """
    Handle text messages from the embeddable widget.
    
    Request JSON:
    {
        "assistant_id": "rest_abc123xyz",
        "session_id": "widget_rest_abc123xyz_...",
        "message": "I want to book a table"
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        assistant_id = data.get('assistant_id')
        session_id = data.get('session_id')
        message = data.get('message', '').strip()
        
        if not assistant_id:
            return jsonify({'success': False, 'error': 'assistant_id is required'}), 400
        
        if not message:
            return jsonify({'success': False, 'error': 'message is required'}), 400
        
        # Generate session_id if not provided
        if not session_id:
            session_id = f"widget_{assistant_id}_{uuid.uuid4().hex[:12]}"
        
        # Get or create conversation history for this widget session
        if session_id not in widget_sessions:
            widget_sessions[session_id] = {
                'assistant_id': assistant_id,
                'history': [],
                'created_at': datetime.now().isoformat()
            }
        
        conversation_history = widget_sessions[session_id]['history']
        
        # Create user_id from assistant_id and session for tracking
        user_id = f"{assistant_id}:{session_id}"
        
        # Process with booking agent
        agent_response, updated_history = process_booking_message(
            message=message,
            user_id=user_id,
            conversation_history=conversation_history
        )
        
        # Update stored history
        widget_sessions[session_id]['history'] = updated_history
        
        logger.info(f"Widget chat - Assistant: {assistant_id}, Session: {session_id[:20]}..., Message: {message[:50]}...")
        
        return jsonify({
            'success': True,
            'response': agent_response,
            'session_id': session_id
        })
        
    except Exception as e:
        logger.error(f"Widget chat error: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/widget/chat/audio', methods=['POST'])
def widget_chat_audio():
    """
    Handle audio messages from the embeddable widget.
    Transcribes audio using Whisper and processes with booking agent.
    
    Request (multipart/form-data):
    - audio: audio file (webm)
    - assistant_id: restaurant assistant ID
    - session_id: widget session ID
    """
    try:
        # Get form data
        assistant_id = request.form.get('assistant_id')
        session_id = request.form.get('session_id')
        audio_file = request.files.get('audio')
        
        if not assistant_id:
            return jsonify({'success': False, 'error': 'assistant_id is required'}), 400
        
        if not audio_file:
            return jsonify({'success': False, 'error': 'No audio file provided'}), 400
        
        # Generate session_id if not provided
        if not session_id:
            session_id = f"widget_{assistant_id}_{uuid.uuid4().hex[:12]}"
        
        # Save audio to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as temp_audio:
            audio_file.save(temp_audio.name)
            temp_audio_path = temp_audio.name
        
        try:
            # Initialize OpenAI client
            client = OpenAI()
            
            # Transcribe audio using Whisper (auto-detect language)
            with open(temp_audio_path, 'rb') as audio:
                transcription = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio
                    # Auto-detect language (supports: hr, en, de, it, es, etc.)
                )
            
            transcribed_text = transcription.text.strip()
            
            if not transcribed_text:
                return jsonify({
                    'success': False,
                    'error': 'Could not transcribe audio'
                }), 400
            
            logger.info(f"Widget audio transcribed: {transcribed_text}")
            
            # Get or create conversation history
            if session_id not in widget_sessions:
                widget_sessions[session_id] = {
                    'assistant_id': assistant_id,
                    'history': [],
                    'created_at': datetime.now().isoformat()
                }
            
            conversation_history = widget_sessions[session_id]['history']
            user_id = f"{assistant_id}:{session_id}"
            
            # Process with booking agent
            agent_response, updated_history = process_booking_message(
                message=transcribed_text,
                user_id=user_id,
                conversation_history=conversation_history
            )
            
            # Update stored history
            widget_sessions[session_id]['history'] = updated_history
            
            return jsonify({
                'success': True,
                'transcribed_text': transcribed_text,
                'response': agent_response,
                'session_id': session_id
            })
            
        finally:
            # Clean up temp file
            if os.path.exists(temp_audio_path):
                os.remove(temp_audio_path)
        
    except Exception as e:
        logger.error(f"Widget audio error: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/widget/config/<assistant_id>', methods=['GET'])
def widget_config(assistant_id):
    """
    Get widget configuration for a specific assistant.
    This can be extended to load custom configurations per restaurant.
    """
    try:
        # For now, return default config with restaurant info from knowledgebase
        restaurant_name = kb.get_restaurant_name()
        
        config = {
            'assistant_id': assistant_id,
            'restaurant_name': restaurant_name,
            'welcome_message': f"Hi! I'm the booking assistant for {restaurant_name}. How can I help you today?",
            'primary_color': '#4CAF50',
            'supported_languages': ['hr', 'en', 'de', 'it', 'es'],
            'features': {
                'voice_input': True,
                'text_input': True
            }
        }
        
        return jsonify({
            'success': True,
            'config': config
        })
        
    except Exception as e:
        logger.error(f"Widget config error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/widget/demo', methods=['GET'])
def widget_demo():
    """
    Demo page showing the embedded widget in action.
    """
    return render_template('widget_demo.html')


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
        'restaurant': kb.get_restaurant_name(),
        'chatwoot_configured': bool(os.getenv('CHATWOOT_API_ACCESS_TOKEN'))
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
    # Heroku sets PORT environment variable
    debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    host = os.getenv('FLASK_HOST', '0.0.0.0')
    port = int(os.getenv('PORT', os.getenv('FLASK_PORT', 5000)))
    
    restaurant_name = kb.get_restaurant_name()
    chatwoot_configured = bool(os.getenv('CHATWOOT_API_ACCESS_TOKEN'))
    
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║           Restaurant Booking Agent - Flask Server            ║
╠══════════════════════════════════════════════════════════════╣
║  Server running at: http://{host}:{port}                      
║  Debug mode: {debug}                                          
║  Restaurant: {restaurant_name}
║  Chatwoot: {'Configured' if chatwoot_configured else 'Not configured'}
║                                                              
║  Pages:                                                      
║    - Home/Chat: http://{host}:{port}/                        
║    - About Us:  http://{host}:{port}/about                   
║    - Menu:      http://{host}:{port}/menu                    
║    - Contact:   http://{host}:{port}/contact                 
║    - Widget Demo: http://{host}:{port}/widget/demo           
║                                                              
║  API Endpoints:                                              
║    - Chatwoot Webhook: /api/chatwoot/webhook                 
║    - Widget Chat:      /widget/chat                          
║    - Widget Audio:     /widget/chat/audio                    
║    - Widget JS:        /widget/embed.js                      
║    - Health Check:     /health                               
╚══════════════════════════════════════════════════════════════╝
    """)
    
    app.run(host=host, port=port, debug=debug)
