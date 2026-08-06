from app import app, db, User
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta

def create_user(username, password, days_valid=None):
    with app.app_context():
        # Проверяем, нет ли уже такого пользователя
        if User.query.filter_by(username=username).first():
            print(f"[-] Пользователь {username} уже существует!")
            return

        # Хэшируем пароль
        hashed_pw = generate_password_hash(password)
        
        # Считаем дату отключения, если указано количество дней
        expiration_date = None
        if days_valid:
            expiration_date = datetime.now() + timedelta(days=days_valid)

        new_user = User(
            username=username, 
            password_hash=hashed_pw, 
            expires_at=expiration_date
        )
        
        db.session.add(new_user)
        db.session.commit()
        
        if days_valid:
            print(f"[+] Временный аккаунт {username} создан! Истекает: {expiration_date.strftime('%Y-%m-%d %H:%M')}")
        else:
            print(f"[+] Постоянный аккаунт {username} успешно создан!")

if __name__ == '__main__':
    print("--- УПРАВЛЕНИЕ ДОСТУПОМ ---")
    while True:
        uname = input("Введите логин (или 'q' для выхода): ")
        if uname.lower() == 'q':
            break
            
        pwd = input("Введите пароль: ")
        
        temp_input = input("Срок действия в днях (нажми Enter, если аккаунт навсегда): ")
        days = int(temp_input) if temp_input.strip() else None
        
        create_user(uname, pwd, days)
        print("-" * 30)