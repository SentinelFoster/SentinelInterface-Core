from datetime import datetime
from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

class Admin(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(64), unique=True, nullable=False)
    access_tier = db.Column(db.String(32), default="Public")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    interactions = db.relationship('Interaction', backref='user', lazy=True)

class Interaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    si_id = db.Column(db.String(32), nullable=False)
    user_input = db.Column(db.Text, nullable=False)
    si_response = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class AccessCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(64), unique=True, nullable=False)
    tier = db.Column(db.String(32), nullable=False)
    is_used = db.Column(db.Boolean, default=False)
    used_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    tier = db.Column(db.String(32), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    transaction_id = db.Column(db.String(128), nullable=True)
    status = db.Column(db.String(32), default="pending")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
