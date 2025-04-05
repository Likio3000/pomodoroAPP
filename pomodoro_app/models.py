# pomodoro_app/models.py
from datetime import datetime
from pomodoro_app import db
from flask_login import UserMixin

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    password = db.Column(db.String(200), nullable=False)  # stores hashed password

    def __repr__(self):
        return f'<User {self.email}>'

class PomodoroSession(db.Model):
    __tablename__ = 'sessions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    work_duration = db.Column(db.Integer, nullable=False)   # work duration in minutes
    break_duration = db.Column(db.Integer, nullable=False)  # break duration in minutes
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship to user (optional, for convenience if needed)
    user = db.relationship('User', backref=db.backref('sessions', lazy=True))

    def __repr__(self):
        return f'<PomodoroSession {self.id}: {self.work_duration}/{self.break_duration} min>'
