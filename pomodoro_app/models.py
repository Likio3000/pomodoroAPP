# pomodoro_app/models.py
from datetime import datetime, timezone, date # Add date import
from pomodoro_app import db
from flask_login import UserMixin
from sqlalchemy import Index, func # Import func for default values

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    password = db.Column(db.String(200), nullable=False)

    # +++ Points and Streaks +++
    total_points = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    consecutive_sessions = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    last_session_timestamp = db.Column(db.DateTime(timezone=True), nullable=True) # Track last completion for consistency streak
    daily_streak = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    last_active_date = db.Column(db.Date, nullable=True) # Track last active date for daily streak

    # Relationship backrefs defined below (for PomodoroSession)
    # sessions backref defined in PomodoroSession model

class PomodoroSession(db.Model):
    __tablename__ = 'sessions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    work_duration = db.Column(db.Integer, nullable=False)
    break_duration = db.Column(db.Integer, nullable=False)
    # +++ Points earned in this specific session (optional but good for history) +++
    points_earned = db.Column(db.Integer, nullable=True) # Can be null for older sessions before points system
    timestamp = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    # Define relationship and backref here
    user = db.relationship('User', backref=db.backref('sessions', lazy='dynamic', order_by=timestamp.desc()))

    # Add Index for user_id and timestamp for efficient querying
    __table_args__ = (
        Index('ix_sessions_user_id_timestamp', "user_id", "timestamp"),
        Index('ix_sessions_timestamp', timestamp),
    )

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
    # +++ Current Multiplier for this active work phase +++
    current_multiplier = db.Column(db.Float, nullable=False, default=1.0, server_default='1.0')


    # Optional: Define a relationship back to the User
    # This allows accessing the active timer state directly from a user object if needed
    # Note: Use uselist=False for one-to-one relationship from User perspective
    # user = db.relationship('User', backref=db.backref('active_timer_state', uselist=False))
    # Decided against the backref on User for simplicity, can query by user_id easily.

    def __repr__(self):
        end_repr = self.end_time.isoformat() if self.end_time else "None"        return f'<ActiveTimerState user_id={self.user_id} phase={self.phase} mult={self.current_multiplier} ends={end_repr}>'


# +++ Chat Message History Model +++
class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    role = db.Column(db.String(20), nullable=False)
    text = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    user = db.relationship(
        'User',
        backref=db.backref(
            'chat_messages',
            lazy='dynamic',
            order_by='ChatMessage.timestamp',
            cascade='all, delete-orphan'
        )
    )

    __table_args__ = (
        Index('ix_chat_messages_user_id_timestamp', 'user_id', 'timestamp'),
    )

