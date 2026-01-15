"""
Admin Dashboard Routes - Complete Version
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
        
        from models import AdminUser
        user = AdminUser.authenticate(username, password)
        
        if user:
            session['admin_logged_in'] = True
            session['admin_user_id'] = user.id
            session['admin_username'] = user.username
            session['admin_role'] = user.role
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
@login_required
def dashboard():
    """Main admin dashboard with statistics"""
    from models import Reservation
    
    now = datetime.now(ZAGREB_TZ)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Get statistics
    stats = Reservation.get_stats()
    
    # Get today's reservations
    today_reservations = Reservation.get_by_date(now.date())
    
    # Get upcoming reservations (next 7 days)
    upcoming = Reservation.get_upcoming(days=7, limit=10)
    
    return render_template('admin/dashboard.html',
                         stats=stats,
                         today_reservations=today_reservations,
                         upcoming_reservations=upcoming,
                         current_time=now)

# ============================================================================
# RESERVATIONS MANAGEMENT
# ============================================================================

@admin_bp.route('/reservations')
@login_required
def reservations():
    """List all reservations with filtering"""
    from models import Reservation
    
    # Get filter parameters
    status_filter = request.args.get('status', '')
    date_filter = request.args.get('date', '')
    search_query = request.args.get('search', '')
    
    # Build query
    if search_query:
        reservations_list = Reservation.search(search_query)
    elif date_filter:
        try:
            filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
            reservations_list = Reservation.get_by_date(filter_date)
        except ValueError:
            reservations_list = Reservation.get_all()
    elif status_filter:
        reservations_list = Reservation.get_by_status(status_filter)
    else:
        reservations_list = Reservation.get_all()
    
    return render_template('admin/reservations.html',
                         reservations=reservations_list,
                         status_filter=status_filter,
                         date_filter=date_filter,
                         search_query=search_query)

@admin_bp.route('/reservations/<int:reservation_id>')
@login_required
def reservation_detail(reservation_id):
    """View single reservation details"""
    from models import Reservation
    
    reservation = Reservation.get_by_id(reservation_id)
    if not reservation:
        flash('Reservation not found.', 'danger')
        return redirect(url_for('admin.reservations'))
    
    return render_template('admin/reservation_detail.html', reservation=reservation)

@admin_bp.route('/reservations/<int:reservation_id>/update-status', methods=['POST'])
@login_required
def update_reservation_status(reservation_id):
    """Update reservation status"""
    from models import Reservation
    
    new_status = request.form.get('status')
    if new_status not in ['pending', 'confirmed', 'cancelled', 'completed', 'no-show']:
        flash('Invalid status.', 'danger')
        return redirect(url_for('admin.reservations'))
    
    reservation = Reservation.get_by_id(reservation_id)
    if reservation:
        reservation.update_status(new_status)
        flash(f'Reservation status updated to {new_status}.', 'success')
    else:
        flash('Reservation not found.', 'danger')
    
    return redirect(url_for('admin.reservations'))

@admin_bp.route('/reservations/<int:reservation_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_reservation(reservation_id):
    """Edit reservation details"""
    from models import Reservation
    
    reservation = Reservation.get_by_id(reservation_id)
    if not reservation:
        flash('Reservation not found.', 'danger')
        return redirect(url_for('admin.reservations'))
    
    if request.method == 'POST':
        # Update reservation fields
        reservation.customer_name = request.form.get('customer_name', reservation.customer_name)
        reservation.customer_phone = request.form.get('customer_phone', reservation.customer_phone)
        reservation.party_size = int(request.form.get('party_size', reservation.party_size))
        reservation.special_requests = request.form.get('special_requests', '')
        reservation.table_number = request.form.get('table_number', '')
        
        # Update date/time
        date_str = request.form.get('date')
        time_str = request.form.get('time')
        if date_str and time_str:
            try:
                reservation.reservation_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                reservation.reservation_time = datetime.strptime(time_str, '%H:%M').time()
            except ValueError:
                flash('Invalid date or time format.', 'danger')
                return render_template('admin/edit_reservation.html', reservation=reservation)
        
        reservation.save()
        flash('Reservation updated successfully.', 'success')
        return redirect(url_for('admin.reservations'))
    
    return render_template('admin/edit_reservation.html', reservation=reservation)

@admin_bp.route('/reservations/<int:reservation_id>/delete', methods=['POST'])
@login_required
def delete_reservation(reservation_id):
    """Delete a reservation"""
    from models import Reservation
    
    reservation = Reservation.get_by_id(reservation_id)
    if reservation:
        reservation.delete()
        flash('Reservation deleted.', 'success')
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
    from models import Reservation
    
    start = request.args.get('start', '')
    end = request.args.get('end', '')
    
    # Get all reservations (or filter by date range if provided)
    reservations_list = Reservation.get_all()
    
    events = []
    for res in reservations_list:
        # Combine date and time for event
        event_datetime = datetime.combine(res.reservation_date, res.reservation_time)
        
        # Color based on status
        color_map = {
            'pending': '#ffc107',
            'confirmed': '#28a745',
            'cancelled': '#dc3545',
            'completed': '#17a2b8',
            'no-show': '#6c757d'
        }
        
        events.append({
            'id': res.id,
            'title': f'{res.customer_name} ({res.party_size})',
            'start': event_datetime.isoformat(),
            'backgroundColor': color_map.get(res.status, '#6c757d'),
            'borderColor': color_map.get(res.status, '#6c757d'),
            'extendedProps': {
                'phone': res.customer_phone,
                'party_size': res.party_size,
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
    
    from models import AdminUser
    users_list = AdminUser.get_all()
    
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
        
        from models import AdminUser
        
        # Check if username exists
        if AdminUser.get_by_username(username):
            flash('Username already exists.', 'danger')
            return render_template('admin/create_user.html')
        
        # Create user
        user = AdminUser.create(username=username, email=email, password=password, role=role)
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
    
    from models import AdminUser
    user = AdminUser.get_by_id(user_id)
    if user:
        user.delete()
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
        from staff_chatbot import process_staff_message
        response = process_staff_message(message, session.get('admin_username', 'Staff'))
        
        return jsonify({'response': response})
    
    except ImportError:
        # Fallback if staff_chatbot module not available
        return jsonify({
            'response': 'Staff assistant is currently unavailable. Please check the system configuration.'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
            from staff_chatbot import process_staff_message
            response = process_staff_message(transcribed_text, session.get('admin_username', 'Staff'))
            
            return jsonify({
                'transcription': transcribed_text,
                'response': response
            })
        
        finally:
            # Clean up temp file
            import os
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    
    except ImportError:
        return jsonify({
            'transcription': '',
            'response': 'Staff assistant is currently unavailable.'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================================================
# PROFILE
# ============================================================================

@admin_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """User profile page"""
    from models import AdminUser
    
    user = AdminUser.get_by_id(session.get('admin_user_id'))
    if not user:
        flash('User not found.', 'danger')
        return redirect(url_for('admin.dashboard'))
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'update_profile':
            email = request.form.get('email', '').strip()
            if email:
                user.email = email
                user.save()
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
                user.set_password(new_password)
                user.save()
                flash('Password changed successfully.', 'success')
    
    return render_template('admin/profile.html', user=user)
