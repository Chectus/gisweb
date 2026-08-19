import os
import requests
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, flash, Response, make_response
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import secrets
import smtplib
import random
import string
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Активируем чтение скрытого файла .env
load_dotenv()

app = Flask(__name__)

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

def send_2fa_email(to_email, code):
    """Отправка 6-значного кода подтверждения на почту геолога"""
    if not MAIL_USERNAME or not MAIL_PASSWORD:
        print("[-] Ошибка: Настройки почты не заданы в .env!")
        return False
        
    msg = MIMEMultipart('alternative')
    msg['Subject'] = 'Код подтверждения входа в Веб-ГИС'
    msg['From'] = f"Лаборатория ГИС <{MAIL_USERNAME}>"
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
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=3) # Время жизни сессии ровно 3 часа
app.config['SESSION_REFRESH_EACH_REQUEST'] = True             # Скользящее окно: каждый клик/запрос обновляет таймер

db = SQLAlchemy(app)

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
        return datetime.now() < (self.last_login + timedelta(days=3))

@app.before_request
def make_session_permanent():
    session.permanent = True

# --- РОУТЫ ---

@app.route('/api/<path:subpath>')
def proxy_nextgis(subpath):
    # 1. Жесткая защита: пропускаем только своих авторизованных геологов
    if 'user' not in session:
        return "Доступ запрещен", 403

    # 2. Формируем запрос к скрытому локальному NextGIS
    url = f"{NEXTGIS_LOCAL_URL}/api/{subpath}"
    
    # 3. Flask сам идет в NextGIS с правами из .env и прокидывает параметры от пользователя
    req = requests.get(url, params=request.args, auth=NEXTGIS_AUTH)
    
    # 4. Аккуратно передаем картинку (тайл) или GeoJSON обратно в браузер
    excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
    headers = [(name, value) for (name, value) in req.headers.items() if name.lower() not in excluded_headers]
    
    return Response(req.content, req.status_code, headers)

@app.route('/')
def index():
    if 'user' in session:
        return redirect(url_for('hub'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        # 1. Проверяем правильность логина и пароля
        if user and check_password_hash(user.password_hash, password):
            if not user.is_active():
                return render_template('login.html', error='Срок действия вашего аккаунта истёк.')
            
            # 2. Если у юзера НЕТ почты (общий аккаунт) -> пускаем сразу
            if not user.email:
                session['user'] = username
                session['is_admin'] = user.is_admin
                return redirect(url_for('hub'))
            
            # 3. Если почта ЕСТЬ -> ищем токен доверенного устройства в браузере
            device_token = request.cookies.get('trusted_device')
            if device_token:
                trusted_device = TrustedDevice.query.filter_by(device_token=device_token, user_id=user.id).first()
                # Если устройство найдено и таймер (3 дня) не истёк -> пускаем
                if trusted_device and trusted_device.is_valid():
                    # Обновляем таймер последнего входа
                    trusted_device.last_login = datetime.now()
                    db.session.commit()
                    
                    session['user'] = username
                    session['is_admin'] = user.is_admin
                    return redirect(url_for('hub'))
            
            # 4. Если устройства нет или оно просрочено -> Генерируем 2FA
            # Генерируем 6 случайных цифр
            code = ''.join(random.choices(string.digits, k=6))
            user.current_2fa_code = code
            db.session.commit()
            
            # ВОТ ТУТ МЫ СТРЕЛЯЕМ ИЗ НАШЕЙ ФУНКЦИИ!
            send_2fa_email(user.email, code)
            
            # Запоминаем во временную сессию, кто именно пытается войти
            session['pending_2fa_user_id'] = user.id
            return redirect(url_for('verify_2fa'))
            
        else:
            return render_template('login.html', error='Неверный логин или пароль')
            
    return render_template('login.html')


@app.route('/verify_2fa', methods=['GET', 'POST'])
def verify_2fa():
    # Если никто не пытается войти, выкидываем отсюда
    user_id = session.get('pending_2fa_user_id')
    if not user_id:
        return redirect(url_for('login'))
        
    user = User.query.get(user_id)
    
    if request.method == 'POST':
        entered_code = request.form.get('code')
        
        # Если код совпал с тем, что в базе
        if entered_code and entered_code == user.current_2fa_code:
            # Чистим временный код
            user.current_2fa_code = None
            
            # Генерируем длинный криптографический токен для устройства
            new_token = secrets.token_hex(32)
            new_device = TrustedDevice(user_id=user.id, device_token=new_token)
            db.session.add(new_device)
            db.session.commit()
            
            # Авторизуем в системе
            session['user'] = user.username
            session['is_admin'] = user.is_admin
            session.pop('pending_2fa_user_id', None) # Удаляем временную метку
            
            # Создаем ответ и кладем токен в куки браузера на 30 дней
            # (сама кука живет 30 дней, но база пустит только 3 дня)
            resp = make_response(redirect(url_for('hub')))
            resp.set_cookie('trusted_device', new_token, max_age=60*60*24*30, httponly=True)
            return resp
            
        else:
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
    session.pop('user', None)
    session.pop('is_admin', None) # Чистим админские права при выходе
    return redirect(url_for('login'))

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
    is_admin_flag = request.form.get('is_admin') == 'on'
    
    # Забираем почту из формы (если она есть)
    email = request.form.get('email')
    # Если поле было, но оно пустое (просто пробелы или ничего не ввели), делаем его None
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

    # Создаем юзера с учетом роли и почты
    new_user = User(
        username=username, 
        password_hash=hashed_pw, 
        expires_at=expires_at, 
        is_admin=is_admin_flag,
        email=email
    )
    
    db.session.add(new_user)
    db.session.commit()

    flash(f'Пользователь {username} успешно добавлен!', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if not session.get('is_admin'):
        return redirect(url_for('index'))

    user_to_delete = User.query.get(user_id)
    
    if user_to_delete:
        if user_to_delete.username == session['user']:
            flash('Вы не можете удалить сами себя!', 'error')
        else:
            db.session.delete(user_to_delete)
            db.session.commit()
            flash(f'Пользователь {user_to_delete.username} удален.', 'success')
    
    return redirect(url_for('admin_panel'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)