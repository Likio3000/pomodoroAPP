# pomodoro_app/forms.py
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, IntegerField
from wtforms.validators import DataRequired, Email, EqualTo, Length, NumberRange

class RegistrationForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(min=2, max=100)])
    email = StringField('Email', validators=[DataRequired(), Email(message="Invalid email")])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6, message="Password too short")])
    confirm = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password', message="Passwords must match")])
    submit = SubmitField('Register')

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember Me')
    submit = SubmitField('Log In')


class SettingsForm(FlaskForm):
    preferred_work_minutes = IntegerField(
        'Preferred Work Minutes',
        validators=[DataRequired(), NumberRange(min=1, max=600)]
    )
    productivity_goal = StringField(
        'Productivity Goal',
        validators=[Length(max=200)]
    )
    submit = SubmitField('Save Settings')
