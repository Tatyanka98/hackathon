from flask import Flask, request, jsonify, render_template, session, redirect, url_for, flash
from database import db, User, Subscription, Recommended, History
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import imaplib
import email
import email.header
import email.utils
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

# ─── Словарь известных сервисов-подписок ───────────────────────────────────────
# Ключ: фрагмент домена/названия отправителя или темы (lowercase)
# Значение: (display_name, category, price_rub — None если ищем в теле письма)
KNOWN_SERVICES = {
    'netflix':        ('Netflix',        'Видео',   None),
    'spotify':        ('Spotify',        'Музыка',  None),
    'apple':          ('Apple',          'Музыка',  None),
    'yandex':         ('Яндекс Плюс',   'Музыка',  None),
    'яндекс':         ('Яндекс Плюс',   'Музыка',  None),
    'kinopoisk':      ('Кинопоиск',     'Видео',   None),
    'кинопоиск':      ('Кинопоиск',     'Видео',   None),
    'vk':             ('VK Музыка',     'Музыка',  None),
    'okko':           ('Okko',           'Видео',   None),
    'sberbank':       ('СберПрайм',     'Видео',   None),
    'сбер':           ('СберПрайм',     'Видео',   None),
    'mts':            ('МТС Premium',   'Видео',   None),
    'мтс':            ('МТС Premium',   'Видео',   None),
    'bookmate':       ('Bookmate',       'Книги',   None),
    'litres':         ('Литрес',         'Книги',   None),
    'литрес':         ('Литрес',         'Книги',   None),
    'dropbox':        ('Dropbox',        'Облако',  None),
    'google':         ('Google One',     'Облако',  None),
    'icloud':         ('iCloud+',        'Облако',  None),
    'adobe':          ('Adobe CC',       'Другое',  None),
    'notion':         ('Notion',         'Другое',  None),
    'chatgpt':        ('ChatGPT Plus',   'Другое',  None),
    'openai':         ('ChatGPT Plus',   'Другое',  None),
    'microsoft':      ('Microsoft 365',  'Другое',  None),
    'ivi':            ('Иви',            'Видео',   None),
    'иви':            ('Иви',            'Видео',   None),
    'more.tv':        ('More.TV',        'Видео',   None),
    'premier':        ('Premier',        'Видео',   None),
    'zvuk':           ('Звук',           'Музыка',  None),
    'звук':           ('Звук',           'Музыка',  None),
    'telegram':       ('Telegram Premium','Другое', None),
}

# Паттерны для извлечения суммы из текста письма
PRICE_PATTERNS = [
    r'(\d[\d\s]*[,.]?\d*)\s*(?:руб|рублей|₽|RUB)',
    r'(?:сумма|итого|списано|оплата|charged|amount|total)[^\d]{0,20}(\d[\d\s]*[,.]?\d*)',
    r'(\d[\d\s]{1,6}[,.]?\d{0,2})\s*(?:р\.|р\b)',
]

def decode_header_value(value: str) -> str:
    """Декодирует заголовок письма из RFC 2047."""
    parts = email.header.decode_header(value)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or 'utf-8', errors='replace'))
        else:
            decoded.append(part)
    return ' '.join(decoded)

def get_email_text(msg) -> str:
    """Извлекает текстовое содержимое письма (plain text или html stripped)."""
    text = ''
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get('Content-Disposition', ''))
            if 'attachment' in cd:
                continue
            if ct == 'text/plain':
                charset = part.get_content_charset() or 'utf-8'
                text += part.get_payload(decode=True).decode(charset, errors='replace')
                break
            elif ct == 'text/html' and not text:
                charset = part.get_content_charset() or 'utf-8'
                html = part.get_payload(decode=True).decode(charset, errors='replace')
                # Убираем теги — оставляем только текст
                text += re.sub(r'<[^>]+>', ' ', html)
    else:
        charset = msg.get_content_charset() or 'utf-8'
        text = msg.get_payload(decode=True).decode(charset, errors='replace')
    return text

def extract_price(text: str) -> float | None:
    """Ищет первую упоминаемую сумму в тексте письма."""
    for pattern in PRICE_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            raw = re.sub(r'\s', '', m.group(1)).replace(',', '.')
            try:
                val = float(raw)
                if 10 <= val <= 100000:   # правдоподобный диапазон цены подписки
                    return round(val, 2)
            except ValueError:
                continue
    return None

def match_service(sender: str, subject: str) -> tuple | None:
    """Определяет сервис по отправителю и теме."""
    haystack = (sender + ' ' + subject).lower()
    for keyword, service_info in KNOWN_SERVICES.items():
        if keyword in haystack:
            return service_info
    return None

def extract_pay_day(text: str, date_str: str) -> int:
    """Пытается извлечь день списания из текста или даты письма."""
    m = re.search(r'(?:каждое|каждый|ежемесячно\s+\d+|списание\s+\d+)[^\d]{0,5}(\d{1,2})', text, re.IGNORECASE)
    if m:
        day = int(m.group(1))
        if 1 <= day <= 31:
            return day
    try:
        t = email.utils.parsedate(date_str)
        if t:
            return t[2]
    except Exception:
        pass
    return 1


@app.route('/api/parse-email', methods=['POST'])
def parse_email():
    user = get_current_user()
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.json
    email_addr = data.get('email', '').strip()
    password   = data.get('password', '')
    server     = data.get('server', '').strip()

    if not email_addr or not password:
        return jsonify({'error': 'Укажите email и пароль'}), 400

    # Автоопределение IMAP-сервера если не указан
    if not server:
        domain = email_addr.split('@')[-1].lower()
        imap_map = {
            'gmail.com':       'imap.gmail.com',
            'googlemail.com':  'imap.gmail.com',
            'yahoo.com':       'imap.mail.yahoo.com',
            'yandex.ru':       'imap.yandex.ru',
            'ya.ru':           'imap.yandex.ru',
            'mail.ru':         'imap.mail.ru',
            'bk.ru':           'imap.mail.ru',
            'inbox.ru':        'imap.mail.ru',
            'list.ru':         'imap.mail.ru',
            'outlook.com':     'outlook.office365.com',
            'hotmail.com':     'outlook.office365.com',
            'live.com':        'outlook.office365.com',
            'rambler.ru':      'imap.rambler.ru',
        }
        server = imap_map.get(domain, f'imap.{domain}')

    # Подключаемся по IMAP
    try:
        mail = imaplib.IMAP4_SSL(server, timeout=10)
    except Exception as e:
        return jsonify({'error': f'Не удалось подключиться к серверу {server}: {str(e)}'}), 400

    try:
        mail.login(email_addr, password)
    except imaplib.IMAP4.error:
        mail.logout()
        return jsonify({'error': 'Неверный email или пароль. '
                                  'Для Gmail используйте пароль приложения (не обычный пароль).'}), 401

    try:
        mail.select('INBOX')

        # Ищем письма за последние 90 дней с ключевыми словами
        since_date = (datetime.now() - timedelta(days=90)).strftime('%d-%b-%Y')
        search_terms = [
            f'(SINCE {since_date} SUBJECT "подписка")',
            f'(SINCE {since_date} SUBJECT "subscription")',
            f'(SINCE {since_date} SUBJECT "оплата")',
            f'(SINCE {since_date} SUBJECT "списание")',
            f'(SINCE {since_date} SUBJECT "receipt")',
            f'(SINCE {since_date} SUBJECT "invoice")',
            f'(SINCE {since_date} SUBJECT "payment")',
        ]

        found_ids = set()
        for term in search_terms:
            _, ids = mail.search(None, term)
            if ids[0]:
                found_ids.update(ids[0].split())

        added = []
        skipped = []
        seen_services = set()

        for msg_id in list(found_ids)[:100]:  # не более 100 писем
            _, msg_data = mail.fetch(msg_id, '(RFC822)')
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            sender  = decode_header_value(msg.get('From', ''))
            subject = decode_header_value(msg.get('Subject', ''))
            date    = msg.get('Date', '')
            body    = get_email_text(msg)

            service = match_service(sender, subject)
            if not service:
                continue

            name, category, _ = service
            if name in seen_services:
                continue  # уже нашли эту подписку из другого письма
            seen_services.add(name)

            price   = extract_price(body) or extract_price(subject)
            pay_day = extract_pay_day(body, date)

            # Проверяем, нет ли уже такой подписки у пользователя
            existing = Subscription.query.filter_by(user_id=user.id, name=name).first()
            if existing:
                skipped.append(name)
                continue

            new_sub = Subscription(
                name=name,
                description=f'Импортировано из письма: {subject[:80]}',
                category=category,
                price=price if price else 0.0,
                pay_day=pay_day,
                user_id=user.id
            )
            db.session.add(new_sub)
            hist = History(
                action=f'Автоматически добавлена подписка {name} из почты',
                user_id=user.id
            )
            db.session.add(hist)
            added.append({'name': name, 'price': price, 'payDay': pay_day})

        db.session.commit()

        msg_parts = [f'Найдено и добавлено: {len(added)}']
        if skipped:
            msg_parts.append(f'уже есть: {len(skipped)}')

        return jsonify({
            'added': [a['name'] for a in added],
            'addedDetails': added,
            'skipped': skipped,
            'message': ', '.join(msg_parts)
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Ошибка при разборе почты: {str(e)}'}), 500
    finally:
        try:
            mail.logout()
        except Exception:
            pass

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=8080)
