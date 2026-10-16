import os
import re
import io
import json
import pdfkit
import requests
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, flash, Response, make_response, jsonify, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
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
from sqlalchemy.orm.attributes import flag_modified
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

# Активируем чтение скрытого файла .env
load_dotenv()

app = Flask(__name__)

# Папка для хранения прикрепленных файлов к задачам CRM
TASKS_UPLOAD_FOLDER = os.path.join(app.root_path, 'uploads', 'tasks')
os.makedirs(TASKS_UPLOAD_FOLDER, exist_ok=True)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # Лимит файла: 50 МБ

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
    <div style="font-family: 'Helvetica Neue', Arial, sans-serif; max-width: 500px; margin: 0 auto; padding: 30px; border: 1px solid #e2e8f0; border-radius: 12px; background-color: #ffffff; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);">
        <h2 style="color: #0f172a; text-align: center; margin-bottom: 20px; font-weight: 700;">Авторизация в системе</h2>
        <p style="color: #475569; font-size: 15px; line-height: 1.6;">Уважаемый пользователь,</p>
        <p style="color: #475569; font-size: 15px; line-height: 1.6;">Зафиксирована попытка входа в закрытый контур Веб-ГИС «Недра Забайкальского края». Ваш одноразовый код для подтверждения сессии:</p>
        <div style="text-align: center; margin: 35px 0;">
            <span style="font-size: 32px; font-weight: 800; letter-spacing: 8px; color: #1e3a8a; background: #f8fafc; padding: 15px 25px; border-radius: 8px; border-left: 4px solid #d97706;">{code}</span>
        </div>
        <p style="font-size: 13px; color: #94a3b8; border-top: 1px solid #e2e8f0; padding-top: 20px; margin-top: 30px;">Если вы не инициировали этот запрос, проигнорируйте письмо или обратитесь в службу безопасности лаборатории.</p>
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

def send_reset_email(to_email, reset_link):
    """Отправка ссылки для сброса пароля (забыли пароль)"""
    if not MAIL_USERNAME or not MAIL_PASSWORD:
        return False
        
    msg = MIMEMultipart('alternative')
    msg['Subject'] = 'Восстановление пароля Веб-ГИС'
    msg['From'] = MAIL_USERNAME
    msg['To'] = to_email

    html_content = f"""
    <div style="font-family: 'Helvetica Neue', Arial, sans-serif; max-width: 500px; margin: 0 auto; padding: 30px; border: 1px solid #e2e8f0; border-radius: 12px; background-color: #ffffff; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);">
        <h2 style="color: #0f172a; text-align: center; margin-bottom: 20px; font-weight: 700;">Восстановление доступа</h2>
        <p style="color: #475569; font-size: 15px; line-height: 1.6;">Уважаемый пользователь,</p>
        <p style="color: #475569; font-size: 15px; line-height: 1.6;">Поступил автоматический запрос на сброс пароля от вашей учетной записи на портале Веб-ГИС. Для генерации нового пароля нажмите на кнопку ниже:</p>
        <div style="text-align: center; margin: 35px 0;">
            <a href="{reset_link}" style="background-color: #1e3a8a; color: #ffffff; padding: 14px 28px; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 15px; display: inline-block;">Сбросить пароль</a>
        </div>
        <p style="color: #dc2626; font-size: 13px; text-align: center; font-weight: 500;">Ссылка действительна в течение 15 минут.</p>
        <p style="font-size: 13px; color: #94a3b8; border-top: 1px solid #e2e8f0; padding-top: 20px; margin-top: 30px;">Если запрос отправлен по ошибке, никаких действий не требуется.</p>
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


def send_profile_code_email(to_email, code):
    """Отправка кода подтверждения при смене пароля из профиля"""
    if not MAIL_USERNAME or not MAIL_PASSWORD:
        return False
        
    msg = MIMEMultipart('alternative')
    msg['Subject'] = 'Смена пароля в Веб-ГИС'
    msg['From'] = MAIL_USERNAME
    msg['To'] = to_email

    html_content = f"""
    <div style="font-family: 'Helvetica Neue', Arial, sans-serif; max-width: 500px; margin: 0 auto; padding: 30px; border: 1px solid #e2e8f0; border-radius: 12px; background-color: #ffffff; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);">
        <h2 style="color: #0f172a; text-align: center; margin-bottom: 20px; font-weight: 700;">Изменение учетных данных</h2>
        <p style="color: #475569; font-size: 15px; line-height: 1.6;">Уважаемый пользователь,</p>
        <p style="color: #475569; font-size: 15px; line-height: 1.6;">Вы запросили изменение пароля. Для подтверждения операции и внесения изменений в базу данных, пожалуйста, используйте следующий код:</p>
        <div style="text-align: center; margin: 35px 0;">
            <span style="font-size: 32px; font-weight: 800; letter-spacing: 8px; color: #1e3a8a; background: #f8fafc; padding: 15px 25px; border-radius: 8px; border-left: 4px solid #d97706;">{code}</span>
        </div>
        <p style="font-size: 13px; color: #94a3b8; border-top: 1px solid #e2e8f0; padding-top: 20px; margin-top: 30px;">Внимание: никому не передавайте этот код. Администраторы портала никогда не запрашивают пароли.</p>
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

def send_bruteforce_alert_email(to_email, ip_address):
    """Отправка алерта о попытке взлома аккаунта"""
    if not MAIL_USERNAME or not MAIL_PASSWORD:
        return False
        
    msg = MIMEMultipart('alternative')
    msg['Subject'] = '⚠️ Внимание: Попытка взлома аккаунта!'
    msg['From'] = MAIL_USERNAME
    msg['To'] = to_email

    html_content = f"""
    <div style="font-family: 'Helvetica Neue', Arial, sans-serif; max-width: 500px; margin: 0 auto; padding: 30px; border: 1px solid #fecaca; border-radius: 12px; background-color: #ffffff; box-shadow: 0 4px 6px -1px rgba(220, 38, 38, 0.1);">
        <div style="text-align: center; margin-bottom: 15px;">
            <span style="background-color: #fee2e2; color: #991b1b; padding: 6px 12px; border-radius: 20px; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px;">Security Alert</span>
        </div>
        <h2 style="color: #991b1b; text-align: center; margin-bottom: 20px; font-weight: 700;">Учетная запись заблокирована</h2>
        <p style="color: #475569; font-size: 15px; line-height: 1.6;">Зафиксирована серия неудачных попыток подбора пароля к вашему аккаунту.</p>
        <p style="color: #475569; font-size: 15px; line-height: 1.6;">В целях защиты геоданных алгоритмы безопасности <b>временно заблокировали</b> доступ к логину на 15 минут.</p>
        <div style="text-align: center; margin: 30px 0;">
            <span style="font-size: 14px; font-weight: 600; color: #991b1b; background: #f8fafc; padding: 12px 20px; border-radius: 6px; border: 1px solid #fecaca;">IP-адрес инициатора: {ip_address}</span>
        </div>
        <p style="font-size: 13px; color: #94a3b8; border-top: 1px solid #e2e8f0; padding-top: 20px; margin-top: 30px;">Рекомендуем воспользоваться функцией восстановления пароля после снятия блокировки.</p>
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

def get_nextgis_objects_data(layer_id, object_ids):
    """
    Функция стучится в локальный NextGIS и достает атрибуты конкретных объектов
    """
    objects_data = []
    
    # Пробегаемся по всем ID, которые прислал фронтенд
    for obj_id in object_ids:
        # Стандартный эндпоинт NextGIS для получения конкретного объекта (feature)
        url = f"{NEXTGIS_LOCAL_URL}/api/resource/{layer_id}/feature/{obj_id}"
        
        try:
            # Делаем запрос к NextGIS, используя твою учетку из .env
            response = requests.get(url, auth=NEXTGIS_AUTH)
            
            if response.status_code == 200:
                data = response.json()
                # NextGIS возвращает много служебной инфы, но сами атрибуты (колонки из таблицы) 
                # всегда лежат внутри ключа 'fields'. Берем только их!
                fields = data.get('fields', {})
                objects_data.append(fields)
            else:
                print(f"[-] Ошибка NextGIS при запросе объекта {obj_id}: статус {response.status_code}")
                
        except Exception as e:
            print(f"[-] Ошибка связи с локальным NextGIS: {e}")
            
    return objects_data

if not NEXTGIS_USER or not NEXTGIS_PASS:
    raise ValueError("Не заданы логин или пароль NextGIS в переменных окружения (.env)!")

NEXTGIS_AUTH = (NEXTGIS_USER, NEXTGIS_PASS)
NEXTGIS_LOCAL_URL = "http://127.0.0.1:8081" # Порт докера NextGIS

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'postgresql://geo_user:password@localhost:5432/geo_db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# --- НАСТРОЙКИ СЕССИЙ (ТАЙМ-АУТ 3 ЧАСА) ---
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=1) # Время жизни сессии ровно 1 часа
app.config['SESSION_REFRESH_EACH_REQUEST'] = True             # Скользящее окно: каждый клик/запрос обновляет таймер

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# 1. СПРАВОЧНИК РОЛЕЙ
class Role(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False) # 'admin', 'worker', 'viewer'
    can_assign_tasks = db.Column(db.Boolean, default=False)      # Права начальника/зама
    can_receive_tasks = db.Column(db.Boolean, default=False)     # Права лаборантов
    
    users = db.relationship('User', backref='role', lazy=True)

# 2. ТАБЛИЦА ДОСТУПОВ К СЛОЯМ
class UserLayer(db.Model):
    __tablename__ = 'user_layers'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    layer_id = db.Column(db.Integer, nullable=False) # Просто число из layers_config.json

# 3. ПОЛЬЗОВАТЕЛИ
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(120), nullable=True)
    
    # Новые поля для отчетов и связей
    full_name = db.Column(db.String(150), nullable=True) 
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False)
    has_all_layers = db.Column(db.Boolean, default=True) # Замена JSON "*"
    
    # Старые поля (оставляем для безопасности и 2FA)
    expires_at = db.Column(db.DateTime, nullable=True) 
    current_2fa_code = db.Column(db.String(6), nullable=True)
    onboarding_state = db.Column(db.JSON, default=dict)
    
    # Связи (Relationships)
    specific_layers = db.relationship('UserLayer', backref='user', cascade="all, delete-orphan")
    trusted_devices = db.relationship('TrustedDevice', backref='user', lazy=True, cascade="all, delete-orphan")
    tasks_assigned = db.relationship('Task', foreign_keys='Task.assignee_id', backref='assignee', lazy=True)
    tasks_authored = db.relationship('Task', foreign_keys='Task.author_id', backref='author', lazy=True)

    # --- МАГИЯ ОБРАТНОЙ СОВМЕСТИМОСТИ И ПРАВ CRM ---
    @property
    def is_admin(self):
        """Чтобы старый код (session['is_admin'] = user.is_admin) не сломался"""
        return self.role.name == 'admin' if self.role else False

    @property
    def role_name(self):
        return self.role.name if self.role else 'viewer'

    @property
    def can_assign(self):
        """Может ли пользователь раздавать и проверять задачи (Начальник/Зам)"""
        return self.is_admin or (self.role is not None and self.role.can_assign_tasks)

    @property
    def can_receive(self):
        """Может ли пользователь получать задачи в работу (Лаборант/Геолог)"""
        return self.role is not None and (self.role.name == 'worker' or self.role.can_receive_tasks)

    @property
    def allowed_layers(self):
        """Чтобы прокси-охранник и фронтенд Светы получали привычный формат '*' или [320, 321]"""
        if self.has_all_layers:
            return "*"
        return [link.layer_id for link in self.specific_layers]

    def is_active(self):
        if self.expires_at is None:
            return True
        return datetime.now() < self.expires_at


# 4. ЗАДАЧИ (Модуль CRM)
class Task(db.Model):
    __tablename__ = 'tasks'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    
    # Статус: 'pending', 'in_progress', 'review', 'completed'
    status = db.Column(db.String(50), default='pending')
    score = db.Column(db.Integer, nullable=True) # Оценка начальника от 1 до 10
    
    employee_report = db.Column(db.Text, nullable=True)
    attachment_path = db.Column(db.String(255), nullable=True)
    
    # Строгий тайминг для формирования рабочих карт
    created_at = db.Column(db.DateTime, default=datetime.now)
    deadline = db.Column(db.DateTime, nullable=True)
    accepted_at = db.Column(db.DateTime, nullable=True)
    submitted_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    
    assignee_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    @property
    def is_overdue(self):
        """Проверка: просрочена ли задача сейчас или была ли сдана с опозданием"""
        if not self.deadline:
            return False
        if self.status == 'completed':
            check_time = self.submitted_at or self.completed_at or datetime.now()
            return check_time > self.deadline
        return datetime.now() > self.deadline

    def to_dict(self):
        """Упаковка задачи со всеми датами и связями в JSON для фронтенда"""
        fmt = '%d.%m.%Y %H:%M'
        iso_fmt = '%Y-%m-%dT%H:%M'
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description or '',
            'status': self.status,
            'is_overdue': self.is_overdue,
            'score': self.score,
            'employee_report': self.employee_report or '',
            'has_attachment': bool(self.attachment_path),
            'attachment_name': os.path.basename(self.attachment_path) if self.attachment_path else None,
            'attachment_url': url_for('download_task_attachment', task_id=self.id) if self.attachment_path else None,
            
            # Красивые даты для отображения в карточках
            'created_at': self.created_at.strftime(fmt) if self.created_at else None,
            'deadline': self.deadline.strftime(fmt) if self.deadline else None,
            'accepted_at': self.accepted_at.strftime(fmt) if self.accepted_at else None,
            'submitted_at': self.submitted_at.strftime(fmt) if self.submitted_at else None,
            'completed_at': self.completed_at.strftime(fmt) if self.completed_at else None,
            
            # Сырая дата дедлайна для подстановки в HTML <input type="datetime-local">
            'deadline_iso': self.deadline.strftime(iso_fmt) if self.deadline else None,
            
            # Информация об исполнителе и авторе
            'assignee_id': self.assignee_id,
            'assignee_username': self.assignee.username if self.assignee else 'Удален',
            'assignee_full_name': (self.assignee.full_name or self.assignee.username) if self.assignee else 'Удален',
            'author_id': self.author_id,
            'author_username': self.author.username if self.author else 'Система',
            'author_full_name': (self.author.full_name or self.author.username) if self.author else 'Система'
        }

# 5. ДОВЕРЕННЫЕ УСТРОЙСТВА (Оставляем без изменений!)
class TrustedDevice(db.Model):
    __tablename__ = 'trusted_devices'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    device_token = db.Column(db.String(100), unique=True, nullable=False)
    last_login = db.Column(db.DateTime, default=datetime.now)

    def is_valid(self):
        return datetime.now() < (self.last_login + timedelta(days=1))

# 6. ЛОГИ АУДИТА (Оставляем без изменений!)
class ActionLog(db.Model):
    __tablename__ = 'action_logs'
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True) 
    username = db.Column(db.String(50)) 
    action_type = db.Column(db.String(50)) 
    details = db.Column(db.String(255)) 
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.String(255))

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
    
    # --- НАЧАЛО БЛОКА ФЕЙС-КОНТРОЛЯ ---
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

            # Весь код умного шпионажа за обычными кликами по карте отсюда удален!
                
        except ValueError:
            pass # Если ID оказался не числом, просто пропускаем
    # --- КОНЕЦ БЛОКА ФЕЙС-КОНТРОЛЯ ---

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
def login():
    if request.method == 'POST':
        # Сначала получаем логин и пароль из формы
        username = request.form.get('username')
        password = request.form.get('password')
        
        # --- УМНАЯ ЗАЩИТА 2.0 (АНТИ-VPN) ---
        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
        time_limit = datetime.now() - timedelta(minutes=15)
        
        # 1. Проверяем атаки с одного IP
        failed_by_ip = ActionLog.query.filter(
            ActionLog.ip_address == ip_address,
            ActionLog.action_type == 'ОШИБКА_ВХОДА',
            ActionLog.timestamp >= time_limit
        ).count()
        
        # 2. Проверяем атаки на конкретный логин (защита от VPN-ротации)
        failed_by_user = 0
        if username:
            failed_by_user = ActionLog.query.filter(
                ActionLog.username == username,
                ActionLog.action_type == 'ОШИБКА_ВХОДА',
                ActionLog.timestamp >= time_limit
            ).count()
        
        # Если пробили лимит по IP
        if failed_by_ip >= 5:
            return render_template('login.html', error='Слишком много попыток. Ваш IP заблокирован на 15 минут!'), 429
            
        # Если пробили лимит по Логину (заморозка аккаунта)
        # ... (тут проверка failed_by_ip) ...
            
        # Если пробили лимит по Логину (заморозка аккаунта)
        if failed_by_user >= 5:
            # Отправляем алерт ТОЛЬКО один раз - ровно на 5-ю попытку (чтобы не заспамить почту)
            if failed_by_user == 5:
                target_user = User.query.filter_by(username=username).first()
                if target_user and target_user.email:
                    send_bruteforce_alert_email(target_user.email, ip_address)
            
            return render_template('login.html', error=f'Попытки входа для {username} временно заблокированы в целях безопасности.'), 429
            
        # Если защиты не сработали, идем дальше по старому коду:
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
    
    send_profile_code_email(user.email, code)
    
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
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # Достаем юзера из базы
    user = db.session.get(User, session['user_id'])
    
    # --- НОВОЕ: Проверка статуса обучалки для карты ---
    state_dict = user.onboarding_state if user.onboarding_state else {}
    # Ищем ключ 'map'. Если его еще нет, возвращаем False (обучалку не видел)
    has_seen_tutorial = state_dict.get('map', False)
    
    # Передаем в шаблон логин, JSON слоев и статус обучалки
    return render_template('map.html', 
                           username=user.username,
                           allowed_layers=json.dumps(user.allowed_layers),
                           has_seen_tutorial=json.dumps(has_seen_tutorial))

@app.route('/docs')
def docs():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('docs.html')

@app.route('/api/report/generate', methods=['POST'])
def generate_pdf_report():
    if 'user_id' not in session:
        return jsonify({'error': 'Не авторизован'}), 401
        
    data = request.get_json()
    layer_id = data.get('layer_id')
    object_ids = data.get('object_ids', []) # Это массив, например [45] или [45, 48]
    
    if not layer_id or not object_ids:
        return jsonify({'error': 'Нет данных для отчета'}), 400
        
    # --- ЗЛОЙ ОХРАННИК ---
    # Проверяем, есть ли у юзера доступ к этому слою (твоя защита из proxy_nextgis)
    user = db.session.get(User, session['user_id'])
    if user.allowed_layers != "*":
        if not user.allowed_layers or int(layer_id) not in user.allowed_layers:
            return jsonify({'error': 'Нет доступа к слою'}), 403

    # 1. Идем в NextGIS (или твою БД) и достаем атрибуты по этим object_ids
    # (Здесь будет твой код запроса к слою, я напишу заглушку)
    objects_data = get_nextgis_objects_data(layer_id, object_ids) 
    
    # 2. Рендерим HTML-шаблон, передавая туда данные
    # Если len(object_ids) == 1, Светин шаблон нарисует соло-таблицу.
    # Если len(object_ids) > 1, шаблон нарисует таблицу сравнения колонка к колонке.
    html_content = render_template('pdf_report_template.html', 
                                   objects=objects_data, 
                                   layer_id=layer_id)
                                   
    # 3. Настройки для PDF (А4, без отступов, UTF-8)
    options = {
        'page-size': 'A4',
        'margin-top': '10mm',
        'margin-right': '10mm',
        'margin-bottom': '10mm',
        'margin-left': '10mm',
        'encoding': "UTF-8",
        'enable-local-file-access': None # Чтобы картинки/css грузились
    }
    
    # 4. Конвертируем HTML в PDF прямо в оперативной памяти (без сохранения на диск SSD)
    pdf_bytes = pdfkit.from_string(html_content, False, options=options)
    
    # 5. Отдаем файл юзеру на скачивание
    filename = f"report_layer_{layer_id}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(
        io.BytesIO(pdf_bytes),
        download_name=filename,
        as_attachment=True,
        mimetype='application/pdf'
    )

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
    # Защита маршрута через флаг сессии
    if not session.get('is_admin'):
        flash('Доступ запрещен. Требуются права администратора.', 'error')
        return redirect(url_for('index'))
    
    all_users = User.query.all()
    
    # Достаем структуру слоев для модалки редактирования
    config_path = os.path.join(app.root_path, 'layers_config.json')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            all_layers = json.load(f)
    except Exception:
        all_layers = [] 
        
    # --- НОВОЕ: Проверка статуса обучалки для админки ---
    # Нам нужен текущий пользователь, чтобы посмотреть его личные настройки
    current_user = db.session.get(User, session['user_id'])
    
    state_dict = current_user.onboarding_state if current_user.onboarding_state else {}
    # Ищем ключ 'admin'. Если его еще нет, возвращаем False
    has_seen_tutorial = state_dict.get('admin', False)
        
    # Передаем юзеров, слои и статус обучалки в шаблон
    return render_template('admin.html', 
                           users=all_users, 
                           all_layers=all_layers,
                           has_seen_tutorial=json.dumps(has_seen_tutorial))

# --- ОБНОВЛЕННЫЕ ЭНДПОИНТЫ ЮЗЕРОВ (С ПОДДЕРЖКОЙ ФИО И 3 РОЛЕЙ) ---

@app.route('/admin/api/create_user', methods=['POST'])
def api_create_user():
    """Единый API-эндпоинт для создания юзеров (с паролями, ФИО, 3 ролями и слоями)"""
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Не авторизован'}), 401
        
    current_user = db.session.get(User, session['user_id'])
    if not current_user or not current_user.is_admin:
        return jsonify({'status': 'error', 'message': 'Нет прав'}), 403

    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': 'Пустой запрос'}), 400

    username = data.get('username', '').strip()
    full_name = data.get('full_name', '').strip() or None
    email = data.get('email')
    password = data.get('password')
    expire_days = data.get('expire_days')
    is_admin = data.get('is_admin', False)
    role_from_front = data.get('role') # Может прийти 'admin', 'worker' или 'viewer'
    allowed_layers = data.get('allowed_layers', []) 
    
    if not username:
        return jsonify({'status': 'error', 'message': 'Логин не может быть пустым'}), 400

    if not email or email.strip() == '':
        email = None

    if User.query.filter_by(username=username).first():
        return jsonify({'status': 'error', 'message': 'Пользователь с таким логином уже существует'}), 400

    if not password:
        password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))

    expires_at = None
    if expire_days and str(expire_days).isdigit():
        expires_at = datetime.now() + timedelta(days=int(expire_days))

    # Определяем роль: приоритет явному полю 'role', иначе фоллбэк на старый 'is_admin'
    if role_from_front in ['admin', 'worker', 'viewer']:
        role_name = role_from_front
    else:
        role_name = 'admin' if is_admin else 'worker'
        
    role = Role.query.filter_by(name=role_name).first()
    if not role:
        return jsonify({'status': 'error', 'message': f'Системная роль {role_name} не найдена в БД.'}), 500

    # Работникам и админам по твоей задумке можно сразу открывать все слои, 
    # а ограничивать только пользователей (viewer), либо по выбору в админке:
    has_all = (role_name in ['admin', 'worker']) or (allowed_layers == "*")

    new_user = User(
        username=username,
        full_name=full_name,
        email=email,
        password_hash=generate_password_hash(password),
        expires_at=expires_at,
        role_id=role.id,
        has_all_layers=has_all
    )
    
    db.session.add(new_user)
    db.session.commit()
    
    if not has_all and isinstance(allowed_layers, list):
        for layer_id in allowed_layers:
            try:
                db.session.add(UserLayer(user_id=new_user.id, layer_id=int(layer_id)))
            except ValueError:
                pass
        db.session.commit()

    log_action(current_user.id, current_user.username, 'АДМИНКА', f'Создан аккаунт ({role_name}): {username}')

    return jsonify({
        'status': 'success', 
        'message': f'Пользователь {username} успешно создан!',
        'temp_password': password
    })


@app.route('/admin/api/edit_user/<int:user_id>', methods=['POST'])
def api_edit_user(user_id):
    """API-эндпоинт для редактирования существующего пользователя"""
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Не авторизован'}), 401
        
    current_user = db.session.get(User, session['user_id'])
    if not current_user or not current_user.is_admin:
        return jsonify({'status': 'error', 'message': 'Нет прав'}), 403

    target_user = db.session.get(User, user_id)
    if not target_user:
        return jsonify({'status': 'error', 'message': 'Пользователь не найден'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': 'Пустой запрос'}), 400

    new_username = data.get('username')
    if new_username and new_username != target_user.username:
        if User.query.filter_by(username=new_username).first():
            return jsonify({'status': 'error', 'message': 'Логин уже занят другим пользователем'}), 400
        target_user.username = new_username

    if 'full_name' in data:
        fn = data.get('full_name')
        target_user.full_name = fn.strip() if fn and fn.strip() != '' else None

    if 'email' in data:
        email = data.get('email')
        target_user.email = email.strip() if email and email.strip() != '' else None
    
    password = data.get('password')
    if password and password.strip() != '':
        target_user.password_hash = generate_password_hash(password)

    # Обновляем роль (поддержка как 'role', так и старого 'is_admin')
    if 'role' in data and data.get('role') in ['admin', 'worker', 'viewer']:
        role = Role.query.filter_by(name=data.get('role')).first()
        if role:
            target_user.role_id = role.id
    elif 'is_admin' in data:
        role_name = 'admin' if data.get('is_admin') else 'worker'
        role = Role.query.filter_by(name=role_name).first()
        if role:
            target_user.role_id = role.id

    # Обновляем слои
    if 'allowed_layers' in data:
        allowed_layers = data.get('allowed_layers')
        UserLayer.query.filter_by(user_id=target_user.id).delete()
        
        if allowed_layers == "*" or target_user.role_name in ['admin', 'worker']:
            target_user.has_all_layers = True
        else:
            target_user.has_all_layers = False
            if isinstance(allowed_layers, list):
                for layer_id in allowed_layers:
                    try:
                        db.session.add(UserLayer(user_id=target_user.id, layer_id=int(layer_id)))
                    except ValueError:
                        pass

    expire_days = data.get('expire_days')
    if expire_days and str(expire_days).isdigit():
        target_user.expires_at = datetime.now() + timedelta(days=int(expire_days))
    elif expire_days == "": 
        target_user.expires_at = None

    db.session.commit()
    log_action(current_user.id, current_user.username, 'АДМИНКА', f'Отредактирован аккаунт: {target_user.username}')

    return jsonify({
        'status': 'success', 
        'message': f'Аккаунт {target_user.username} успешно обновлен!'
    })


# =====================================================================
# --- МОДУЛЬ CRM: УПРАВЛЕНИЕ ЗАДАЧАМИ И ЭФФЕКТИВНОСТЬЮ ЛАБОРАТОРИИ ---
# =====================================================================

def parse_deadline(date_str):
    """Умный парсер дат: понимает и 'YYYY-MM-DDTHH:MM', и просто 'YYYY-MM-DD'"""
    if not date_str or not str(date_str).strip():
        return None
    date_str = str(date_str).strip()
    for fmt in ('%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M', '%Y-%m-%d', '%d.%m.%Y'):
        try:
            dt = datetime.strptime(date_str, fmt)
            # Если передана только дата без времени, ставим конец рабочего дня (23:59)
            if fmt in ('%Y-%m-%d', '%d.%m.%Y'):
                dt = dt.replace(hour=23, minute=59, second=59)
            return dt
        except ValueError:
            continue
    return None


@app.route('/api/tasks/workers', methods=['GET'])
def api_get_workers():
    """
    Отдает список сотрудников (лаборантов/геологов), которым начальник 
    может насильно назначить задачу в выпадающем списке.
    Инвесторы ('viewer') сюда не попадают!
    """
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Не авторизован'}), 401

    current_user = db.session.get(User, session['user_id'])
    if not current_user or not current_user.can_assign:
        return jsonify({'status': 'error', 'message': 'Доступ запрещен'}), 403

    # Берем всех пользователей, у чьей роли есть право получать задачи (или роль 'worker')
    workers = User.query.join(Role).filter(
        (Role.can_receive_tasks == True) | (Role.name == 'worker')
    ).order_by(User.username.asc()).all()

    workers_list = [{
        'id': w.id,
        'username': w.username,
        'full_name': w.full_name or w.username,
        'email': w.email
    } for w in workers]

    return jsonify({'status': 'success', 'workers': workers_list})


@app.route('/api/tasks/my', methods=['GET'])
def api_get_my_tasks():
    """
    Личный кабинет сотрудника: отдает все задачи, назначенные текущему пользователю,
    плюс его личную статистику (KPI/баллы). Инвесторам ('viewer') вход закрыт.
    """
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Не авторизован'}), 401

    current_user = db.session.get(User, session['user_id'])
    if not current_user or current_user.role_name == 'viewer':
        return jsonify({'status': 'error', 'message': 'У вашей роли нет доступа к модулю задач'}), 403

    tasks = Task.query.filter_by(assignee_id=current_user.id).order_by(Task.created_at.desc()).all()
    tasks_data = [t.to_dict() for t in tasks]

    # Считаем статистику для красивых плашек в личном кабинете
    now = datetime.now()
    completed_tasks = [t for t in tasks if t.status == 'completed']
    completed_this_month = [
        t for t in completed_tasks 
        if t.completed_at and t.completed_at.year == now.year and t.completed_at.month == now.month
    ]
    
    total_score_month = sum(t.score for t in completed_this_month if t.score)
    scored_tasks = [t.score for t in completed_tasks if t.score is not None]
    avg_score = round(sum(scored_tasks) / len(scored_tasks), 1) if scored_tasks else 0.0

    stats = {
        'pending_count': sum(1 for t in tasks if t.status == 'pending'),
        'in_progress_count': sum(1 for t in tasks if t.status == 'in_progress'),
        'review_count': sum(1 for t in tasks if t.status == 'review'),
        'completed_count': len(completed_tasks),
        'overdue_count': sum(1 for t in tasks if t.status != 'completed' and t.is_overdue),
        'month_points': total_score_month,
        'average_score': avg_score
    }

    return jsonify({
        'status': 'success',
        'tasks': tasks_data,
        'stats': stats
    })


@app.route('/api/tasks/all', methods=['GET'])
def api_get_all_tasks():
    """
    Доска руководителя: отдает все задачи лаборатории.
    Поддерживает фильтры: ?assignee_id=5&status=review&month=2026-10
    """
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Не авторизован'}), 401

    current_user = db.session.get(User, session['user_id'])
    if not current_user or not current_user.can_assign:
        return jsonify({'status': 'error', 'message': 'Доступ только для руководства'}), 403

    query = Task.query

    # Фильтр по конкретному лаборанту
    assignee_id = request.args.get('assignee_id')
    if assignee_id and assignee_id.isdigit():
        query = query.filter_by(assignee_id=int(assignee_id))

    # Фильтр по статусу ('pending', 'in_progress', 'review', 'completed')
    status_filter = request.args.get('status')
    if status_filter in ['pending', 'in_progress', 'review', 'completed']:
        query = query.filter_by(status=status_filter)

    tasks = query.order_by(Task.created_at.desc()).all()

    # Опциональный фильтр по месяцу (формат 'YYYY-MM') для просмотра архива/рабочих карт
    month_filter = request.args.get('month')
    if month_filter and re.match(r'^\d{4}-\d{2}$', month_filter):
        year, month = map(int, month_filter.split('-'))
        tasks = [
            t for t in tasks 
            if (t.created_at and t.created_at.year == year and t.created_at.month == month) or
               (t.completed_at and t.completed_at.year == year and t.completed_at.month == month)
        ]

    return jsonify({
        'status': 'success',
        'tasks': [t.to_dict() for t in tasks]
    })


@app.route('/api/tasks/create', methods=['POST'])
def api_create_task():
    """
    Насильное назначение задачи конкретному сотруднику руководителем.
    Создает задачу в статусе 'pending' (Ожидает принятия сотрудником).
    """
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Не авторизован'}), 401

    current_user = db.session.get(User, session['user_id'])
    if not current_user or not current_user.can_assign:
        return jsonify({'status': 'error', 'message': 'У вас нет прав назначать задачи'}), 403

    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': 'Пустой запрос'}), 400

    title = data.get('title', '').strip()
    description = data.get('description', '').strip()
    assignee_id = data.get('assignee_id')
    deadline_raw = data.get('deadline')

    if not title:
        return jsonify({'status': 'error', 'message': 'Укажите название задачи'}), 400
    if not assignee_id:
        return jsonify({'status': 'error', 'message': 'Необходимо обязательно выбрать исполнителя'}), 400

    assignee = db.session.get(User, int(assignee_id))
    if not assignee:
        return jsonify({'status': 'error', 'message': 'Выбранный сотрудник не найден'}), 404

    if assignee.role_name == 'viewer':
        return jsonify({'status': 'error', 'message': 'Нельзя назначить рабочую задачу гостю/инвестору!'}), 400

    deadline_dt = parse_deadline(deadline_raw)
    if deadline_raw and not deadline_dt:
        return jsonify({'status': 'error', 'message': 'Неверный формат даты дедлайна'}), 400

    new_task = Task(
        title=title,
        description=description,
        status='pending',
        created_at=datetime.now(),
        deadline=deadline_dt,
        assignee_id=assignee.id,
        author_id=current_user.id
    )

    db.session.add(new_task)
    db.session.commit()

    log_action(
        current_user.id, 
        current_user.username, 
        'CRM', 
        f'Назначена задача #{new_task.id} ("{title[:40]}") сотруднику {assignee.username}'
    )

    return jsonify({
        'status': 'success',
        'message': f'Задача успешно назначена сотруднику {assignee.full_name or assignee.username}!',
        'task': new_task.to_dict()
    })


@app.route('/api/tasks/<int:task_id>/accept', methods=['POST'])
def api_accept_task(task_id):
    """
    Кнопка «Принять задачу» для лаборанта.
    Фиксирует точное время принятия (accepted_at) и переводит статус в 'in_progress'.
    """
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Не авторизован'}), 401

    current_user = db.session.get(User, session['user_id'])
    task = db.session.get(Task, task_id)

    if not task:
        return jsonify({'status': 'error', 'message': 'Задача не найдена'}), 404

    if task.assignee_id != current_user.id:
        return jsonify({'status': 'error', 'message': 'Вы не являетесь исполнителем этой задачи'}), 403

    if task.status != 'pending':
        return jsonify({'status': 'error', 'message': 'Задача уже принята в работу или завершена'}), 400

    task.status = 'in_progress'
    task.accepted_at = datetime.now()
    db.session.commit()

    log_action(current_user.id, current_user.username, 'CRM', f'Принята в работу задача #{task.id}')

    return jsonify({
        'status': 'success',
        'message': 'Задача принята в работу!',
        'task': task.to_dict()
    })


@app.route('/api/tasks/<int:task_id>/submit', methods=['POST'])
def api_submit_task(task_id):
    """
    Кнопка «Сдать на проверку» для лаборанта.
    Принимает обязательный текстовый отчет и опциональный файл.
    Поддерживает и multipart/form-data (с файлом), и обычный JSON.
    """
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Не авторизован'}), 401

    current_user = db.session.get(User, session['user_id'])
    task = db.session.get(Task, task_id)

    if not task:
        return jsonify({'status': 'error', 'message': 'Задача не найдена'}), 404

    if task.assignee_id != current_user.id:
        return jsonify({'status': 'error', 'message': 'Вы не являетесь исполнителем этой задачи'}), 403

    if task.status != 'in_progress':
        return jsonify({'status': 'error', 'message': 'Сдать можно только задачу, находящуюся в работе'}), 400

    # Универсальное чтение: сначала проверяем JSON, иначе берем из формы (multipart/form-data)
    if request.is_json:
        data = request.get_json()
        report_text = data.get('employee_report', '').strip()
        uploaded_file = None
    else:
        report_text = request.form.get('employee_report', '').strip()
        uploaded_file = request.files.get('attachment')

    if not report_text:
        return jsonify({'status': 'error', 'message': 'Напишите краткий отчет о проделанной работе перед сдачей'}), 400

    # Если прикрепили файл — сохраняем его на диск
    if uploaded_file and uploaded_file.filename:
        safe_name = secure_filename(uploaded_file.filename)
        # Если имя файла было полностью на кириллице и secure_filename оставил только расширение
        if not safe_name or safe_name.startswith('.'):
            ext = os.path.splitext(uploaded_file.filename)[1]
            safe_name = f"report_file{ext}"
            
        unique_filename = f"task_{task.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_name}"
        full_save_path = os.path.join(TASKS_UPLOAD_FOLDER, unique_filename)
        
        # Если у задачи уже был старый файл (при пересдаче) — аккуратно удаляем старый
        if task.attachment_path and os.path.exists(task.attachment_path):
            try:
                os.remove(task.attachment_path)
            except OSError:
                pass
                
        uploaded_file.save(full_save_path)
        task.attachment_path = full_save_path

    task.employee_report = report_text
    task.status = 'review'
    task.submitted_at = datetime.now()
    db.session.commit()

    log_action(current_user.id, current_user.username, 'CRM', f'Задача #{task.id} отправлена на проверку руководителю')

    return jsonify({
        'status': 'success',
        'message': 'Отчет отправлен руководителю на проверку!',
        'task': task.to_dict()
    })


@app.route('/api/tasks/<int:task_id>/review', methods=['POST'])
def api_review_task(task_id):
    """
    Вердикт руководителя по задаче:
    - action = 'approve': закрывает задачу ('completed'), ставит балл от 1 до 10, фиксирует completed_at.
    - action = 'reject': возвращает задачу на доработку ('in_progress'), опционально меняет дедлайн.
    - action = 'extend_deadline': просто продлевает срок выполнения задачи в любой момент.
    """
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Не авторизован'}), 401

    current_user = db.session.get(User, session['user_id'])
    if not current_user or not current_user.can_assign:
        return jsonify({'status': 'error', 'message': 'Только руководитель может проверять и оценивать задачи'}), 403

    task = db.session.get(Task, task_id)
    if not task:
        return jsonify({'status': 'error', 'message': 'Задача не найдена'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'status': 'error', 'message': 'Пустой запрос'}), 400

    action = data.get('action') # Ожидаем 'approve', 'reject' или 'extend_deadline'

    # ВАРИАНТ 1: Принять работу и выставить баллы (1-10)
    if action == 'approve':
        score = data.get('score')
        try:
            score_int = int(score)
            if not (1 <= score_int <= 10):
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({'status': 'error', 'message': 'Оценка должна быть целым числом от 1 до 10'}), 400

        task.score = score_int
        task.status = 'completed'
        task.completed_at = datetime.now()
        # Если начальник закрыл задачу сразу без этапа сдачи, проставим даты для порядка в отчете
        if not task.accepted_at:
            task.accepted_at = task.completed_at
        if not task.submitted_at:
            task.submitted_at = task.completed_at

        db.session.commit()
        log_action(current_user.id, current_user.username, 'CRM', f'Задача #{task.id} принята с оценкой {score_int}/10')

        return jsonify({
            'status': 'success',
            'message': f'Задача закрыта! Выставлена оценка: {score_int} из 10.',
            'task': task.to_dict()
        })

    # ВАРИАНТ 2: Вернуть задачу сотруднику на доработку (с возможным продлением дедлайна)
    elif action == 'reject':
        new_deadline_raw = data.get('new_deadline')
        if new_deadline_raw:
            new_dt = parse_deadline(new_deadline_raw)
            if not new_dt:
                return jsonify({'status': 'error', 'message': 'Неверный формат новой даты дедлайна'}), 400
            task.deadline = new_dt

        task.status = 'in_progress'
        task.completed_at = None
        task.score = None
        db.session.commit()

        log_action(current_user.id, current_user.username, 'CRM', f'Задача #{task.id} возвращена на доработку')

        return jsonify({
            'status': 'success',
            'message': 'Задача возвращена сотруднику на доработку!',
            'task': task.to_dict()
        })

    # ВАРИАНТ 3: Просто продлить дедлайн задачи
    elif action == 'extend_deadline':
        new_deadline_raw = data.get('new_deadline')
        new_dt = parse_deadline(new_deadline_raw)
        if not new_dt:
            return jsonify({'status': 'error', 'message': 'Укажите корректную дату нового дедлайна'}), 400

        task.deadline = new_dt
        db.session.commit()

        log_action(current_user.id, current_user.username, 'CRM', f'Продлен срок задачи #{task.id} до {new_dt.strftime("%d.%m.%Y %H:%M")}')

        return jsonify({
            'status': 'success',
            'message': 'Срок выполнения задачи успешно обновлен!',
            'task': task.to_dict()
        })

    return jsonify({'status': 'error', 'message': 'Неизвестное действие (ожидается approve, reject или extend_deadline)'}), 400


@app.route('/api/tasks/<int:task_id>/delete', methods=['DELETE', 'POST'])
def api_delete_task(task_id):
    """Удаление задачи руководителем (если создана по ошибке)"""
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Не авторизован'}), 401

    current_user = db.session.get(User, session['user_id'])
    if not current_user or not current_user.can_assign:
        return jsonify({'status': 'error', 'message': 'Нет прав на удаление задач'}), 403

    task = db.session.get(Task, task_id)
    if not task:
        return jsonify({'status': 'error', 'message': 'Задача не найдена'}), 404

    # Удаляем прикрепленный файл с диска, если он был
    if task.attachment_path and os.path.exists(task.attachment_path):
        try:
            os.remove(task.attachment_path)
        except OSError:
            pass

    task_title = task.title
    db.session.delete(task)
    db.session.commit()

    log_action(current_user.id, current_user.username, 'CRM', f'Удалена задача #{task_id} ("{task_title[:40]}")')

    return jsonify({'status': 'success', 'message': 'Задача успешно удалена'})


@app.route('/api/tasks/<int:task_id>/attachment', methods=['GET'])
def download_task_attachment(task_id):
    """Защищенное скачивание прикрепленного к отчету файла"""
    if 'user_id' not in session:
        return "Доступ запрещен", 403

    current_user = db.session.get(User, session['user_id'])
    task = db.session.get(Task, task_id)

    if not task or not task.attachment_path or not os.path.exists(task.attachment_path):
        return "Файл не найден", 404

    # Скачать файл может только сам исполнитель задачи или руководство
    if task.assignee_id != current_user.id and not current_user.can_assign:
        log_action(current_user.id, current_user.username, 'ВТОРЖЕНИЕ', f'Попытка скачать чужой отчет по задаче #{task.id}')
        return "У вас нет прав для скачивания этого файла", 403

    return send_file(
        task.attachment_path,
        as_attachment=True,
        download_name=os.path.basename(task.attachment_path)
    )

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

@app.route('/api/onboarding/update', methods=['POST'])
def update_onboarding():
    if 'user_id' not in session:
        return jsonify({'error': 'Не авторизован'}), 401
        
    data = request.get_json()
    page = data.get('page')       # Ожидаем 'map' или 'admin'
    status = data.get('status')   # True (пройдено) или False (сброшено)
    
    user = db.session.get(User, session['user_id'])
    
    # Берем текущий словарь состояний или создаем пустой
    state = user.onboarding_state if user.onboarding_state else {}
    
    # Обновляем статус конкретной страницы
    state[page] = status
    user.onboarding_state = state
    
    # Особенность SQLAlchemy: нужно принудительно сказать, что JSON изменился
    flag_modified(user, 'onboarding_state')
    db.session.commit()
    
    return jsonify({'status': 'success', 'page': page, 'state': status})

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)