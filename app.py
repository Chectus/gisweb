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
    task_participations = db.relationship('TaskAssignee', backref='user', cascade="all, delete-orphan", lazy=True)

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
        """Может ли пользователь получать задачи в работу (Админы и Лаборанты)"""
        return self.role is not None and self.role.name != 'viewer'

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


# 4.1. ИНДИВИДУАЛЬНОЕ НАЗНАЧЕНИЕ В ЗАДАЧЕ (Поддержка нескольких исполнителей)
class TaskAssignee(db.Model):
    __tablename__ = 'task_assignees'
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)

    # Личный статус сотрудника по этой задаче: 'pending', 'in_progress', 'review', 'completed'
    status = db.Column(db.String(50), default='pending')
    score = db.Column(db.Integer, nullable=True) # Личная оценка сотрудника (1-10)

    # Личный отчет, файл и замечание начальника для этого конкретного сотрудника
    employee_report = db.Column(db.Text, nullable=True)
    attachment_path = db.Column(db.String(255), nullable=True)
    reviewer_comment = db.Column(db.Text, nullable=True)

    # Личный тайминг сотрудника
    accepted_at = db.Column(db.DateTime, nullable=True)
    submitted_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)

    @property
    def is_overdue(self):
        deadline = self.task.deadline if self.task else None
        if not deadline:
            return False
        if self.status == 'completed':
            check_time = self.submitted_at or self.completed_at or datetime.now()
            return check_time > deadline
        return datetime.now() > deadline

    @property
    def is_revision(self):
        return self.status == 'in_progress' and bool(self.reviewer_comment)

    @property
    def visual_status(self):
        if self.status == 'completed':
            return 'completed_late' if self.is_overdue else 'completed_on_time'
        if self.is_overdue:
            return 'overdue'
        if self.status == 'review':
            return 'review'
        if self.is_revision:
            return 'revision'
        return self.status # 'pending' или 'in_progress'

    def to_dict(self):
        fmt = '%d.%m.%Y %H:%M'
        u = self.user
        display_name = (u.full_name or u.username) if u else 'Удален'
        return {
            'user_id': self.user_id,
            'username': u.username if u else 'Удален',
            'full_name': display_name,
            'role': u.role_name if u else 'worker',
            'status': self.status,
            'visual_status': self.visual_status,
            'is_overdue': self.is_overdue,
            'is_revision': self.is_revision,
            'score': self.score,
            'employee_report': self.employee_report or '',
            'reviewer_comment': self.reviewer_comment or '',
            'has_attachment': bool(self.attachment_path),
            'attachment_name': os.path.basename(self.attachment_path) if self.attachment_path else None,
            'attachment_url': url_for('download_task_attachment', task_id=self.task_id, user_id=self.user_id) if self.attachment_path else None,
            'accepted_at': self.accepted_at.strftime(fmt) if self.accepted_at else None,
            'submitted_at': self.submitted_at.strftime(fmt) if self.submitted_at else None,
            'completed_at': self.completed_at.strftime(fmt) if self.completed_at else None
        }


# 4.2. ЗАДАЧИ (Модуль CRM)
class Task(db.Model):
    __tablename__ = 'tasks'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    
    # Агрегированный статус задачи: 'pending', 'in_progress', 'review', 'completed'
    status = db.Column(db.String(50), default='pending')
    score = db.Column(db.Integer, nullable=True)
    
    employee_report = db.Column(db.Text, nullable=True)
    attachment_path = db.Column(db.String(255), nullable=True)
    reviewer_comment = db.Column(db.Text, nullable=True)
    
    # Строгий тайминг
    created_at = db.Column(db.DateTime, default=datetime.now)
    deadline = db.Column(db.DateTime, nullable=True)
    accepted_at = db.Column(db.DateTime, nullable=True)
    submitted_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    
    # Оставляем assignee_id для обратной совместимости со старой схемой БД (хранит первого исполнителя)
    assignee_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # Список всех назначенных исполнителей (1, 2, 5 и т.д.)
    assignments = db.relationship('TaskAssignee', backref='task', cascade="all, delete-orphan", lazy='joined')

    def sync_aggregate_state(self):
        """
        Пересчитывает общий статус задачи на основе статусов всех её исполнителей.
        - Если все завершили -> 'completed'
        - Если хотя бы один сдал на проверку -> 'review' (чтобы начальник сразу видел!)
        - Если хотя бы один принял или завершил -> 'in_progress'
        - Иначе -> 'pending'
        """
        if not self.assignments:
            return
        statuses = [a.status for a in self.assignments]
        if all(s == 'completed' for s in statuses):
            self.status = 'completed'
            comp_dates = [a.completed_at for a in self.assignments if a.completed_at]
            self.completed_at = max(comp_dates) if comp_dates else datetime.now()
            scores = [a.score for a in self.assignments if a.score is not None]
            if scores:
                self.score = round(sum(scores) / len(scores))
        elif any(s == 'review' for s in statuses):
            self.status = 'review'
            self.completed_at = None
        elif any(s in ('in_progress', 'completed') for s in statuses):
            self.status = 'in_progress'
            self.completed_at = None
        else:
            self.status = 'pending'
            self.completed_at = None

        acc_dates = [a.accepted_at for a in self.assignments if a.accepted_at]
        if acc_dates:
            self.accepted_at = min(acc_dates)
        sub_dates = [a.submitted_at for a in self.assignments if a.submitted_at]
        if sub_dates:
            self.submitted_at = max(sub_dates)

    @property
    def is_overdue(self):
        if not self.deadline:
            return False
        if self.status == 'completed':
            check_time = self.submitted_at or self.completed_at or datetime.now()
            return check_time > self.deadline
        return datetime.now() > self.deadline

    @property
    def is_revision(self):
        if self.assignments:
            return any(a.is_revision for a in self.assignments)
        return self.status == 'in_progress' and bool(self.reviewer_comment)

    @property
    def visual_status(self):
        if self.status == 'completed':
            return 'completed_late' if self.is_overdue else 'completed_on_time'
        if self.is_overdue:
            return 'overdue'
        if self.status == 'review':
            return 'review'
        if self.is_revision:
            return 'revision'
        return self.status

    def to_dict(self, for_user_id=None):
        """
        Упаковка задачи в JSON.
        Если передан for_user_id (для Личного кабинета и Таймлайна конкретного человека),
        основные поля статуса/цвета/отчета заполняются данными ЭТОГО сотрудника.
        А в массиве 'assignees' всегда отдается полная картина по всем участникам!
        """
        fmt = '%d.%m.%Y %H:%M'
        iso_fmt = '%Y-%m-%dT%H:%M'
        date_only_fmt = '%Y-%m-%d'
        
        start_dt = self.created_at or datetime.now()
        end_dt = self.deadline or self.completed_at or datetime.now()
        if end_dt < start_dt:
            end_dt = start_dt

        assignees_list = [a.to_dict() for a in sorted(self.assignments, key=lambda x: x.id)]
        total_cnt = len(assignees_list)
        completed_cnt = sum(1 for a in assignees_list if a['status'] == 'completed')
        review_cnt = sum(1 for a in assignees_list if a['status'] == 'review')
        in_progress_cnt = sum(1 for a in assignees_list if a['status'] == 'in_progress')
        pending_cnt = sum(1 for a in assignees_list if a['status'] == 'pending')

        progress_info = {
            'total': total_cnt,
            'completed': completed_cnt,
            'review': review_cnt,
            'in_progress': in_progress_cnt,
            'pending': pending_cnt,
            'submitted_or_done': completed_cnt + review_cnt,
            'label': f"{completed_cnt + review_cnt}/{total_cnt}" if total_cnt > 0 else "0/1"
        }

        # Ищем запись конкретного пользователя, если запрос из /my или /timeline
        personal_a = None
        if for_user_id is not None and self.assignments:
            personal_a = next((a for a in self.assignments if a.user_id == for_user_id), None)

        if personal_a:
            eff_status = personal_a.status
            eff_visual = personal_a.visual_status
            eff_overdue = personal_a.is_overdue
            eff_revision = personal_a.is_revision
            eff_score = personal_a.score
            eff_report = personal_a.employee_report or ''
            eff_comment = personal_a.reviewer_comment or self.reviewer_comment or ''
            eff_has_att = bool(personal_a.attachment_path)
            eff_att_name = os.path.basename(personal_a.attachment_path) if personal_a.attachment_path else None
            eff_att_url = url_for('download_task_attachment', task_id=self.id, user_id=personal_a.user_id) if personal_a.attachment_path else None
            eff_accepted = personal_a.accepted_at.strftime(fmt) if personal_a.accepted_at else None
            eff_submitted = personal_a.submitted_at.strftime(fmt) if personal_a.submitted_at else None
            eff_completed = personal_a.completed_at.strftime(fmt) if personal_a.completed_at else None
        else:
            eff_status = self.status
            eff_visual = self.visual_status
            eff_overdue = self.is_overdue
            eff_revision = self.is_revision
            eff_score = self.score
            # Для общей карточки руководителя собираем сводный текст отчетов, если их несколько
            reports_summary = [
                f"[{a['full_name']}]: {a['employee_report']}" 
                for a in assignees_list if a['employee_report']
            ]
            eff_report = "\n\n".join(reports_summary) if reports_summary else (self.employee_report or '')
            
            comments_summary = [
                f"[{a['full_name']}]: {a['reviewer_comment']}"
                for a in assignees_list if a['reviewer_comment']
            ]
            eff_comment = "\n".join(comments_summary) if comments_summary else (self.reviewer_comment or '')
            
            first_with_att = next((a for a in assignees_list if a['has_attachment']), None)
            eff_has_att = bool(first_with_att) or bool(self.attachment_path)
            eff_att_name = first_with_att['attachment_name'] if first_with_att else (os.path.basename(self.attachment_path) if self.attachment_path else None)
            eff_att_url = first_with_att['attachment_url'] if first_with_att else (url_for('download_task_attachment', task_id=self.id) if self.attachment_path else None)
            eff_accepted = self.accepted_at.strftime(fmt) if self.accepted_at else None
            eff_submitted = self.submitted_at.strftime(fmt) if self.submitted_at else None
            eff_completed = self.completed_at.strftime(fmt) if self.completed_at else None

        # Строка всех имен через запятую, чтобы даже старая верстка сразу показала всех исполнителей!
        all_names_str = ", ".join(a['full_name'] for a in assignees_list) if assignees_list else (
            (self.assignee.full_name or self.assignee.username) if self.assignee else 'Удален'
        )
        all_usernames_str = ", ".join(a['username'] for a in assignees_list) if assignees_list else (
            self.assignee.username if self.assignee else 'Удален'
        )

        return {
            'id': self.id,
            'title': self.title,
            'description': self.description or '',
            'status': eff_status,
            'overall_status': self.status,
            'visual_status': eff_visual,
            'overall_visual_status': self.visual_status,
            'is_overdue': eff_overdue,
            'is_revision': eff_revision,
            'score': eff_score,
            'employee_report': eff_report,
            'reviewer_comment': eff_comment,
            'has_attachment': eff_has_att,
            'attachment_name': eff_att_name,
            'attachment_url': eff_att_url,
            
            # Даты
            'created_at': self.created_at.strftime(fmt) if self.created_at else None,
            'deadline': self.deadline.strftime(fmt) if self.deadline else None,
            'accepted_at': eff_accepted,
            'submitted_at': eff_submitted,
            'completed_at': eff_completed,
            'deadline_iso': self.deadline.strftime(iso_fmt) if self.deadline else None,
            'timeline_start': start_dt.strftime(date_only_fmt),
            'timeline_end': end_dt.strftime(date_only_fmt),
            
            # Новые поля для групповой работы (несколько исполнителей)
            'is_group_task': total_cnt > 1,
            'assignees': assignees_list,
            'assignee_ids': [a['user_id'] for a in assignees_list],
            'progress': progress_info,
            
            # Обратная совместимость со старыми полями карточки
            'assignee_id': self.assignee_id,
            'assignee_username': all_usernames_str,
            'assignee_full_name': all_names_str,
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

_schema_synced = False

@app.before_request
def ensure_multi_assignee_schema():
    """
    Автоматическая безопасная миграция при первом запросе:
    1. Создает таблицу task_assignees в PostgreSQL, если её еще нет.
    2. Переносит уже существующие одиночные задачи из tasks в task_assignees без потери данных.
    """
    global _schema_synced
    if _schema_synced:
        return
    try:
        db.create_all()
        legacy_tasks = Task.query.all()
        migrated = False
        for t in legacy_tasks:
            if not t.assignments and t.assignee_id:
                ta = TaskAssignee(
                    task_id=t.id,
                    user_id=t.assignee_id,
                    status=t.status or 'pending',
                    score=t.score,
                    employee_report=t.employee_report,
                    attachment_path=t.attachment_path,
                    reviewer_comment=t.reviewer_comment,
                    accepted_at=t.accepted_at,
                    submitted_at=t.submitted_at,
                    completed_at=t.completed_at
                )
                db.session.add(ta)
                migrated = True
        if migrated:
            db.session.commit()
        _schema_synced = True
    except Exception as e:
        db.session.rollback()
        print(f"[-] Предупреждение авто-синхронизации CRM: {e}")


def parse_deadline(date_str):
    """Умный парсер дат: понимает и 'YYYY-MM-DDTHH:MM', и просто 'YYYY-MM-DD'"""
    if not date_str or not str(date_str).strip():
        return None
    date_str = str(date_str).strip()
    for fmt in ('%Y-%m-%dT%H:%M', '%Y-%m-%d %H:%M', '%Y-%m-%d', '%d.%m.%Y'):
        try:
            dt = datetime.strptime(date_str, fmt)
            if fmt in ('%Y-%m-%d', '%d.%m.%Y'):
                dt = dt.replace(hour=23, minute=59, second=59)
            return dt
        except ValueError:
            continue
    return None


@app.route('/api/tasks/workers', methods=['GET'])
def api_get_workers():
    """
    Отдает список всех сотрудников и админов (всех, кроме 'viewer'), 
    которым можно назначить задачу (по одному или группой).
    """
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Не авторизован'}), 401

    current_user = db.session.get(User, session['user_id'])
    if not current_user or not current_user.can_assign:
        return jsonify({'status': 'error', 'message': 'Доступ запрещен'}), 403

    workers = User.query.join(Role).filter(
        Role.name != 'viewer'
    ).order_by(User.full_name.asc().nulls_last(), User.username.asc()).all()

    workers_list = [{
        'id': w.id,
        'username': w.username,
        'full_name': w.full_name or w.username,
        'role': w.role_name, # 'admin' или 'worker'
        'email': w.email
    } for w in workers]

    return jsonify({'status': 'success', 'workers': workers_list})


@app.route('/api/tasks/my', methods=['GET'])
def api_get_my_tasks():
    """
    Личный кабинет сотрудника: отдает все задачи (и одиночные, и групповые),
    где текущий пользователь является одним из исполнителей, плюс его личную статистику.
    """
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Не авторизован'}), 401

    current_user = db.session.get(User, session['user_id'])
    if not current_user or current_user.role_name == 'viewer':
        return jsonify({'status': 'error', 'message': 'У вашей роли нет доступа к модулю задач'}), 403

    my_assignments = TaskAssignee.query.filter_by(user_id=current_user.id).all()
    task_ids = [a.task_id for a in my_assignments]
    tasks = Task.query.filter(Task.id.in_(task_ids)).order_by(Task.created_at.desc()).all() if task_ids else []
    
    # Передаем for_user_id=current_user.id, чтобы статус карточки отражал личный прогресс сотрудника
    tasks_data = [t.to_dict(for_user_id=current_user.id) for t in tasks]

    now = datetime.now()
    completed_assignments = [a for a in my_assignments if a.status == 'completed']
    completed_this_month = [
        a for a in completed_assignments 
        if a.completed_at and a.completed_at.year == now.year and a.completed_at.month == now.month
    ]
    
    total_score_month = sum(a.score for a in completed_this_month if a.score)
    scored_list = [a.score for a in completed_assignments if a.score is not None]
    avg_score = round(sum(scored_list) / len(scored_list), 1) if scored_list else 0.0

    stats = {
        'pending_count': sum(1 for a in my_assignments if a.status == 'pending'),
        'in_progress_count': sum(1 for a in my_assignments if a.status == 'in_progress'),
        'review_count': sum(1 for a in my_assignments if a.status == 'review'),
        'completed_count': len(completed_assignments),
        'overdue_count': sum(1 for a in my_assignments if a.status != 'completed' and a.is_overdue),
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

    # Фильтр по конкретному сотруднику (ищет его среди всех участников задачи)
    assignee_id = request.args.get('assignee_id')
    if assignee_id and assignee_id.isdigit():
        uid = int(assignee_id)
        query = query.filter(Task.assignments.any(TaskAssignee.user_id == uid))

    # Фильтр по статусу ('pending', 'in_progress', 'review', 'completed')
    status_filter = request.args.get('status')
    if status_filter in ['pending', 'in_progress', 'review', 'completed']:
        query = query.filter_by(status=status_filter)

    tasks = query.order_by(Task.created_at.desc()).all()

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
    Назначение задачи одному ИЛИ нескольким исполнителям (админам/работникам).
    Принимает:
      - "assignee_ids": [1, 3, 5] (массив ID) 
      - ИЛИ старый вариант "assignee_id": 1 (для обратной совместимости).
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
    deadline_raw = data.get('deadline')

    # Собираем список ID исполнителей (поддерживаем и массив assignee_ids, и одиночный assignee_id)
    raw_ids = data.get('assignee_ids')
    if not raw_ids:
        single_id = data.get('assignee_id')
        if isinstance(single_id, list):
            raw_ids = single_id
        elif single_id is not None and str(single_id).strip() != '':
            raw_ids = [x.strip() for x in str(single_id).split(',') if x.strip()]
        else:
            raw_ids = []

    # Очищаем дубликаты и приводим к int
    clean_ids = []
    for rid in raw_ids:
        try:
            uid = int(rid)
            if uid not in clean_ids:
                clean_ids.append(uid)
        except (ValueError, TypeError):
            continue

    if not title:
        return jsonify({'status': 'error', 'message': 'Укажите название задачи'}), 400
    if not clean_ids:
        return jsonify({'status': 'error', 'message': 'Необходимо выбрать хотя бы одного исполнителя'}), 400

    assignees = []
    for uid in clean_ids:
        u = db.session.get(User, uid)
        if not u:
            return jsonify({'status': 'error', 'message': f'Сотрудник с ID {uid} не найден'}), 404
        if u.role_name == 'viewer':
            return jsonify({'status': 'error', 'message': f'Нельзя назначить задачу инвестору ({u.username})!'}), 400
        assignees.append(u)

    deadline_dt = parse_deadline(deadline_raw)
    if deadline_raw and not deadline_dt:
        return jsonify({'status': 'error', 'message': 'Неверный формат даты дедлайна'}), 400

    new_task = Task(
        title=title,
        description=description,
        status='pending',
        created_at=datetime.now(),
        deadline=deadline_dt,
        assignee_id=assignees[0].id, # Первый исполнитель для обратной совместимости
        author_id=current_user.id
    )
    db.session.add(new_task)
    db.session.flush() # Получаем new_task.id до коммита

    for u in assignees:
        db.session.add(TaskAssignee(
            task_id=new_task.id,
            user_id=u.id,
            status='pending'
        ))

    db.session.commit()

    names_log = ", ".join(u.username for u in assignees)
    log_action(
        current_user.id, 
        current_user.username, 
        'CRM', 
        f'Назначена задача #{new_task.id} ("{title[:35]}") исполнителям: {names_log}'
    )

    names_display = ", ".join(u.full_name or u.username for u in assignees)
    return jsonify({
        'status': 'success',
        'message': f'Задача назначена ({len(assignees)} чел.): {names_display}!',
        'task': new_task.to_dict()
    })


@app.route('/api/tasks/<int:task_id>/accept', methods=['POST'])
def api_accept_task(task_id):
    """
    Кнопка «Принять задачу» для конкретного участника.
    Переводит личный статус сотрудника в 'in_progress' и обновляет общий статус задачи.
    """
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Не авторизован'}), 401

    current_user = db.session.get(User, session['user_id'])
    task = db.session.get(Task, task_id)

    if not task:
        return jsonify({'status': 'error', 'message': 'Задача не найдена'}), 404

    assignment = TaskAssignee.query.filter_by(task_id=task.id, user_id=current_user.id).first()
    if not assignment:
        return jsonify({'status': 'error', 'message': 'Вы не являетесь исполнителем этой задачи'}), 403

    if assignment.status != 'pending':
        return jsonify({'status': 'error', 'message': 'Вы уже приняли эту задачу в работу'}), 400

    assignment.status = 'in_progress'
    assignment.accepted_at = datetime.now()
    task.sync_aggregate_state()
    db.session.commit()

    log_action(current_user.id, current_user.username, 'CRM', f'Принята в работу задача #{task.id}')

    return jsonify({
        'status': 'success',
        'message': 'Задача принята в работу!',
        'task': task.to_dict(for_user_id=current_user.id)
    })


@app.route('/api/tasks/<int:task_id>/submit', methods=['POST'])
def api_submit_task(task_id):
    """
    Кнопка «Сдать на проверку» для конкретного участника задачи.
    Сохраняет его личный отчет и личный файл в TaskAssignee, не затирая файлы коллег!
    """
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Не авторизован'}), 401

    current_user = db.session.get(User, session['user_id'])
    task = db.session.get(Task, task_id)

    if not task:
        return jsonify({'status': 'error', 'message': 'Задача не найдена'}), 404

    assignment = TaskAssignee.query.filter_by(task_id=task.id, user_id=current_user.id).first()
    if not assignment:
        return jsonify({'status': 'error', 'message': 'Вы не являетесь исполнителем этой задачи'}), 403

    if assignment.status != 'in_progress':
        return jsonify({'status': 'error', 'message': 'Сдать можно только задачу, находящуюся у вас в работе'}), 400

    if request.is_json:
        data = request.get_json()
        report_text = data.get('employee_report', '').strip()
        uploaded_file = None
    else:
        report_text = request.form.get('employee_report', '').strip()
        uploaded_file = request.files.get('attachment')

    if not report_text:
        return jsonify({'status': 'error', 'message': 'Напишите краткий отчет о проделанной работе перед сдачей'}), 400

    if uploaded_file and uploaded_file.filename:
        safe_name = secure_filename(uploaded_file.filename)
        if not safe_name or safe_name.startswith('.'):
            ext = os.path.splitext(uploaded_file.filename)[1]
            safe_name = f"report_file{ext}"
            
        unique_filename = f"task_{task.id}_user_{current_user.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_name}"
        full_save_path = os.path.join(TASKS_UPLOAD_FOLDER, unique_filename)
        
        if assignment.attachment_path and os.path.exists(assignment.attachment_path):
            try:
                os.remove(assignment.attachment_path)
            except OSError:
                pass
                
        uploaded_file.save(full_save_path)
        assignment.attachment_path = full_save_path
        task.attachment_path = full_save_path # Для обратной совместимости

    assignment.employee_report = report_text
    assignment.status = 'review'
    assignment.submitted_at = datetime.now()
    
    task.employee_report = report_text
    task.sync_aggregate_state()
    db.session.commit()

    log_action(current_user.id, current_user.username, 'CRM', f'Отчет по задаче #{task.id} отправлен на проверку')

    return jsonify({
        'status': 'success',
        'message': 'Ваш отчет отправлен руководителю на проверку!',
        'task': task.to_dict(for_user_id=current_user.id)
    })


@app.route('/api/tasks/<int:task_id>/review', methods=['POST'])
def api_review_task(task_id):
    """
    Вердикт руководителя по задаче (поддерживает как оценку конкретного участника, так и всей группы):
    - Опциональный параметр "target_user_id": ID конкретного исполнителя. 
      Если не передан — действие применяется ко всем участникам, сдавшим отчет ('review'), либо ко всем участникам задачи.
    - action = 'approve': ставит оценку (1-10) и переводит в 'completed'.
    - action = 'reject': возвращает в 'in_progress' с обязательным комментарием (reviewer_comment).
    - action = 'extend_deadline': продлевает общий дедлайн задачи.
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

    action = data.get('action')
    comment = data.get('reviewer_comment', '').strip()
    target_user_id = data.get('target_user_id') or data.get('assignee_id')

    # Выбираем, кого именно проверяем
    target_assignments = []
    if target_user_id:
        ta = TaskAssignee.query.filter_by(task_id=task.id, user_id=int(target_user_id)).first()
        if not ta:
            return jsonify({'status': 'error', 'message': 'Указанный сотрудник не назначен на эту задачу'}), 404
        target_assignments = [ta]
    else:
        # Если конкретный сотрудник не указан: берем тех, кто на проверке ('review'), 
        # а если таких нет — всех участников задачи
        in_review = [a for a in task.assignments if a.status == 'review']
        target_assignments = in_review if in_review else list(task.assignments)

    # ВАРИАНТ 1: Принять работу и выставить баллы (1-10)
    if action == 'approve':
        score = data.get('score')
        try:
            score_int = int(score)
            if not (1 <= score_int <= 10):
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({'status': 'error', 'message': 'Оценка должна быть целым числом от 1 до 10'}), 400

        now = datetime.now()
        for a in target_assignments:
            a.score = score_int
            a.status = 'completed'
            a.completed_at = now
            if comment:
                a.reviewer_comment = comment
            if not a.accepted_at:
                a.accepted_at = now
            if not a.submitted_at:
                a.submitted_at = now

        if comment:
            task.reviewer_comment = comment
        task.sync_aggregate_state()
        db.session.commit()

        who_str = ", ".join(a.user.username for a in target_assignments if a.user)
        log_action(current_user.id, current_user.username, 'CRM', f'Задача #{task.id} принята у [{who_str}] с оценкой {score_int}/10')

        return jsonify({
            'status': 'success',
            'message': f'Работа принята (оценка: {score_int}/10)!',
            'task': task.to_dict()
        })

    # ВАРИАНТ 2: Вернуть задачу на доработку (конкретному человеку или всем сдавшим)
    elif action == 'reject':
        if not comment:
            return jsonify({
                'status': 'error', 
                'message': 'Пожалуйста, укажите в комментарии, что именно нужно переделать!'
            }), 400

        new_deadline_raw = data.get('new_deadline')
        if new_deadline_raw:
            new_dt = parse_deadline(new_deadline_raw)
            if not new_dt:
                return jsonify({'status': 'error', 'message': 'Неверный формат новой даты дедлайна'}), 400
            task.deadline = new_dt

        for a in target_assignments:
            a.reviewer_comment = comment
            a.status = 'in_progress'
            a.completed_at = None
            a.score = None
            if not a.accepted_at:
                a.accepted_at = datetime.now()

        task.reviewer_comment = comment
        task.sync_aggregate_state()
        db.session.commit()

        who_str = ", ".join(a.user.username for a in target_assignments if a.user)
        log_action(current_user.id, current_user.username, 'CRM', f'Задача #{task.id} возвращена на доработку [{who_str}]: {comment[:50]}')

        return jsonify({
            'status': 'success',
            'message': 'Задача возвращена на доработку с вашим комментарием!',
            'task': task.to_dict()
        })

    # ВАРИАНТ 3: Продлить дедлайн задачи
    elif action == 'extend_deadline':
        new_deadline_raw = data.get('new_deadline')
        new_dt = parse_deadline(new_deadline_raw)
        if not new_dt:
            return jsonify({'status': 'error', 'message': 'Укажите корректную дату нового дедлайна'}), 400

        task.deadline = new_dt
        if comment:
            task.reviewer_comment = comment
            for a in target_assignments:
                a.reviewer_comment = comment
        db.session.commit()

        log_action(current_user.id, current_user.username, 'CRM', f'Продлен срок задачи #{task.id} до {new_dt.strftime("%d.%m.%Y %H:%M")}')

        return jsonify({
            'status': 'success',
            'message': 'Срок выполнения задачи успешно обновлен!',
            'task': task.to_dict()
        })

    return jsonify({'status': 'error', 'message': 'Неизвестное действие (ожидается approve, reject или extend_deadline)'}), 400


@app.route('/api/tasks/timeline', methods=['GET'])
def api_get_timeline():
    """
    Диаграмма Таймлайна с поддержкой групповых задач:
    Если задача назначена 3 сотрудникам, она появится на дорожке у каждого из этих 3 сотрудников,
    причем цвет полоски (visual_status) у каждого будет отражать ЕГО ЛИЧНЫЙ статус по этой задаче!
    """
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Не авторизован'}), 401

    current_user = db.session.get(User, session['user_id'])
    if not current_user or current_user.role_name == 'viewer':
        return jsonify({'status': 'error', 'message': 'Нет доступа к таймлайну задач'}), 403

    now = datetime.now()
    month_param = request.args.get('month')
    start_param = request.args.get('start_date')
    end_param = request.args.get('end_date')

    try:
        if start_param and end_param:
            period_start = datetime.strptime(start_param, '%Y-%m-%d').date()
            period_end = datetime.strptime(end_param, '%Y-%m-%d').date()
        elif month_param and re.match(r'^\d{4}-\d{2}$', month_param):
            y, m = map(int, month_param.split('-'))
            period_start = datetime(y, m, 1).date()
            if m == 12:
                period_end = (datetime(y + 1, 1, 1) - timedelta(days=1)).date()
            else:
                period_end = (datetime(y, m + 1, 1) - timedelta(days=1)).date()
        else:
            period_start = datetime(now.year, now.month, 1).date()
            if now.month == 12:
                period_end = (datetime(now.year + 1, 1, 1) - timedelta(days=1)).date()
            else:
                period_end = (datetime(now.year, now.month + 1, 1) - timedelta(days=1)).date()
    except ValueError:
        return jsonify({'status': 'error', 'message': 'Неверный формат дат периода'}), 400

    if period_end < period_start:
        period_start, period_end = period_end, period_start

    total_days = (period_end - period_start).days + 1

    days_grid = []
    for i in range(total_days):
        curr_d = period_start + timedelta(days=i)
        days_grid.append({
            'date': curr_d.strftime('%Y-%m-%d'),
            'day': curr_d.day,
            'weekday': curr_d.weekday(),
            'is_weekend': curr_d.weekday() in (5, 6),
            'is_today': (curr_d == now.date())
        })

    only_me = request.args.get('only_me') == 'true' or not current_user.can_assign
    if only_me:
        users_list = [current_user]
    else:
        users_list = User.query.join(Role).filter(
            Role.name != 'viewer'
        ).order_by(User.full_name.asc().nulls_last(), User.username.asc()).all()

    employees_timeline = []

    for emp in users_list:
        # Находим все задачи, где сотрудник является участником через TaskAssignee
        emp_tasks = Task.query.filter(
            Task.assignments.any(TaskAssignee.user_id == emp.id)
        ).all()
        visible_tasks = []

        for t in emp_tasks:
            # Берем личную запись сотрудника, чтобы знать его личную дату сдачи
            personal_a = next((a for a in t.assignments if a.user_id == emp.id), None)
            t_start = (t.created_at or now).date()
            
            if t.deadline:
                t_end = t.deadline.date()
            elif personal_a and personal_a.completed_at:
                t_end = personal_a.completed_at.date()
            elif t.completed_at:
                t_end = t.completed_at.date()
            else:
                t_end = max(t_start, now.date())

            if t_end < t_start:
                t_end = t_start

            if t_end < period_start or t_start > period_end:
                continue

            vis_start = max(t_start, period_start)
            vis_end = min(t_end, period_end)

            start_idx = (vis_start - period_start).days
            duration_days = (vis_end - vis_start).days + 1

            # Важно: передаем for_user_id=emp.id, чтобы полоска на таймлайне красилась в ЛИЧНЫЙ статус этого сотрудника!
            task_item = t.to_dict(for_user_id=emp.id)
            task_item.update({
                'real_start_date': t_start.strftime('%Y-%m-%d'),
                'real_end_date': t_end.strftime('%Y-%m-%d'),
                'visible_start_date': vis_start.strftime('%Y-%m-%d'),
                'visible_end_date': vis_end.strftime('%Y-%m-%d'),
                'start_day_index': start_idx,
                'grid_column_start': start_idx + 1,
                'duration_days': duration_days,
                'clipped_left': t_start < period_start,
                'clipped_right': t_end > period_end,
                '_sort_start': vis_start,
                '_sort_end': vis_end
            })
            visible_tasks.append(task_item)

        # Алгоритм раскладки по непересекающимся видеодорожкам
        visible_tasks.sort(key=lambda x: (x['_sort_start'], -x['duration_days']))

        tracks = []
        track_last_end = []

        for item in visible_tasks:
            v_start = item.pop('_sort_start')
            v_end = item.pop('_sort_end')

            placed_track_idx = None
            for idx, last_end_date in enumerate(track_last_end):
                if last_end_date < v_start:
                    placed_track_idx = idx
                    track_last_end[idx] = v_end
                    tracks[idx].append(item)
                    break

            if placed_track_idx is None:
                placed_track_idx = len(tracks)
                track_last_end.append(v_end)
                tracks.append([item])

            item['track_index'] = placed_track_idx

        display_name = emp.full_name or emp.username
        words = [w for w in display_name.split() if w]
        if len(words) >= 2:
            initials = (words[0][0] + words[1][0]).upper()
        else:
            initials = display_name[:2].upper()

        employees_timeline.append({
            'user_id': emp.id,
            'username': emp.username,
            'full_name': display_name,
            'initials': initials,
            'role': emp.role_name,
            'tracks_count': max(1, len(tracks)),
            'tracks': tracks,
            'tasks_flat': visible_tasks
        })

    return jsonify({
        'status': 'success',
        'period': {
            'start_date': period_start.strftime('%Y-%m-%d'),
            'end_date': period_end.strftime('%Y-%m-%d'),
            'total_days': total_days
        },
        'days_grid': days_grid,
        'employees': employees_timeline
    })


@app.route('/api/tasks/<int:task_id>/delete', methods=['DELETE', 'POST'])
def api_delete_task(task_id):
    """Удаление задачи руководителем (вместе со всеми файлами участников)"""
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Не авторизован'}), 401

    current_user = db.session.get(User, session['user_id'])
    if not current_user or not current_user.can_assign:
        return jsonify({'status': 'error', 'message': 'Нет прав на удаление задач'}), 403

    task = db.session.get(Task, task_id)
    if not task:
        return jsonify({'status': 'error', 'message': 'Задача не найдена'}), 404

    for a in task.assignments:
        if a.attachment_path and os.path.exists(a.attachment_path):
            try:
                os.remove(a.attachment_path)
            except OSError:
                pass

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
    """
    Защищенное скачивание файла отчета.
    Поддерживает параметр ?user_id=<id>, чтобы начальник мог скачать файл конкретного участника групповой задачи.
    """
    if 'user_id' not in session:
        return "Доступ запрещен", 403

    current_user = db.session.get(User, session['user_id'])
    task = db.session.get(Task, task_id)
    if not task:
        return "Задача не найдена", 404

    is_participant = any(a.user_id == current_user.id for a in task.assignments)
    if not is_participant and not current_user.can_assign:
        log_action(current_user.id, current_user.username, 'ВТОРЖЕНИЕ', f'Попытка скачать чужой отчет по задаче #{task.id}')
        return "У вас нет прав для скачивания этого файла", 403

    target_uid = request.args.get('user_id', type=int)
    file_path = None

    if target_uid:
        ta = next((a for a in task.assignments if a.user_id == target_uid), None)
        if ta and ta.attachment_path:
            file_path = ta.attachment_path
    else:
        # Если user_id не указан — ищем файл текущего юзера, либо первый доступный
        my_ta = next((a for a in task.assignments if a.user_id == current_user.id and a.attachment_path), None)
        if my_ta:
            file_path = my_ta.attachment_path
        else:
            any_ta = next((a for a in task.assignments if a.attachment_path), None)
            file_path = any_ta.attachment_path if any_ta else task.attachment_path

    if not file_path or not os.path.exists(file_path):
        return "Файл не найден", 404

    return send_file(
        file_path,
        as_attachment=True,
        download_name=os.path.basename(file_path)
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