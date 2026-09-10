import os
import re
import json
import requests
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, flash, Response, make_response, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import secrets
import smtplib
import random
import string
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask_migrate import Migrate
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

# Активируем чтение скрытого файла .env
load_dotenv()

app = Flask(__name__)

# --- НОВОЕ: Настройка защиты от брутфорса ---
limiter = Limiter(
    get_remote_address,
    app=app,
    storage_uri="memory://"
)

# Достаем главный ключ из сейфа[cite: 4]
app.secret_key = os.environ.get('SECRET_KEY')
if not app.secret_key:
    raise ValueError("Не задан SECRET_KEY в переменных окружения!")

# НОВОЕ: Достаем учетку от NextGIS из сейфа
NEXTGIS_USER = os.environ.get('NEXTGIS_USER')
NEXTGIS_PASS = os.environ.get('NEXTGIS_PASS')
MAIL_SERVER = os.environ.get('MAIL_SERVER')
MAIL_PORT = int(os.environ.get('MAIL_PORT', 465))
MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')

def get_reset_serializer():
    return URLSafeTimedSerializer(app.secret_key)

def send_2fa_email(to_email, code):
    """Отправка 6-значного кода подтверждения на почту пользователя"""
    if not MAIL_USERNAME or not MAIL_PASSWORD:
        print("[-] Ошибка: Настройки почты не заданы в .env!")
        return False
        
    msg = MIMEMultipart('alternative')
    msg['Subject'] = 'Код подтверждения входа в Веб-ГИС'
    msg['From'] = MAIL_USERNAME
    msg['To'] = to_email

    # Красивое текстовое оформление письма
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 500px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
        <h2 style="color: #1a4d2e; text-align: center;">Безопасный вход</h2>
        <p>Здравствуйте! Зафиксирована попытка входа в систему геоинформационного хаба.</p>
        <p>Ваш одноразовый код для подтверждения устройства:</p>
        <div style="text-align: center; margin: 25px 0;">
            <span style="font-size: 32px; font-weight: bold; letter-spacing: 6px; color: #1a4d2e; background: #e8f5e9; padding: 10px 20px; border-radius: 6px;">{code}</span>
        </div>
        <p style="font-size: 12px; color: #777;">Если вы не пытались войти в систему, срочно обратитесь к администратору.</p>
    </div>
    """
    msg.attach(MIMEText(html_content, 'html'))

    try:
        with smtplib.SMTP_SSL(MAIL_SERVER, MAIL_PORT) as server:
            server.login(MAIL_USERNAME, MAIL_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"[-] Ошибка отправки письма: {e}")
        return False

if not NEXTGIS_USER or not NEXTGIS_PASS:
    raise ValueError("Не заданы логин или пароль NextGIS в переменных окружения (.env)!")

NEXTGIS_AUTH = (NEXTGIS_USER, NEXTGIS_PASS)
NEXTGIS_LOCAL_URL = "http://127.0.0.1:8081" # Порт докера NextGIS

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# --- НАСТРОЙКИ СЕССИЙ (ТАЙМ-АУТ 3 ЧАСА) ---
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=1) # Время жизни сессии ровно 1 часа
app.config['SESSION_REFRESH_EACH_REQUEST'] = True             # Скользящее окно: каждый клик/запрос обновляет таймер

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# --- МОДЕЛЬ ПОЛЬЗОВАТЕЛЯ В БАЗЕ ДАННЫХ ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=True) 
    is_admin = db.Column(db.Boolean, default=False)
    
    # --- НОВЫЕ ПОЛЯ ДЛЯ 2FA ---
    email = db.Column(db.String(120), nullable=True)          # Почта (если None — 2FA выключена)
    current_2fa_code = db.Column(db.String(6), nullable=True) # Сюда будем класть 6 цифр из письма
    
    # Связь базы данных: один пользователь -> много устройств
    # cascade="all, delete-orphan" значит, что если мы удалим геолога, все его устройства тоже удалятся
    trusted_devices = db.relationship('TrustedDevice', backref='user', lazy=True, cascade="all, delete-orphan")
    allowed_layers = db.Column(db.JSON, default="*")

    def is_active(self):
        if self.expires_at is None:
            return True
        return datetime.now() < self.expires_at

# --- НОВАЯ МОДЕЛЬ ДОВЕРЕННОГО УСТРОЙСТВА ---
class TrustedDevice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # Привязываем токен к конкретному ID пользователя
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    # Сам длинный криптографический токен, который ляжет в куки браузера
    device_token = db.Column(db.String(100), unique=True, nullable=False)
    # Дата последнего входа с этого компа
    last_login = db.Column(db.DateTime, default=datetime.now)

    # Метод, который проверяет тот самый тайм-аут в 3 дня (72 часа)
    def is_valid(self):
        return datetime.now() < (self.last_login + timedelta(days=1))

# --- НОВАЯ МОДЕЛЬ ДЛЯ ЛОГОВ ---
class ActionLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    # ondelete='SET NULL' значит, что если мы удалим юзера, его логи останутся, просто ID станет пустым
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True) 
    username = db.Column(db.String(50)) # Запоминаем логин текстом навечно
    action_type = db.Column(db.String(50)) # Категория (ВХОД, ОШИБКА, АДМИНКА)
    details = db.Column(db.String(255)) # Суть действия
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.String(255)) # Браузер и ОС

# --- ФУНКЦИЯ-ШПИОН ЗАПИСИ ЛОГОВ ---
def log_action(user_id, username, action_type, details):
    """Тихо записывает действие пользователя в базу"""
    # Достаем реальный IP (даже если сервер за прокси)
    ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
    # Достаем инфу о браузере
    user_agent = request.user_agent.string[:255] 
    
    log_entry = ActionLog(
        user_id=user_id,
        username=username,
        action_type=action_type,
        details=details,
        ip_address=ip_address,
        user_agent=user_agent
    )
    db.session.add(log_entry)
    db.session.commit()

@app.before_request
def make_session_permanent():
    session.permanent = True

@app.errorhandler(429)
def ratelimit_handler(e):
    ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
    print(f"[-] БЛОКИРОВКА БРУТФОРСА: IP {ip_address} забанен на 15 минут!")
    return render_template('login.html', error="Слишком много попыток входа. Ваш IP заблокирован на 15 минут!"), 429
# --- РОУТЫ ---

@app.route('/api/<path:subpath>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def proxy_nextgis(subpath):
    # 1. Базовая авторизация
    if 'user_id' not in session:
        return "Доступ запрещен", 403

    user = User.query.get(session['user_id'])
    
    # --- НАЧАЛО БЛОКА ФЕЙС-КОНТРОЛЯ И ШПИОНАЖА ---
    # Пытаемся найти ID ресурса (в пути или в аргументах)
    layer_id_str = None
    match = re.search(r'resource/(\d+)', subpath)
    if match:
        layer_id_str = match.group(1)
    elif request.args.get('resource'):
        layer_id_str = request.args.get('resource')

    if layer_id_str:
        try:
            layer_id = int(layer_id_str)
            
            # --- ЗЛОЙ ОХРАННИК (ДАТА-РУМЫ) ---
            if user.allowed_layers != "*":
                # Если список пустой или слоя там нет
                if not user.allowed_layers or layer_id not in user.allowed_layers:
                    log_action(user.id, user.username, 'ВТОРЖЕНИЕ', f'Попытка доступа к закрытому слою ID {layer_id}')
                    return "У вас нет доступа к этому дата-руму", 403

            # --- УМНЫЙ ШПИОНАЖ (только для разрешенных слоев) ---
            session_key = f'log_layer_{layer_id}'
            last_logged_str = session.get(session_key)
            
            should_log = False
            if not last_logged_str:
                should_log = True
            else:
                last_logged_time = datetime.fromisoformat(last_logged_str)
                if datetime.now() > last_logged_time + timedelta(minutes=5):
                    should_log = True
                    
            if should_log:
                log_action(user.id, user.username, 'КАРТА', f'Работа со слоем/ресурсом #{layer_id}')
                session[session_key] = datetime.now().isoformat()
                
        except ValueError:
            pass # Если ID оказался не числом, просто пропускаем
    # --- КОНЕЦ БЛОКА ФЕЙС-КОНТРОЛЯ И ШПИОНАЖА ---

    # 2. Формируем запрос к скрытому локальному NextGIS
    url = f"{NEXTGIS_LOCAL_URL}/api/{subpath}"
    
    # 3. Flask сам идет в NextGIS (поддерживаем любые методы GET/POST)
    req = requests.request(
        method=request.method,
        url=url, 
        params=request.args,
        data=request.get_data(), 
        auth=NEXTGIS_AUTH
    )
    
    # 4. Аккуратно передаем ответ обратно в браузер
    excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
    headers = [(name, value) for (name, value) in req.headers.items() if name.lower() not in excluded_headers]
    
    return Response(req.content, req.status_code, headers)

@app.route('/')
def index():
    if 'user' in session:
        return redirect(url_for('hub'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per 15 minute", methods=["POST"]) # НОВОЕ: Блокируем IP на 15 минут после 5 попыток входа
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            if not user.is_active():
                log_action(user.id, user.username, 'ОШИБКА_ВХОДА', 'Попытка входа с истекшим сроком')
                return render_template('login.html', error='Срок действия вашего аккаунта истёк.')
            
            # 1. Логин без 2FA (общий аккаунт)
            if not user.email:
                log_action(user.id, user.username, 'ВХОД', 'Успешный вход (Без 2FA)')
                session['user'] = username
                session['user_id'] = user.id
                session['is_admin'] = user.is_admin
                return redirect(url_for('hub'))
            
            # 2. Логин по токену доверенного устройства
            device_token = request.cookies.get('trusted_device')
            if device_token:
                trusted_device = TrustedDevice.query.filter_by(device_token=device_token, user_id=user.id).first()
                if trusted_device and trusted_device.is_valid():
                    trusted_device.last_login = datetime.now()
                    db.session.commit()
                    
                    log_action(user.id, user.username, 'ВХОД', 'Успешный вход (По токену устройства)')
                    session['user'] = username
                    session['user_id'] = user.id
                    session['is_admin'] = user.is_admin
                    return redirect(url_for('hub'))
            
            # 3. Отправка 2FA
            code = ''.join(random.choices(string.digits, k=6))
            user.current_2fa_code = code
            db.session.commit()
            
            send_2fa_email(user.email, code)
            log_action(user.id, user.username, '2FA_ЗАПРОС', 'Отправлен код подтверждения на почту')
            
            session['pending_2fa_user_id'] = user.id
            return redirect(url_for('verify_2fa'))
            
        else:
            user_id = user.id if user else None
            log_action(user_id, username, 'ОШИБКА_ВХОДА', 'Неверный логин или пароль')
            return render_template('login.html', error='Неверный логин или пароль')
            
    return render_template('login.html')

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        
        # Ищем пользователя ТОЛЬКО по почте
        user = User.query.filter_by(email=email).first()
        
        if user:
            # Генерируем безопасный токен
            s = get_reset_serializer()
            token = s.dumps(user.email, salt='password-reset-salt')
            
            # Создаем полную ссылку (с твоим доменом)
            reset_link = url_for('reset_password', token=token, _external=True)
            
            # Отправляем письмо
            send_reset_email(user.email, reset_link)
            log_action(user.id, user.username, 'ЗАПРОС_СБРОСА', 'Отправлена ссылка для сброса пароля')
        
        # ВАЖНО: Мы всегда выводим одно и то же сообщение, даже если почты нет в базе.
        # Это защита от хакеров, чтобы они не могли проверять, какие email зарегистрированы.
        return render_template('forgot_password.html', 
                               message='Если такой email есть в системе, мы отправили на него ссылку для сброса пароля.')
        
    return render_template('forgot_password.html')

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    s = get_reset_serializer()
    try:
        # Проверяем токен. max_age=900 означает, что ссылка живет ровно 15 минут
        email = s.loads(token, salt='password-reset-salt', max_age=900)
    except SignatureExpired:
        return render_template('reset_password.html', error='Ссылка устарела. Запросите новую.')
    except BadSignature:
        return render_template('reset_password.html', error='Неверная ссылка.')
        
    user = User.query.filter_by(email=email).first()
    if not user:
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        new_password = request.form.get('password')
        
        # Хешируем новый пароль и сохраняем
        user.password_hash = generate_password_hash(new_password)
        
        # Очищаем временные коды (на всякий случай)
        user.current_2fa_code = None
        db.session.commit()
        
        log_action(user.id, user.username, 'СБРОС_ПАРОЛЯ', 'Пароль успешно изменен')
        
        # Перекидываем на логин
        return render_template('login.html', message='Пароль успешно изменен! Теперь вы можете войти.')
        
    return render_template('reset_password.html', token=token)

@app.route('/profile')
def profile():
    """Просто отрисовка профиля со всей инфой и таймером"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    return render_template('profile.html', user=user)

@app.route('/logout_devices', methods=['POST'])
def logout_devices():
    """Кнопка 'Выйти со всех других устройств'"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    # Сносим все сохраненные сессии этого юзера
    TrustedDevice.query.filter_by(user_id=session['user_id']).delete()
    db.session.commit()
    
    log_action(session['user_id'], session.get('user'), 'БЕЗОПАСНОСТЬ', 'Завершены все другие сеансы')
    
    user = User.query.get(session['user_id'])
    return render_template('profile.html', user=user, message='Все другие устройства успешно отключены!')

# --- УМНАЯ СМЕНА ПАРОЛЯ В ПРОФИЛЕ ---

@app.route('/change_password_request', methods=['POST'])
def change_password_request():
    """Шаг 1: Проверка старого пароля и отправка кода (если есть почта)"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    user = User.query.get(session['user_id'])
    old_password = request.form.get('old_password')
    new_password = request.form.get('new_password')
    
    # Проверяем старый пароль
    if not check_password_hash(user.password_hash, old_password):
        return render_template('profile.html', user=user, error_pwd='Неверный текущий пароль!')
        
    # Если у юзера нет почты (общий аккаунт) - меняем сразу
    if not user.email:
        user.password_hash = generate_password_hash(new_password)
        db.session.commit()
        log_action(user.id, user.username, 'СМЕНА_ПАРОЛЯ', 'Пароль изменен (без 2FA)')
        return render_template('profile.html', user=user, msg_pwd='Пароль успешно изменен!')
        
    # Если есть почта - генерируем код 2FA
    code = ''.join(random.choices(string.digits, k=6))
    user.current_2fa_code = code
    db.session.commit()
    
    send_2fa_email(user.email, code)
    
    # Временно сохраняем новый пароль в сессию, чтобы применить после ввода кода
    session['pending_new_password'] = new_password
    
    # Отдаем профиль обратно, но с флагом show_pwd_2fa=True, чтобы фронтенд показал поле для кода
    return render_template('profile.html', user=user, show_pwd_2fa=True, msg_pwd='Код подтверждения отправлен на почту!')

@app.route('/change_password_confirm', methods=['POST'])
def change_password_confirm():
    """Шаг 2: Проверка кода и финальное сохранение пароля"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    user = User.query.get(session['user_id'])
    code = request.form.get('code')
    pending_password = session.get('pending_new_password')
    
    if not pending_password:
         return render_template('profile.html', user=user, error_pwd='Что-то пошло не так. Попробуйте снова.')
         
    if user.current_2fa_code and user.current_2fa_code == code:
        # Код верный! Сохраняем пароль
        user.password_hash = generate_password_hash(pending_password)
        user.current_2fa_code = None
        db.session.commit()
        
        session.pop('pending_new_password', None)
        
        log_action(user.id, user.username, 'СМЕНА_ПАРОЛЯ', 'Пароль успешно изменен с подтверждением 2FA')
        return render_template('profile.html', user=user, msg_pwd='Пароль успешно изменен!')
    else:
        # Код неверный, возвращаем обратно на форму ввода кода
        return render_template('profile.html', user=user, show_pwd_2fa=True, error_pwd='Неверный код подтверждения!')

@app.route('/verify_2fa', methods=['GET', 'POST'])
def verify_2fa():
    user_id = session.get('pending_2fa_user_id')
    if not user_id:
        return redirect(url_for('login'))
        
    user = User.query.get(user_id)
    
    if request.method == 'POST':
        entered_code = request.form.get('code')
        
        if entered_code and entered_code == user.current_2fa_code:
            user.current_2fa_code = None
            
            new_token = secrets.token_hex(32)
            new_device = TrustedDevice(user_id=user.id, device_token=new_token)
            db.session.add(new_device)
            db.session.commit()
            
            session['user'] = user.username
            session['user_id'] = user.id # НОВОЕ: Запоминаем ID
            session['is_admin'] = user.is_admin
            session.pop('pending_2fa_user_id', None)
            
            log_action(user.id, user.username, 'ВХОД', 'Успешный вход (Подтвержден код 2FA)')
            
            resp = make_response(redirect(url_for('hub')))
            resp.set_cookie('trusted_device', new_token, max_age=60*60*24*1, httponly=True)
            return resp
            
        else:
            log_action(user.id, user.username, 'ОШИБКА_2FA', 'Введен неверный код подтверждения')
            return render_template('verify_2fa.html', error='Неверный код подтверждения')
            
    return render_template('verify_2fa.html', email=user.email)

@app.route('/hub')
def hub():
    if 'user' not in session:
        return redirect(url_for('login'))
    # Передаем is_admin в шаблон, чтобы скрыть/показать кнопку админки
    return render_template('hub.html', username=session['user'], is_admin=session.get('is_admin'))

@app.route('/map')
def map_page():
    if 'user' not in session:
        return redirect(url_for('login'))
    # НОВОЕ: Передаем имя пользователя в шаблон карты, как просили в ТЗ
    return render_template('map.html', username=session.get('user'))

@app.route('/docs')
def docs():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('docs.html')

@app.route('/logout')
def logout():
    username = session.get('user')
    user_id = session.get('user_id')
    
    if username:
        log_action(user_id, username, 'ВЫХОД', 'Пользователь завершил сессию')
        
    session.clear() # Очищаем всю сессию махом
    
    # Жестко убиваем куку доверенного устройства, чтобы выкинуло наверняка
    resp = make_response(redirect(url_for('login')))
    resp.set_cookie('trusted_device', '', expires=0) 
    return resp

@app.route('/admin')
def admin_panel():
    # НОВОЕ: Защита маршрута через флаг сессии
    if not session.get('is_admin'):
        flash('Доступ запрещен. Требуются права администратора.', 'error')
        return redirect(url_for('index'))
    
    all_users = User.query.all()
    return render_template('admin.html', users=all_users)

@app.route('/admin/add_user', methods=['POST'])
def add_user():
    if not session.get('is_admin'):
        return redirect(url_for('index'))

    username = request.form.get('username')
    password = request.form.get('password')
    expire_days = request.form.get('expire_days')
    is_admin_flag = str(request.form.get('is_admin')) == '1'
    
    email = request.form.get('email')
    if not email or email.strip() == '':
        email = None

    existing_user = User.query.filter_by(username=username).first()
    if existing_user:
        flash(f'Пользователь {username} уже существует!', 'error')
        return redirect(url_for('admin_panel'))

    hashed_pw = generate_password_hash(password)

    expires_at = None
    if expire_days and expire_days.isdigit():
        expires_at = datetime.now() + timedelta(days=int(expire_days))

    new_user = User(
        username=username, 
        password_hash=hashed_pw, 
        expires_at=expires_at, 
        is_admin=is_admin_flag,
        email=email
    )
    
    db.session.add(new_user)
    db.session.commit()

    # --- ШПИОНАЖ ЗА СОЗДАНИЕМ ---
    current_admin = session.get('user')
    admin_id = session.get('user_id')
    role_text = "Админ" if is_admin_flag else "Гость"
    log_action(admin_id, current_admin, 'АДМИНКА', f'Создан новый {role_text}: {username}')

    flash(f'Пользователь {username} успешно добавлен!', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/admin/users')
def admin_dashboard():
    """Страница управления пользователями (только для админов)"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    current_user = User.query.get(session['user_id'])
    if not current_user.is_admin:
        return "Доступ запрещен. Вы не администратор.", 403
        
    # Достаем всех юзеров, чтобы вывести их в таблицу
    all_users = User.query.all()
    return render_template('admin.html', users=all_users)

@app.route('/admin/api/create_user', methods=['POST'])
def api_create_user():
    """API-эндпоинт для создания геолога с правами на слои"""
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Не авторизован'}), 401
        
    current_user = User.query.get(session['user_id'])
    if not current_user.is_admin:
        return jsonify({'status': 'error', 'message': 'Нет прав'}), 403

    # Получаем данные в формате JSON от фронтенда
    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': 'Пустой запрос'}), 400

    username = data.get('username')
    email = data.get('email')
    # Получаем тот самый массив ID слоев, например: [324, 325, 330]
    allowed_layers = data.get('allowed_layers', []) 
    
    if User.query.filter_by(username=username).first():
        return jsonify({'status': 'error', 'message': 'Пользователь с таким логином уже существует'}), 400

    # Генерируем случайный пароль для нового геолога (8 символов)
    temp_password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    
    # Создаем юзера
    new_user = User(
        username=username,
        email=email,
        password_hash=generate_password_hash(temp_password),
        is_admin=False,
        allowed_layers=allowed_layers # Записываем выданные права!
    )
    
    db.session.add(new_user)
    db.session.commit()
    
    log_action(current_user.id, current_user.username, 'АДМИН', f'Создан новый пользователь: {username}')

    # Если указана почта - отправляем пароль
    if email:
        subject = "Доступ к WebGIS Лаборатории"
        body = f"Здравствуйте!\n\nВам открыт доступ к системе.\nВаш логин: {username}\nВаш временный пароль: {temp_password}\n\nОбязательно смените пароль в Личном кабинете после входа!"
        # Тут вызываем твою функцию отправки почты
        # send_email_custom(email, subject, body) 
        pass 

    return jsonify({
        'status': 'success', 
        'message': f'Пользователь {username} успешно создан!',
        'temp_password': temp_password # Возвращаем пароль, чтобы админ мог скопировать его, если почты нет
    })

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if not session.get('is_admin'):
        return redirect(url_for('index'))

    user_to_delete = User.query.get(user_id)
    
    if user_to_delete:
        if user_to_delete.username == session['user']:
            flash('Вы не можете удалить сами себя!', 'error')
        else:
            # --- ШПИОНАЖ ЗА УДАЛЕНИЕМ ---
            log_action(session.get('user_id'), session.get('user'), 'АДМИНКА', f'Удален пользователь: {user_to_delete.username}')
            
            db.session.delete(user_to_delete)
            db.session.commit()
            flash(f'Пользователь {user_to_delete.username} удален.', 'success')
    
    return redirect(url_for('admin_panel'))

@app.route('/admin/api/logs/<username>', methods=['GET'])
def get_user_logs(username):
    # Защита: логи может смотреть только админ
    if not session.get('is_admin'):
        return jsonify({'error': 'Доступ запрещен'}), 403
        
    # Ищем логи этого пользователя, сортируем от новых к старым, берем последние 50 штук
    logs = ActionLog.query.filter_by(username=username).order_by(ActionLog.timestamp.desc()).limit(50).all()
    
    # Упаковываем в удобный для фронтенда формат (массив словарей)
    logs_data = []
    for log in logs:
        logs_data.append({
            'timestamp': log.timestamp.strftime('%d.%m.%Y %H:%M:%S'),
            'action_type': log.action_type,
            'details': log.details,
            'ip_address': log.ip_address,
            # Отрезаем кусок юзер-агента, чтобы не был слишком длинным
            'user_agent': log.user_agent[:60] + '...' if log.user_agent and len(log.user_agent) > 60 else log.user_agent
        })
        
    return jsonify(logs_data)

@app.route('/api/layers_config')
def get_layers_config():
    """Отдает структуру слоев для отрисовки дерева на фронтенде"""
    # Если на сервере юзер не авторизован - нечего ему смотреть на структуру
    if 'user_id' not in session:
         return jsonify({"error": "Unauthorized"}), 401
         
    config_path = os.path.join(app.root_path, 'layers_config.json')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": f"Ошибка чтения конфига: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)