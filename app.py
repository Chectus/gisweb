from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'super_secret_key_for_laboratory_gis' 

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- МОДЕЛЬ ПОЛЬЗОВАТЕЛЯ В БАЗЕ ДАННЫХ ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=True) # Если None — аккаунт бессрочный

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
    return render_template('hub.html', username=session['user'])

@app.route('/map')
def map_page():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('map.html')

@app.route('/docs')
def docs():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('docs.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)