from flask import Flask, request, jsonify, render_template, session, redirect, url_for, flash
from database import db, User, Subscription, Recommended, History
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import imaplib
import email
import re
from datetime import datetime, timedelta
import random
import os

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///subscriptions.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# ВНИМАНИЕ: в production замените на случайную строку из переменной окружения
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
db.init_app(app)
CORS(app, supports_credentials=True)

# Создание таблиц и начальных данных
with app.app_context():
    db.create_all()
    if Recommended.query.count() == 0:
        recs = [
            Recommended(name='Spotify', description='Музыка без рекламы', category='Музыка', price=299),
            Recommended(name='СберПрайм', description='Видео, музыка, кэшбэк', category='Видео', price=399),
            Recommended(name='МТС Premium', description='Кино, музыка, книги', category='Видео', price=349),
            Recommended(name='VK Музыка', description='Миллионы треков', category='Музыка', price=199),
            Recommended(name='Кинопоиск', description='Фильмы и сериалы', category='Видео', price=399),
            Recommended(name='Apple Music', description='Пространственное аудио', category='Музыка', price=399),
            Recommended(name='Okko', description='Кинотеатр', category='Видео', price=399),
            Recommended(name='Bookmate', description='Книги и подкасты', category='Книги', price=399),
            Recommended(name='Dropbox', description='2 ТБ облака', category='Облако', price=699),
            Recommended(name='Иви', description='Заметки и базы', category='Видео', price=399)
        ]
        db.session.add_all(recs)
        db.session.commit()

    if not User.query.filter_by(email='demo@example.com').first():
        user = User(
            name='Демо Пользователь',
            email='demo@example.com',
            password_hash=generate_password_hash('123'),
            avatar='https://via.placeholder.com/100',
            currency='₽'
        )
        db.session.add(user)
        db.session.commit()
        subs = [
            Subscription(name='Netflix', description='4K, 4 экрана', category='Видео', price=799, pay_day=15, user_id=user.id),
            Subscription(name='Яндекс Плюс', description='Музыка, Кинопоиск', category='Музыка', price=299, pay_day=3, user_id=user.id),
            Subscription(name='VK Combo', description='Музыка + облако', category='Другое', price=189, pay_day=22, user_id=user.id)
        ]
        db.session.add_all(subs)
        db.session.commit()
        hist = [
            History(action='Добавлена подписка Netflix (15 марта)', user_id=user.id),
            History(action='Отключена подписка VK Combo (10 марта)', user_id=user.id),
            History(action='Изменена цена Яндекс Плюс (5 марта)', user_id=user.id)
        ]
        db.session.add_all(hist)
        db.session.commit()

def get_current_user():
    user_id = session.get('user_id')
    if user_id:
        return User.query.get(user_id)
    return None

# Маршруты для аутентификации (без изменений)
@app.route('/')
def index():
    if not get_current_user():
        return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            return redirect(url_for('index'))
        else:
            flash('Неверный email или пароль')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        if User.query.filter_by(email=email).first():
            flash('Пользователь с таким email уже существует')
            return redirect(url_for('register'))
        user = User(
            name=name,
            email=email,
            password_hash=generate_password_hash(password),
            avatar='https://via.placeholder.com/100',
            currency='₽'
        )
        db.session.add(user)
        db.session.commit()
        session['user_id'] = user.id
        return redirect(url_for('index'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))

# API эндпоинты
@app.route('/api/subscriptions', methods=['GET'])
def get_subscriptions():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    subs = [{
        'id': s.id,
        'name': s.name,
        'description': s.description,
        'category': s.category,
        'price': s.price,
        'payDay': s.pay_day
    } for s in user.subscriptions]
    return jsonify(subs)

@app.route('/api/subscriptions', methods=['POST'])
def add_subscription():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    existing = Subscription.query.filter_by(user_id=user.id, name=data['name']).first()
    if existing:
        return jsonify({'error': 'Такая подписка уже есть'}), 400
    sub = Subscription(
        name=data['name'],
        description=data.get('description', ''),
        category=data['category'],
        price=float(data['price']),
        pay_day=int(data.get('payDay', 1)),
        user_id=user.id
    )
    db.session.add(sub)
    hist = History(action=f'Добавлена подписка {data["name"]}', user_id=user.id)
    db.session.add(hist)
    db.session.commit()
    return jsonify({'id': sub.id}), 201

# Изменено: теперь можно менять и цену, и день списания
@app.route('/api/subscriptions/<int:sub_id>', methods=['PUT'])
def update_subscription(sub_id):
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    sub = Subscription.query.get_or_404(sub_id)
    if sub.user_id != user.id:
        return jsonify({'error': 'Forbidden'}), 403
    data = request.json
    changes = []
    if 'price' in data and data['price'] != sub.price:
        old_price = sub.price
        sub.price = float(data['price'])
        changes.append(f'цена с {old_price} на {sub.price}')
    if 'payDay' in data and data['payDay'] != sub.pay_day:
        old_day = sub.pay_day
        sub.pay_day = int(data['payDay'])
        changes.append(f'день списания с {old_day} на {sub.pay_day}')
    if changes:
        hist = History(action=f'Изменена подписка {sub.name}: {", ".join(changes)}', user_id=user.id)
        db.session.add(hist)
    db.session.commit()
    return jsonify({'status': 'ok'})

@app.route('/api/subscriptions/<int:sub_id>', methods=['DELETE'])
def delete_subscription(sub_id):
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    sub = Subscription.query.get_or_404(sub_id)
    if sub.user_id != user.id:
        return jsonify({'error': 'Forbidden'}), 403
    name = sub.name
    db.session.delete(sub)
    hist = History(action=f'Отключена подписка {name}', user_id=user.id)
    db.session.add(hist)
    db.session.commit()
    return jsonify({'status': 'ok'})

@app.route('/api/recommendations', methods=['GET'])
def get_recommendations():
    recs = Recommended.query.all()
    return jsonify([{
        'id': r.id,
        'name': r.name,
        'description': r.description,
        'category': r.category,
        'price': r.price
    } for r in recs])

@app.route('/api/connect-recommendation', methods=['POST'])
def connect_recommendation():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    rec_id = data.get('recommendationId')
    rec = Recommended.query.get(rec_id)
    if not rec:
        return jsonify({'error': 'Рекомендация не найдена'}), 404
    existing = Subscription.query.filter_by(user_id=user.id, name=rec.name).first()
    if existing:
        return jsonify({'error': 'Подписка уже добавлена'}), 400
    sub = Subscription(
        name=rec.name,
        description=rec.description,
        category=rec.category,
        price=rec.price,
        pay_day=1,
        user_id=user.id
    )
    db.session.add(sub)
    hist = History(action=f'Подключена подписка {rec.name} из рекомендаций', user_id=user.id)
    db.session.add(hist)
    db.session.commit()
    return jsonify({'id': sub.id}), 201

@app.route('/api/history', methods=['GET'])
def get_history():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    history = History.query.filter_by(user_id=user.id).order_by(History.timestamp.desc()).limit(10).all()
    return jsonify([{'action': h.action, 'timestamp': h.timestamp.isoformat()} for h in history])

@app.route('/api/profile', methods=['GET'])
def get_profile():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    return jsonify({
        'name': user.name,
        'email': user.email,
        'avatar': user.avatar,
        'currency': user.currency,
        'subscriptions': [s.name for s in user.subscriptions]
    })

@app.route('/api/profile', methods=['PUT'])
def update_profile():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    if 'avatar' in data:
        user.avatar = data['avatar']
    if 'currency' in data:
        user.currency = data['currency']
    db.session.commit()
    return jsonify({'status': 'ok'})

# Новый эндпоинт: уведомления о предстоящих списаниях
@app.route('/api/upcoming-payments', methods=['GET'])
def get_upcoming_payments():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    today = datetime.now().day
    upcoming = []
    for sub in user.subscriptions:
        # Простая логика: если день списания в интервале [today, today+3] (с учётом конца месяца)
        # В реальности нужно учитывать количество дней в месяце, но для демо упростим
        if (sub.pay_day >= today and sub.pay_day <= today + 3) or (today + 3 > 31 and sub.pay_day <= (today + 3 - 31)):
            upcoming.append({
                'id': sub.id,
                'name': sub.name,
                'price': sub.price,
                'payDay': sub.pay_day,
                'daysLeft': sub.pay_day - today if sub.pay_day >= today else sub.pay_day + (31 - today)
            })
    return jsonify(upcoming)

# Улучшенная аналитика с прогнозом
@app.route('/api/analytics', methods=['GET'])
def get_analytics():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    subs = user.subscriptions
    total_month = sum(s.price for s in subs)
    categories = {}
    for s in subs:
        categories[s.category] = categories.get(s.category, 0) + s.price

    # Прогноз на следующий месяц и год (на основе текущих подписок)
    forecast_next_month = total_month
    forecast_next_year = total_month * 12

    # Генерация данных для графиков в зависимости от периода будет на фронтенде,
    # здесь просто возвращаем базовые данные + прогноз
    months = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек']
    # Для имитации истории создадим случайные данные за последние 6 месяцев, где последний - текущий
    monthly_data = [random.randint(int(total_month*0.7), int(total_month*1.3)) for _ in range(5)] + [total_month]

    return jsonify({
        'totalMonth': total_month,
        'total3Months': total_month * 3,
        'totalYear': total_month * 12,
        'activeCount': len(subs),
        'categories': list(categories.keys()),
        'categorySums': list(categories.values()),
        'months': months[-6:],  # последние 6 месяцев
        'monthlyData': monthly_data,
        'forecastNextMonth': forecast_next_month,
        'forecastNextYear': forecast_next_year
    })

@app.route('/api/parse-email', methods=['POST'])
def parse_email():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    email_addr = data.get('email')
    password = data.get('password')
    server = data.get('server', 'imap.gmail.com')

    # Демо-заглушка
    if email_addr == 'demo@example.com' and password == '123':
        test_subs = [
            {'name': 'Netflix', 'price': 799, 'payDay': 15},
            {'name': 'Spotify', 'price': 169, 'payDay': 10},
            {'name': 'Apple Music', 'price': 249, 'payDay': 5}
        ]
        added = []
        for sub_info in test_subs:
            existing = Subscription.query.filter_by(user_id=user.id, name=sub_info['name']).first()
            if not existing:
                new_sub = Subscription(
                    name=sub_info['name'],
                    description='Импортировано из почты (демо)',
                    category='Другое',
                    price=sub_info['price'],
                    pay_day=sub_info['payDay'],
                    user_id=user.id
                )
                db.session.add(new_sub)
                added.append(sub_info['name'])
                hist = History(action=f'Автоматически добавлена подписка {sub_info["name"]} из почты (демо)', user_id=user.id)
                db.session.add(hist)
        db.session.commit()
        return jsonify({'added': added, 'message': f'Добавлено {len(added)} подписок (демо)'})

    return jsonify({'error': 'Реальный импорт из почты отключён. Используйте demo@example.com для теста.'}), 400

if __name__ == '__main__':
    app.run(debug=True, port=8080)
