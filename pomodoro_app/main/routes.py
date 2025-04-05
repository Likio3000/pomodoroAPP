# pomodoro_app/main/routes.py
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user

from pomodoro_app import db
from pomodoro_app.models import PomodoroSession

main = Blueprint('main', __name__)

@main.route('/')
def index():
    # Landing page - if user is logged in, redirect to dashboard, otherwise show welcome page
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return render_template('index.html')

@main.route('/timer')
@login_required
def timer():
    # Render the pomodoro timer page (user can start a new session)
    return render_template('main/timer.html')

@main.route('/complete_session', methods=['POST'])
@login_required
def complete_session():
    # This route is called via AJAX when a Pomodoro session finishes to log the session
    data = request.get_json()
    work_minutes = data.get('work')
    break_minutes = data.get('break')
    # Create a new session record in the database
    new_session = PomodoroSession(user_id=current_user.id, work_duration=work_minutes, break_duration=break_minutes)
    db.session.add(new_session)
    db.session.commit()
    return jsonify({'status': 'success'}), 200

@main.route('/dashboard')
@login_required
def dashboard():
    # Query all sessions for the current user
    sessions = PomodoroSession.query.filter_by(user_id=current_user.id).order_by(PomodoroSession.timestamp.desc()).all()
    # Calculate statistics
    total_focus = sum(sess.work_duration for sess in sessions)
    total_break = sum(sess.break_duration for sess in sessions)
    total_sessions = len(sessions)
    # (Optional) You could also compute additional stats, or limit sessions for display
    return render_template('main/dashboard.html',
                           total_focus=total_focus, total_break=total_break, total_sessions=total_sessions,
                           sessions=sessions)
