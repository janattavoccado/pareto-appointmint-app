"""
Staff Chatbot Routes - Add these routes to your admin_routes.py

These routes handle the staff chatbot interface for managing reservations.
"""

# =============================================================================
# ADD THESE IMPORTS TO THE TOP OF admin_routes.py
# =============================================================================

# from staff_chatbot import get_staff_chatbot
# import tempfile
# import os

# =============================================================================
# ADD THESE ROUTES TO admin_routes.py (inside the admin_bp blueprint)
# =============================================================================


@admin_bp.route('/staff-assistant')
@login_required
def staff_assistant():
    """Display the staff chatbot interface."""
    return render_template('admin/staff_chatbot.html')


@admin_bp.route('/staff-chat', methods=['POST'])
@login_required
def staff_chat():
    """Handle staff chatbot text messages."""
    try:
        data = request.get_json()
        message = data.get('message', '')
        session_id = data.get('session_id', 'default')
        
        if not message:
            return jsonify({'success': False, 'error': 'No message provided'})
        
        # Get the staff chatbot instance
        from models import DatabaseManager
        db = DatabaseManager()
        chatbot = get_staff_chatbot(db)
        
        # Process the message
        response = chatbot.process_message(session_id, message)
        
        return jsonify({
            'success': True,
            'response': response
        })
        
    except Exception as e:
        import logging
        logging.error(f"Staff chat error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })


@admin_bp.route('/staff-chat/voice', methods=['POST'])
@login_required
def staff_chat_voice():
    """Handle staff chatbot voice messages."""
    try:
        from openai import OpenAI
        client = OpenAI()
        
        # Get the audio file
        if 'audio' not in request.files:
            return jsonify({'success': False, 'error': 'No audio file provided'})
        
        audio_file = request.files['audio']
        session_id = request.form.get('session_id', 'default')
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as temp_file:
            audio_file.save(temp_file.name)
            temp_path = temp_file.name
        
        try:
            # Transcribe with Whisper
            with open(temp_path, 'rb') as audio:
                transcription = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio,
                    language="en"
                )
            
            transcribed_text = transcription.text
            
            if not transcribed_text:
                return jsonify({
                    'success': False,
                    'error': 'Could not transcribe audio'
                })
            
            # Get the staff chatbot instance
            from models import DatabaseManager
            db = DatabaseManager()
            chatbot = get_staff_chatbot(db)
            
            # Process the transcribed message
            response = chatbot.process_message(session_id, transcribed_text)
            
            return jsonify({
                'success': True,
                'transcription': transcribed_text,
                'response': response
            })
            
        finally:
            # Clean up temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
        
    except Exception as e:
        import logging
        logging.error(f"Staff voice chat error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        })


@admin_bp.route('/staff-chat/clear', methods=['POST'])
@login_required
def staff_chat_clear():
    """Clear staff chatbot conversation history."""
    try:
        data = request.get_json()
        session_id = data.get('session_id', 'default')
        
        from models import DatabaseManager
        db = DatabaseManager()
        chatbot = get_staff_chatbot(db)
        chatbot.clear_conversation(session_id)
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# =============================================================================
# UPDATE base.html NAVIGATION - Add this link to the sidebar
# =============================================================================

"""
Add this to the navigation in templates/admin/base.html:

<li class="nav-item">
    <a class="nav-link {% if request.endpoint == 'admin.staff_assistant' %}active{% endif %}" 
       href="{{ url_for('admin.staff_assistant') }}">
        <i class="bi bi-headset me-2"></i>
        Staff Assistant
    </a>
</li>
"""
