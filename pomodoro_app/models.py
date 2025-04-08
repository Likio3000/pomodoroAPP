# pomodoro_app/models.py
from datetime import datetime, timezone  # Ensure timezone is imported
from pomodoro_app import db
from flask_login import UserMixin
from sqlalchemy import Index # Import Index if needed

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    # Added index=True for faster email lookups, recommended for login checks
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    password = db.Column(db.String(200), nullable=False)  # stores hashed password

    # Relationship defined via backref in PomodoroSession

    def __repr__(self):
        return f'<User id={self.id} email={self.email}>'


class PomodoroSession(db.Model):
    __tablename__ = 'sessions'
    id = db.Column(db.Integer, primary_key=True)
    # Added index=True for faster lookups by user_id, ensure not nullable
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    work_duration = db.Column(db.Integer, nullable=False)   # work duration in minutes
    break_duration = db.Column(db.Integer, nullable=False)  # break duration in minutes

    # This timestamp definition is the standard way to store timezone-aware UTC times.
    # It relies on the database driver and SQLAlchemy handling the timezone correctly
    # upon reading and writing (especially important for SQLite which lacks native tz support).
    timestamp = db.Column(
        db.DateTime(timezone=True),             # Instructs SQLAlchemy to handle timezone (for supported backends)
        nullable=False,                         # Ensure timestamp is always set
        default=lambda: datetime.now(timezone.utc) # Default to current UTC time when creating new record IN PYTHON
    )

    # Define the relationship to the User model explicitly
    # lazy='select' (default) loads user when accessed.
    # lazy='joined' loads user with the session query using JOIN.
    # lazy='dynamic' makes user.sessions a query object (useful for further filtering/pagination).
    user = db.relationship('User', backref=db.backref('sessions', lazy='dynamic', order_by=timestamp.desc()))

    # Optional: Add an index on the timestamp column if you query/order by it frequently
    __table_args__ = (Index('ix_sessions_timestamp', timestamp), )


    def __repr__(self):
        # Use isoformat for a clearer representation including potential timezone
        ts_repr = self.timestamp.isoformat() if self.timestamp else "None"
        return f'<PomodoroSession id={self.id} user_id={self.user_id} time={ts_repr}>'