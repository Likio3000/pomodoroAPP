# pomodoro_app/main/routes.py
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, session
from flask_login import login_required, current_user

from pomodoro_app import db, limiter
from pomodoro_app.models import PomodoroSession

main = Blueprint('main', __name__)

@main.route('/')
@limiter.limit("10 per minute")
def index():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return render_template('index.html')

@main.route('/timer')
@login_required
def timer():
    return render_template('main/timer.html')

@main.route('/start_timer', methods=['POST'])
@login_required
@limiter.limit("10 per minute")
def start_timer():
    # Set the active timer flag when a Pomodoro session is started
    session['active_timer'] = True
    return jsonify({'status': 'timer started'}), 200

@main.route('/complete_session', methods=['POST'])
@login_required
@limiter.limit("10 per minute")
def complete_session():
    data = request.get_json()
    work_minutes = data.get('work')
    break_minutes = data.get('break')
    # Log the Pomodoro session in the database
    new_session = PomodoroSession(user_id=current_user.id, work_duration=work_minutes, break_duration=break_minutes)
    db.session.add(new_session)
    db.session.commit()
    # Clear the active timer flag since the session is now complete
    session.pop('active_timer', None)
    return jsonify({'status': 'success'}), 200

@main.route('/dashboard')
@login_required
@limiter.limit("10 per minute")
def dashboard():
    sessions = PomodoroSession.query.filter_by(user_id=current_user.id).order_by(PomodoroSession.timestamp.desc()).all()
    total_focus = sum(sess.work_duration for sess in sessions)
    total_break = sum(sess.break_duration for sess in sessions)
    total_sessions = len(sessions)
    return render_template('main/dashboard.html',
                           total_focus=total_focus, total_break=total_break, total_sessions=total_sessions,
                           sessions=sessions)
