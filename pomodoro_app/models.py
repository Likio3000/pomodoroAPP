# pomodoro_app/models.py
from datetime import datetime, timezone
from pomodoro_app import db
from flask_login import UserMixin
from sqlalchemy import Index

class User(UserMixin, db.Model):
    # ... (existing User model remains the same) ...
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    password = db.Column(db.String(200), nullable=False)
    # Relationship backrefs defined below

class PomodoroSession(db.Model):
    # ... (existing PomodoroSession model remains the same) ...
    __tablename__ = 'sessions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    work_duration = db.Column(db.Integer, nullable=False)
    break_duration = db.Column(db.Integer, nullable=False)
    timestamp = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    user = db.relationship('User', backref=db.backref('sessions', lazy='dynamic', order_by=timestamp.desc()))
    __table_args__ = (Index('ix_sessions_timestamp', timestamp), )

# +++ NEW MODEL for Active Timer State +++
class ActiveTimerState(db.Model):
    __tablename__ = 'active_timers'
    # Use user_id as primary key assuming one active timer per user
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True, nullable=False)
    phase = db.Column(db.String(10), nullable=False) # 'work' or 'break'
    start_time = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    end_time = db.Column(db.DateTime(timezone=True), nullable=False)
    work_duration_minutes = db.Column(db.Integer, nullable=False)
    break_duration_minutes = db.Column(db.Integer, nullable=False)

    # Optional: Define a relationship back to the User
    # This allows accessing the active timer state directly from a user object if needed
    # user = db.relationship('User', backref=db.backref('active_timer_state', uselist=False))
    # Decided against the backref for simplicity for now, can query by user_id easily.

    def __repr__(self):
        end_repr = self.end_time.isoformat() if self.end_time else "None"
        return f'<ActiveTimerState user_id={self.user_id} phase={self.phase} ends={end_repr}>'