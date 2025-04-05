# pomodoro_app/__init__.py
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

# Initialize extensions (to be used later in factory)
db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'  # where to redirect for @login_required&#8203;:contentReference[oaicite:11]{index=11}

def create_app():
    app = Flask(__name__)
    # Configuration
    app.config['SECRET_KEY'] = 'your-secret-key-here'  # ideally from environment var&#8203;:contentReference[oaicite:12]{index=12}
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pomodoro.db'  # SQLite DB file&#8203;:contentReference[oaicite:13]{index=13}
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Initialize extensions with app
    db.init_app(app)
    login_manager.init_app(app)

    # Import models here so that they are registered with SQLAlchemy
    from pomodoro_app.models import User

    # User loader function for Flask-Login: load user by ID
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Register blueprints
    from pomodoro_app.auth.routes import auth as auth_blueprint
    from pomodoro_app.main.routes import main as main_blueprint
    app.register_blueprint(auth_blueprint)
    app.register_blueprint(main_blueprint)

    # Create database tables if not already created (for initial run)
    with app.app_context():
        db.create_all()

    return app
