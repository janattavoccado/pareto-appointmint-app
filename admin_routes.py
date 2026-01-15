"""
Admin Dashboard Routes - Complete Version
Uses DatabaseManager pattern for database operations.
Includes: Dashboard, Reservations, Calendar, Pricing, Users, Staff Assistant, Profile
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from functools import wraps
from datetime import datetime, timedelta
import pytz
import os
import json

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Zagreb timezone
ZAGREB_TZ = pytz.timezone('Europe/Zagreb')

def get_db():
    """Get database manager instance."""
    from models import DatabaseManager
    return DatabaseManager.get_instance()

def login_required(f):
    """Decorator to require admin login"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            flash('Please log in to access the admin dashboard.', 'warning')
            return redirect(url_for('admin.login'))
        return f(*args, **kwargs)
    return decorated_function

# ============================================================================
# AUTHENTICATION ROUTES
# ============================================================================

@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Admin login page"""
    if session.get('admin_logged_in'):
        return redirect(url_for('admin.dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        db = get_db()
        user = db.get_admin_user_by_username(username)
        
        if user and user.check_password(password):
            session['admin_logged_in'] = True
            session['admin_user_id'] = user.id
            session['admin_username'] = user.username
            session['admin_role'] = user.role
            
            # Update last login
            db.update_admin_user(user.id, last_login=datetime.utcnow())
            
            flash(f'Welcome back, {user.username}!', 'success')
            return redirect(url_for('admin.dashboard'))
        else:
            flash('Invalid username or password.', 'danger')
    
    return render_template('admin/login.html')

@admin_bp.route('/logout')
def logout():
    """Admin logout"""
    session.pop('admin_logged_in', None)
    session.pop('admin_user_id', None)
    session.pop('admin_username', None)
    session.pop('admin_role', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('admin.login'))

# ============================================================================
# DASHBOARD
# ============================================================================

@admin_bp.route('/')
@admin_bp.route('/dashboard')
@login_required
def dashboard():
    """Main admin dashboard with statistics"""
    db = get_db()
    
    now = datetime.now(ZAGREB_TZ)
    
    # Get statistics
    stats = db.get_reservation_stats(now)
    
    # Get today's reservations
    today_reservations = db.get_reservations_by_date(now)
    
    # Get upcoming reservations
    upcoming_reservations = db.get_upcoming_reservations(limit=10)
    
    return render_template('admin/dashboard.html',
                         stats=stats,
                         today_reservations=today_reservations,
                         upcoming_reservations=upcoming_reservations,
                         current_time=now)

# ============================================================================
# RESERVATIONS MANAGEMENT
# ============================================================================

@admin_bp.route('/reservations')
@login_required
def reservations():
    """List all reservations with filtering"""
    db = get_db()
    
    # Get filter parameters
    status_filter = request.args.get('status', '')
    date_filter = request.args.get('date', '')
    search_query = request.args.get('search', '')
    
    # Build query
    if search_query:
        reservations_list = db.search_reservations(search_query)
    elif date_filter:
        try:
            filter_date = datetime.strptime(date_filter, '%Y-%m-%d')
            reservations_list = db.get_reservations_by_date(filter_date)
        except ValueError:
            reservations_list = db.get_all_reservations(include_cancelled=True)
    elif status_filter:
        all_res = db.get_all_reservations(include_cancelled=True)
        reservations_list = [r for r in all_res if r.status == status_filter]
    else:
        reservations_list = db.get_all_reservations(include_cancelled=True)
    
    return render_template('admin/reservations.html',
                         reservations=reservations_list,
                         status_filter=status_filter,
                         date_filter=date_filter,
                         search_query=search_query)

@admin_bp.route('/reservations/<int:reservation_id>')
@login_required
def reservation_detail(reservation_id):
    """View single reservation details"""
    db = get_db()
    
    reservation = db.get_reservation_by_id(reservation_id)
    if not reservation:
        flash('Reservation not found.', 'danger')
        return redirect(url_for('admin.reservations'))
    
    return render_template('admin/reservation_detail.html', reservation=reservation)

@admin_bp.route('/reservations/<int:reservation_id>/update-status', methods=['POST'])
@login_required
def update_reservation_status(reservation_id):
    """Update reservation status"""
    db = get_db()
    
    new_status = request.form.get('status')
    valid_statuses = ['pending', 'confirmed', 'cancelled', 'completed', 'no_show', 'arrived', 'seated']
    
    if new_status not in valid_statuses:
        flash('Invalid status.', 'danger')
        return redirect(url_for('admin.reservations'))
    
    reservation = db.update_reservation_status(reservation_id, new_status)
    if reservation:
        flash(f'Reservation status updated to {new_status}.', 'success')
    else:
        flash('Reservation not found.', 'danger')
    
    return redirect(url_for('admin.reservations'))

@admin_bp.route('/reservations/<int:reservation_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_reservation(reservation_id):
    """Edit reservation details"""
    db = get_db()
    
    reservation = db.get_reservation_by_id(reservation_id)
    if not reservation:
        flash('Reservation not found.', 'danger')
        return redirect(url_for('admin.reservations'))
    
    if request.method == 'POST':
        # Prepare update data
        update_data = {}
        
        if request.form.get('user_name'):
            update_data['user_name'] = request.form.get('user_name')
        if request.form.get('phone_number'):
            update_data['phone_number'] = request.form.get('phone_number')
        if request.form.get('number_of_guests'):
            update_data['number_of_guests'] = int(request.form.get('number_of_guests'))
        if request.form.get('special_requests') is not None:
            update_data['special_requests'] = request.form.get('special_requests')
        if request.form.get('table_number') is not None:
            update_data['table_number'] = request.form.get('table_number')
        if request.form.get('status'):
            update_data['status'] = request.form.get('status')
        
        # Update date/time
        date_str = request.form.get('date')
        time_str = request.form.get('time')
        if date_str and time_str:
            try:
                new_datetime = datetime.strptime(f"{date_str} {time_str}", '%Y-%m-%d %H:%M')
                update_data['date_time'] = new_datetime
            except ValueError:
                flash('Invalid date or time format.', 'danger')
                return render_template('admin/edit_reservation.html', reservation=reservation)
        
        # Perform update
        updated = db.update_reservation(reservation_id, **update_data)
        if updated:
            flash('Reservation updated successfully.', 'success')
            return redirect(url_for('admin.reservations'))
        else:
            flash('Error updating reservation.', 'danger')
    
    return render_template('admin/edit_reservation.html', reservation=reservation)

@admin_bp.route('/reservations/<int:reservation_id>/delete', methods=['POST'])
@login_required
def delete_reservation(reservation_id):
    """Delete (cancel) a reservation"""
    db = get_db()
    
    result = db.cancel_reservation(reservation_id)
    if result:
        flash('Reservation cancelled.', 'success')
    else:
        flash('Reservation not found.', 'danger')
    
    return redirect(url_for('admin.reservations'))

# ============================================================================
# CALENDAR VIEW
# ============================================================================

@admin_bp.route('/calendar')
@login_required
def calendar():
    """Calendar view of reservations"""
    return render_template('admin/calendar.html')

@admin_bp.route('/api/calendar-events')
@login_required
def calendar_events():
    """API endpoint for calendar events"""
    db = get_db()
    
    # Get all reservations
    reservations_list = db.get_all_reservations(include_cancelled=False)
    
    events = []
    for res in reservations_list:
        # Color based on status
        color_map = {
            'pending': '#ffc107',
            'confirmed': '#28a745',
            'cancelled': '#dc3545',
            'completed': '#17a2b8',
            'no_show': '#6c757d',
            'arrived': '#007bff',
            'seated': '#20c997'
        }
        
        events.append({
            'id': res.id,
            'title': f'{res.user_name} ({res.number_of_guests})',
            'start': res.date_time.isoformat() if res.date_time else None,
            'backgroundColor': color_map.get(res.status, '#6c757d'),
            'borderColor': color_map.get(res.status, '#6c757d'),
            'extendedProps': {
                'phone': res.phone_number,
                'party_size': res.number_of_guests,
                'status': res.status,
                'special_requests': res.special_requests or '',
                'table_number': res.table_number or ''
            }
        })
    
    return jsonify(events)

# ============================================================================
# PRICING & PLANS
# ============================================================================

@admin_bp.route('/pricing')
@login_required
def pricing():
    """Pricing and plans page"""
    plans = [
        {
            'name': 'Starter',
            'price': 29,
            'currency': 'EUR',
            'period': 'month',
            'features': [
                'Up to 100 reservations/month',
                'Basic chatbot widget',
                'Email notifications',
                'Standard support',
                '1 restaurant location'
            ],
            'highlighted': False
        },
        {
            'name': 'Professional',
            'price': 79,
            'currency': 'EUR',
            'period': 'month',
            'features': [
                'Up to 500 reservations/month',
                'Voice + text chatbot',
                'SMS & email notifications',
                'Priority support',
                'Up to 3 locations',
                'Staff assistant chatbot',
                'Advanced analytics'
            ],
            'highlighted': True
        },
        {
            'name': 'Enterprise',
            'price': 199,
            'currency': 'EUR',
            'period': 'month',
            'features': [
                'Unlimited reservations',
                'Full AI capabilities',
                'All notification channels',
                '24/7 dedicated support',
                'Unlimited locations',
                'Custom integrations',
                'White-label option',
                'API access'
            ],
            'highlighted': False
        }
    ]
    
    return render_template('admin/pricing.html', plans=plans)

# ============================================================================
# USER MANAGEMENT
# ============================================================================

@admin_bp.route('/users')
@login_required
def users():
    """User management page"""
    # Check if current user is admin
    if session.get('admin_role') != 'admin':
        flash('You do not have permission to manage users.', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    db = get_db()
    users_list = db.get_all_admin_users()
    
    return render_template('admin/users.html', users=users_list)

@admin_bp.route('/users/create', methods=['GET', 'POST'])
@login_required
def create_user():
    """Create new admin user"""
    if session.get('admin_role') != 'admin':
        flash('You do not have permission to create users.', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        role = request.form.get('role', 'staff')
        
        if not username or not email or not password:
            flash('All fields are required.', 'danger')
            return render_template('admin/create_user.html')
        
        db = get_db()
        
        # Check if username exists
        existing = db.get_admin_user_by_username(username)
        if existing:
            flash('Username already exists.', 'danger')
            return render_template('admin/create_user.html')
        
        # Create user
        user = db.create_admin_user(username=username, email=email, password=password, role=role)
        if user:
            flash(f'User {username} created successfully.', 'success')
            return redirect(url_for('admin.users'))
        else:
            flash('Error creating user.', 'danger')
    
    return render_template('admin/create_user.html')

@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
def delete_user(user_id):
    """Delete admin user"""
    if session.get('admin_role') != 'admin':
        flash('You do not have permission to delete users.', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    # Prevent self-deletion
    if user_id == session.get('admin_user_id'):
        flash('You cannot delete your own account.', 'danger')
        return redirect(url_for('admin.users'))
    
    db = get_db()
    result = db.delete_admin_user(user_id)
    if result:
        flash('User deleted.', 'success')
    else:
        flash('User not found.', 'danger')
    
    return redirect(url_for('admin.users'))

# ============================================================================
# STAFF ASSISTANT CHATBOT
# ============================================================================

@admin_bp.route('/staff-assistant')
@login_required
def staff_assistant():
    """Staff assistant chatbot interface"""
    return render_template('admin/staff_assistant.html')

@admin_bp.route('/api/staff-chat', methods=['POST'])
@login_required
def staff_chat():
    """API endpoint for staff chatbot"""
    try:
        data = request.get_json()
        message = data.get('message', '')
        
        if not message:
            return jsonify({'error': 'No message provided'}), 400
        
        # Import and use staff chatbot
        try:
            from staff_chatbot import process_staff_message
            response = process_staff_message(message, session.get('admin_username', 'Staff'))
        except ImportError:
            # Fallback response if module not available
            response = process_staff_message_fallback(message)
        
        return jsonify({'response': response})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def process_staff_message_fallback(message: str) -> str:
    """Fallback staff message processor when OpenAI module is not available."""
    db = get_db()
    message_lower = message.lower()
    
    # Simple keyword-based responses
    if 'today' in message_lower and 'reservation' in message_lower:
        now = datetime.now(ZAGREB_TZ)
        reservations = db.get_reservations_by_date(now)
        if not reservations:
            return "No reservations found for today."
        
        result = f"Today's reservations ({len(reservations)} total):\n\n"
        for res in reservations:
            time_str = res.date_time.strftime('%H:%M') if res.date_time else 'N/A'
            result += f"• #{res.id} - {res.user_name} at {time_str}\n"
            result += f"  Party: {res.number_of_guests} | Status: {res.status}\n"
        return result
    
    elif 'statistic' in message_lower or 'stats' in message_lower:
        now = datetime.now(ZAGREB_TZ)
        stats = db.get_reservation_stats(now)
        return f"""Reservation Statistics:

Total Today: {stats.get('total', 0)}
Pending: {stats.get('pending', 0)}
Confirmed: {stats.get('confirmed', 0)}
Completed: {stats.get('completed', 0)}
Total Guests: {stats.get('total_guests', 0)}"""
    
    elif 'search' in message_lower or 'find' in message_lower:
        # Extract search term (simple approach)
        words = message.split()
        search_term = words[-1] if len(words) > 1 else ''
        if search_term:
            results = db.search_reservations(search_term)
            if not results:
                return f"No reservations found matching '{search_term}'."
            
            result = f"Found {len(results)} reservation(s):\n\n"
            for res in results:
                result += f"• #{res.id} - {res.user_name} ({res.phone_number})\n"
            return result
    
    return """I can help you with:
• View today's reservations - "Show today's reservations"
• Get statistics - "Show statistics"
• Search reservations - "Search for [name]"

For full AI capabilities, ensure the staff_chatbot module is configured."""

@admin_bp.route('/api/staff-voice', methods=['POST'])
@login_required
def staff_voice():
    """API endpoint for staff voice input"""
    try:
        if 'audio' not in request.files:
            return jsonify({'error': 'No audio file provided'}), 400
        
        audio_file = request.files['audio']
        
        # Save temporarily
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as tmp:
            audio_file.save(tmp.name)
            tmp_path = tmp.name
        
        try:
            # Transcribe with Whisper
            from openai import OpenAI
            client = OpenAI()
            
            with open(tmp_path, 'rb') as f:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f
                )
            
            transcribed_text = transcript.text
            
            # Process with staff chatbot
            try:
                from staff_chatbot import process_staff_message
                response = process_staff_message(transcribed_text, session.get('admin_username', 'Staff'))
            except ImportError:
                response = process_staff_message_fallback(transcribed_text)
            
            return jsonify({
                'transcription': transcribed_text,
                'response': response
            })
        
        finally:
            # Clean up temp file
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================================================
# PROFILE
# ============================================================================

@admin_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """User profile page"""
    db = get_db()
    
    user = db.get_admin_user_by_id(session.get('admin_user_id'))
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'update_profile':
            email = request.form.get('email', '').strip()
            if email:
                db.update_admin_user(user.id, email=email)
                flash('Profile updated.', 'success')
        
        elif action == 'change_password':
            current_password = request.form.get('current_password', '')
            new_password = request.form.get('new_password', '')
            confirm_password = request.form.get('confirm_password', '')
            
            if not user.check_password(current_password):
                flash('Current password is incorrect.', 'danger')
            elif new_password != confirm_password:
                flash('New passwords do not match.', 'danger')
            elif len(new_password) < 6:
                flash('Password must be at least 6 characters.', 'danger')
            else:
                db.update_admin_user_password(user.id, new_password)
                flash('Password changed successfully.', 'success')
        
        # Refresh user data
        user = db.get_admin_user_by_id(session.get('admin_user_id'))
    
    return render_template('admin/profile.html', user=user)
