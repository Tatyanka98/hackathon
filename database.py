from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200))  # в реальном проекте хешировать
    avatar = db.Column(db.String(300), default='https://avatars.mds.yandex.net/i?id=1d31c64a866c718cd7b915b597b877ada4ee7880-4410363-images-thumbs&n=13')
    currency = db.Column(db.String(1), default='₽')
    subscriptions = db.relationship('Subscription', backref='user', lazy=True, cascade='all, delete-orphan')
    history = db.relationship('History', backref='user', lazy=True, order_by='History.timestamp.desc()')


class Subscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(200))
    category = db.Column(db.String(50))
    price = db.Column(db.Float, nullable=False)
    pay_day = db.Column(db.Integer)  # число месяца
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class Recommended(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    description = db.Column(db.String(200))
    category = db.Column(db.String(50))
    price = db.Column(db.Float)

class History(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(200))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)