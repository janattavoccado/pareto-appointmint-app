"""
Admin Dashboard Routes for Restaurant Booking System
=====================================================

This module provides admin routes for viewing and managing reservations.
Uses database-based authentication for admin users.

Usage in app.py:
    from admin_routes import admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')
"""

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, session
from datetime import datetime, timedelta
from functools import wraps
import os

# Create blueprint
admin_bp = Blueprint('admin', __name__, 
                     template_folder='templates',
                     static_folder='static',
                     static_url_path='/admin/static')


def get_db():
    """Get database manager instance."""
    from models import DatabaseManager
    return DatabaseManager.get_instance()


def admin_required(f):
    """Decorator for admin authentication."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin.login'))
        return f(*args, **kwargs)
    return decorated_function


def superadmin_required(f):
    """Decorator for superadmin-only routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin.login'))
        if not session.get('is_superadmin'):
            flash('You do not have permission to access this page', 'error')
            return redirect(url_for('admin.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


# =============================================================================
# Authentication Routes
# =============================================================================

@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Admin login page with database authentication."""
    # If already logged in, redirect to dashboard
    if session.get('admin_logged_in'):
        return redirect(url_for('admin.dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if not username or not password:
            flash('Please enter both username and password', 'error')
            return render_template('admin/login.html')
        
        db = get_db()
        admin = db.authenticate_admin(username, password)
        
        if admin:
            session['admin_logged_in'] = True
            session['admin_id'] = admin.id
            session['admin_username'] = admin.username
            session['admin_fullname'] = admin.full_name or admin.username
            session['is_superadmin'] = admin.is_superadmin
            
            flash(f'Welcome back, {admin.full_name or admin.username}!', 'success')
            return redirect(url_for('admin.dashboard'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('admin/login.html')


@admin_bp.route('/logout')
def logout():
    """Admin logout."""
    session.pop('admin_logged_in', None)
    session.pop('admin_id', None)
    session.pop('admin_username', None)
    session.pop('admin_fullname', None)
    session.pop('is_superadmin', None)
    flash('You have been logged out', 'info')
    return redirect(url_for('admin.login'))


# =============================================================================
# Dashboard Routes
# =============================================================================

@admin_bp.route('/')
@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    """Main admin dashboard with overview stats."""
    db = get_db()
    
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    week_end = today + timedelta(days=7)
    
    # Get all reservations
    all_reservations = db.get_all_reservations(include_cancelled=True)
    
    # Calculate stats
    today_reservations = [r for r in all_reservations 
                         if r.date_time and today <= r.date_time < tomorrow and r.status == 'confirmed']
    
    upcoming_reservations = [r for r in all_reservations 
                            if r.date_time and r.date_time >= datetime.now() and r.status == 'confirmed']
    upcoming_reservations = sorted(upcoming_reservations, key=lambda x: x.date_time)[:10]
    
    week_reservations = [r for r in all_reservations 
                        if r.date_time and today <= r.date_time < week_end and r.status == 'confirmed']
    
    # Count by status
    confirmed_count = len([r for r in all_reservations if r.status == 'confirmed'])
    cancelled_count = len([r for r in all_reservations if r.status == 'cancelled'])
    completed_count = len([r for r in all_reservations if r.status == 'completed'])
    
    # Total guests today
    total_guests_today = sum(r.number_of_guests for r in today_reservations)
    
    stats = {
        'today_count': len(today_reservations),
        'today_guests': total_guests_today,
        'week_count': len(week_reservations),
        'total_count': len(all_reservations),
        'confirmed_count': confirmed_count,
        'cancelled_count': cancelled_count,
        'completed_count': completed_count
    }
    
    return render_template('admin/dashboard.html', 
                          stats=stats, 
                          upcoming_reservations=upcoming_reservations,
                          today=today,
                          now=datetime.now())


# =============================================================================
# Reservations Management Routes
# =============================================================================

@admin_bp.route('/reservations')
@admin_required
def reservations():
    """View all reservations with filtering."""
    db = get_db()
    
    # Get filter parameters
    date_filter = request.args.get('date')
    status_filter = request.args.get('status', 'all')
    search_query = request.args.get('search', '')
    
    # Get all reservations
    all_reservations = db.get_all_reservations(include_cancelled=True)
    
    # Apply filters
    filtered = all_reservations
    
    if date_filter:
        try:
            filter_date = datetime.strptime(date_filter, '%Y-%m-%d')
            next_day = filter_date + timedelta(days=1)
            filtered = [r for r in filtered if r.date_time and filter_date <= r.date_time < next_day]
        except ValueError:
            pass
    
    if status_filter and status_filter != 'all':
        filtered = [r for r in filtered if r.status == status_filter]
    
    if search_query:
        search_lower = search_query.lower()
        filtered = [r for r in filtered if 
                   search_lower in r.user_name.lower() or 
                   search_lower in r.phone_number.lower() or
                   search_lower in str(r.id)]
    
    # Sort by date (newest first)
    filtered = sorted(filtered, key=lambda x: x.date_time if x.date_time else datetime.min, reverse=True)
    
    return render_template('admin/reservations.html', 
                          reservations=filtered,
                          date_filter=date_filter,
                          status_filter=status_filter,
                          search_query=search_query,
                          now=datetime.now())


@admin_bp.route('/reservations/<int:reservation_id>')
@admin_required
def reservation_detail(reservation_id):
    """View single reservation details."""
    db = get_db()
    reservation = db.get_reservation_by_id(reservation_id)
    
    if not reservation:
        flash('Reservation not found', 'error')
        return redirect(url_for('admin.reservations'))
    
    return render_template('admin/reservation_detail.html', reservation=reservation, now=datetime.now())


@admin_bp.route('/reservations/<int:reservation_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_reservation(reservation_id):
    """Edit a reservation."""
    db = get_db()
    reservation = db.get_reservation_by_id(reservation_id)
    
    if not reservation:
        flash('Reservation not found', 'error')
        return redirect(url_for('admin.reservations'))
    
    if request.method == 'POST':
        try:
            # Parse form data
            date_str = request.form.get('date')
            time_str = request.form.get('time')
            date_time = datetime.strptime(f"{date_str} {time_str}", '%Y-%m-%d %H:%M')
            
            # Update reservation
            db.update_reservation(
                reservation_id,
                user_name=request.form.get('user_name'),
                phone_number=request.form.get('phone_number'),
                number_of_guests=int(request.form.get('number_of_guests')),
                date_time=date_time,
                status=request.form.get('status')
            )
            
            flash('Reservation updated successfully', 'success')
            return redirect(url_for('admin.reservation_detail', reservation_id=reservation_id))
        except Exception as e:
            flash(f'Error updating reservation: {str(e)}', 'error')
    
    return render_template('admin/edit_reservation.html', reservation=reservation, now=datetime.now())


@admin_bp.route('/reservations/<int:reservation_id>/cancel', methods=['POST'])
@admin_required
def cancel_reservation(reservation_id):
    """Cancel a reservation."""
    db = get_db()
    
    if db.cancel_reservation(reservation_id):
        flash('Reservation cancelled successfully', 'success')
    else:
        flash('Failed to cancel reservation', 'error')
    
    return redirect(request.referrer or url_for('admin.reservations'))


@admin_bp.route('/reservations/<int:reservation_id>/confirm', methods=['POST'])
@admin_required
def confirm_reservation(reservation_id):
    """Confirm/restore a reservation."""
    db = get_db()
    
    reservation = db.update_reservation(reservation_id, status='confirmed')
    if reservation:
        flash('Reservation confirmed successfully', 'success')
    else:
        flash('Failed to confirm reservation', 'error')
    
    return redirect(request.referrer or url_for('admin.reservations'))


@admin_bp.route('/reservations/<int:reservation_id>/complete', methods=['POST'])
@admin_required
def complete_reservation(reservation_id):
    """Mark a reservation as completed."""
    db = get_db()
    
    reservation = db.update_reservation(reservation_id, status='completed')
    if reservation:
        flash('Reservation marked as completed', 'success')
    else:
        flash('Failed to update reservation', 'error')
    
    return redirect(request.referrer or url_for('admin.reservations'))


# =============================================================================
# Calendar View Routes
# =============================================================================

@admin_bp.route('/calendar')
@admin_required
def calendar():
    """Calendar view of reservations."""
    return render_template('admin/calendar.html', now=datetime.now())


@admin_bp.route('/api/calendar-events')
@admin_required
def calendar_events():
    """API endpoint for calendar events (JSON)."""
    db = get_db()
    
    # Get date range from query params
    start = request.args.get('start')
    end = request.args.get('end')
    
    all_reservations = db.get_all_reservations(include_cancelled=False)
    
    # Filter by date range if provided
    if start and end:
        try:
            start_date = datetime.fromisoformat(start.replace('Z', '+00:00')).replace(tzinfo=None)
            end_date = datetime.fromisoformat(end.replace('Z', '+00:00')).replace(tzinfo=None)
            all_reservations = [r for r in all_reservations 
                               if r.date_time and start_date <= r.date_time <= end_date]
        except ValueError:
            pass
    
    # Convert to calendar events
    events = []
    for r in all_reservations:
        if r.date_time:
            color = '#28a745' if r.status == 'confirmed' else '#6c757d'
            if r.status == 'completed':
                color = '#17a2b8'
            
            events.append({
                'id': r.id,
                'title': f"{r.user_name} ({r.number_of_guests} guests)",
                'start': r.date_time.isoformat(),
                'end': (r.date_time + timedelta(hours=r.time_slot or 2)).isoformat(),
                'color': color,
                'extendedProps': {
                    'phone': r.phone_number,
                    'guests': r.number_of_guests,
                    'status': r.status
                }
            })
    
    return jsonify(events)


# =============================================================================
# Admin User Management Routes
# =============================================================================

@admin_bp.route('/users')
@superadmin_required
def admin_users():
    """List all admin users."""
    db = get_db()
    admins = db.get_all_admins()
    return render_template('admin/users.html', admins=admins, now=datetime.now())


@admin_bp.route('/users/new', methods=['GET', 'POST'])
@superadmin_required
def new_admin_user():
    """Create a new admin user."""
    if request.method == 'POST':
        try:
            db = get_db()
            
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            confirm_password = request.form.get('confirm_password', '')
            email = request.form.get('email', '').strip() or None
            full_name = request.form.get('full_name', '').strip() or None
            is_superadmin = request.form.get('is_superadmin') == 'on'
            
            # Validation
            if not username:
                flash('Username is required', 'error')
                return render_template('admin/user_form.html', admin=None, now=datetime.now())
            
            if not password:
                flash('Password is required', 'error')
                return render_template('admin/user_form.html', admin=None, now=datetime.now())
            
            if password != confirm_password:
                flash('Passwords do not match', 'error')
                return render_template('admin/user_form.html', admin=None, now=datetime.now())
            
            if len(password) < 6:
                flash('Password must be at least 6 characters', 'error')
                return render_template('admin/user_form.html', admin=None, now=datetime.now())
            
            # Create admin
            admin = db.create_admin(
                username=username,
                password=password,
                email=email,
                full_name=full_name,
                is_superadmin=is_superadmin
            )
            
            flash(f'Admin user "{username}" created successfully', 'success')
            return redirect(url_for('admin.admin_users'))
            
        except ValueError as e:
            flash(str(e), 'error')
        except Exception as e:
            flash(f'Error creating admin user: {str(e)}', 'error')
    
    return render_template('admin/user_form.html', admin=None, now=datetime.now())


@admin_bp.route('/users/<int:admin_id>/edit', methods=['GET', 'POST'])
@superadmin_required
def edit_admin_user(admin_id):
    """Edit an admin user."""
    db = get_db()
    admin = db.get_admin_by_id(admin_id)
    
    if not admin:
        flash('Admin user not found', 'error')
        return redirect(url_for('admin.admin_users'))
    
    if request.method == 'POST':
        try:
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            confirm_password = request.form.get('confirm_password', '')
            email = request.form.get('email', '').strip() or None
            full_name = request.form.get('full_name', '').strip() or None
            is_superadmin = request.form.get('is_superadmin') == 'on'
            is_active = request.form.get('is_active') == 'on'
            
            # Validation
            if not username:
                flash('Username is required', 'error')
                return render_template('admin/user_form.html', admin=admin, now=datetime.now())
            
            if password and password != confirm_password:
                flash('Passwords do not match', 'error')
                return render_template('admin/user_form.html', admin=admin, now=datetime.now())
            
            if password and len(password) < 6:
                flash('Password must be at least 6 characters', 'error')
                return render_template('admin/user_form.html', admin=admin, now=datetime.now())
            
            # Update admin
            update_data = {
                'username': username,
                'email': email,
                'full_name': full_name,
                'is_superadmin': is_superadmin,
                'is_active': is_active
            }
            
            if password:
                update_data['password'] = password
            
            db.update_admin(admin_id, **update_data)
            
            flash(f'Admin user "{username}" updated successfully', 'success')
            return redirect(url_for('admin.admin_users'))
            
        except ValueError as e:
            flash(str(e), 'error')
        except Exception as e:
            flash(f'Error updating admin user: {str(e)}', 'error')
    
    return render_template('admin/user_form.html', admin=admin, now=datetime.now())


@admin_bp.route('/users/<int:admin_id>/delete', methods=['POST'])
@superadmin_required
def delete_admin_user(admin_id):
    """Delete an admin user."""
    db = get_db()
    
    # Prevent self-deletion
    if admin_id == session.get('admin_id'):
        flash('You cannot delete your own account', 'error')
        return redirect(url_for('admin.admin_users'))
    
    try:
        if db.delete_admin(admin_id):
            flash('Admin user deleted successfully', 'success')
        else:
            flash('Admin user not found', 'error')
    except ValueError as e:
        flash(str(e), 'error')
    except Exception as e:
        flash(f'Error deleting admin user: {str(e)}', 'error')
    
    return redirect(url_for('admin.admin_users'))


# =============================================================================
# Profile Routes (for current admin)
# =============================================================================

@admin_bp.route('/profile', methods=['GET', 'POST'])
@admin_required
def profile():
    """View and edit current admin's profile."""
    db = get_db()
    admin = db.get_admin_by_id(session.get('admin_id'))
    
    if not admin:
        flash('Profile not found', 'error')
        return redirect(url_for('admin.dashboard'))
    
    if request.method == 'POST':
        try:
            email = request.form.get('email', '').strip() or None
            full_name = request.form.get('full_name', '').strip() or None
            
            db.update_admin(admin.id, email=email, full_name=full_name)
            
            # Update session
            session['admin_fullname'] = full_name or admin.username
            
            flash('Profile updated successfully', 'success')
            return redirect(url_for('admin.profile'))
            
        except Exception as e:
            flash(f'Error updating profile: {str(e)}', 'error')
    
    return render_template('admin/profile.html', admin=admin, now=datetime.now())


@admin_bp.route('/profile/password', methods=['GET', 'POST'])
@admin_required
def change_password():
    """Change current admin's password."""
    if request.method == 'POST':
        try:
            db = get_db()
            admin = db.get_admin_by_id(session.get('admin_id'))
            
            current_password = request.form.get('current_password', '')
            new_password = request.form.get('new_password', '')
            confirm_password = request.form.get('confirm_password', '')
            
            # Verify current password
            if not admin.check_password(current_password):
                flash('Current password is incorrect', 'error')
                return render_template('admin/change_password.html', now=datetime.now())
            
            # Validate new password
            if not new_password:
                flash('New password is required', 'error')
                return render_template('admin/change_password.html', now=datetime.now())
            
            if new_password != confirm_password:
                flash('New passwords do not match', 'error')
                return render_template('admin/change_password.html', now=datetime.now())
            
            if len(new_password) < 6:
                flash('Password must be at least 6 characters', 'error')
                return render_template('admin/change_password.html', now=datetime.now())
            
            # Change password
            db.change_admin_password(admin.id, new_password)
            
            flash('Password changed successfully', 'success')
            return redirect(url_for('admin.profile'))
            
        except Exception as e:
            flash(f'Error changing password: {str(e)}', 'error')
    
    return render_template('admin/change_password.html', now=datetime.now())


# =============================================================================
# API Routes for AJAX operations
# =============================================================================

@admin_bp.route('/api/reservations/<int:reservation_id>', methods=['GET'])
@admin_required
def api_get_reservation(reservation_id):
    """API: Get reservation details."""
    db = get_db()
    reservation = db.get_reservation_by_id(reservation_id)
    
    if not reservation:
        return jsonify({'error': 'Reservation not found'}), 404
    
    return jsonify(reservation.to_dict())


@admin_bp.route('/api/reservations/<int:reservation_id>', methods=['PUT'])
@admin_required
def api_update_reservation(reservation_id):
    """API: Update reservation."""
    db = get_db()
    data = request.get_json()
    
    try:
        # Parse date_time if provided
        if 'date_time' in data:
            data['date_time'] = datetime.fromisoformat(data['date_time'])
        
        reservation = db.update_reservation(reservation_id, **data)
        if reservation:
            return jsonify(reservation.to_dict())
        return jsonify({'error': 'Reservation not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@admin_bp.route('/api/stats')
@admin_required
def api_stats():
    """API: Get dashboard stats."""
    db = get_db()
    
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    
    all_reservations = db.get_all_reservations(include_cancelled=True)
    
    today_reservations = [r for r in all_reservations 
                         if r.date_time and today <= r.date_time < tomorrow and r.status == 'confirmed']
    
    return jsonify({
        'today_count': len(today_reservations),
        'today_guests': sum(r.number_of_guests for r in today_reservations),
        'total_count': len(all_reservations),
        'confirmed_count': len([r for r in all_reservations if r.status == 'confirmed']),
        'cancelled_count': len([r for r in all_reservations if r.status == 'cancelled'])
    })
