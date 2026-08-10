import os
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta

# Активируем чтение скрытого файла .env
load_dotenv()

app = Flask(__name__)

# Достаем ключ из сейфа
app.secret_key = os.environ.get('SECRET_KEY')

# Если ключа нет (например, забыли создать .env), роняем сервер с ошибкой
if not app.secret_key:
    raise ValueError("Не задан SECRET_KEY в переменных окружения!")

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- МОДЕЛЬ ПОЛЬЗОВАТЕЛЯ В БАЗЕ ДАННЫХ ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=True) # Если None — аккаунт бессрочный
    is_admin = db.Column(db.Boolean, default=False)    # НОВОЕ: Флаг администратора

    # Проверка, не истёк ли срок годности аккаунта
    def is_active(self):
        if self.expires_at is None:
            return True
        return datetime.now() < self.expires_at

# Автоматическое создание таблиц при запуске
with app.app_context():
    db.create_all()

# --- РОУТЫ ---

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
        
        # Ищем пользователя в базе
        user = User.query.filter_by(username=username).first()
        
        # Проверяем: 1. Существует ли юзер. 2. Совпадает ли хэш пароля
        if user and check_password_hash(user.password_hash, password):
            # 3. Проверяем, не истёк ли срок действия
            if user.is_active():
                session['user'] = username
                session['is_admin'] = user.is_admin # НОВОЕ: Сохраняем права в сессию
                return redirect(url_for('hub'))
            else:
                error = 'Срок действия вашего аккаунта истёк.'
                return render_template('login.html', error=error)
        else:
            error = 'Неверный логин или пароль'
            return render_template('login.html', error=error)
            
    return render_template('login.html')

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
    
    # Можно добавить чекбокс в форму "Сделать админом"
    # is_admin_flag = True if request.form.get('is_admin') == 'on' else False
    is_admin_flag = request.form.get('is_admin') == 'on'

    existing_user = User.query.filter_by(username=username).first()
    if existing_user:
        flash(f'Пользователь {username} уже существует!', 'error')
        return redirect(url_for('admin_panel'))

    hashed_pw = generate_password_hash(password)

    expires_at = None
    if expire_days and expire_days.isdigit():
        expires_at = datetime.now() + timedelta(days=int(expire_days))

    # Создаем с учетом роли
    new_user = User(username=username, password_hash=hashed_pw, expires_at=expires_at, is_admin=is_admin_flag)
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