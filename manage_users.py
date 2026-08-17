from app import app, db, User
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta

def create_user(username, password, days_valid=None, is_admin=False):
    with app.app_context():
        if User.query.filter_by(username=username).first():
            print(f"[-] Пользователь {username} уже существует!")
            return

        hashed_pw = generate_password_hash(password)
        
        expiration_date = None
        if days_valid:
            expiration_date = datetime.now() + timedelta(days=days_valid)

        new_user = User(
            username=username, 
            password_hash=hashed_pw, 
            expires_at=expiration_date,
            is_admin=is_admin
        )
        
        db.session.add(new_user)
        db.session.commit()
        
        role = "Администратор" if is_admin else "Пользователь"
        if days_valid:
            print(f"[+] Временный {role} '{username}' создан! Истекает: {expiration_date.strftime('%Y-%m-%d %H:%M')}")
        else:
            print(f"[+] Постоянный {role} '{username}' успешно создан!")

def delete_user(username):
    with app.app_context():
        user_to_delete = User.query.filter_by(username=username).first()
        
        if not user_to_delete:
            print(f"[-] Ошибка: Пользователь '{username}' не найден в базе!")
            return
            
        db.session.delete(user_to_delete)
        db.session.commit()
        print(f"[+] Пользователь '{username}' был успешно удален и больше не сможет зайти на карту.")

def list_users():
    with app.app_context():
        users = User.query.all()
        
        print(f"\n--- СПИСОК АККАУНТОВ (Всего пользователей: {len(users)}) ---")
        if not users:
            print("База пуста. Самое время кого-нибудь добавить!")
        else:
            for u in users:
                status = "Бессрочный" if u.expires_at is None else u.expires_at.strftime('%d.%m.%Y %H:%M')
                role = "Админ" if u.is_admin else "Геолог"
                print(f"ID: {u.id} | Логин: {u.username} | Роль: {role} | Годен до: {status}")
        print("-" * 50)

if __name__ == '__main__':
    while True:
        print("\n=== ГЛАВНОЕ МЕНЮ УПРАВЛЕНИЯ ДОСТУПОМ ===")
        print("1. Посмотреть всех пользователей")
        print("2. Создать нового пользователя")
        print("3. Удалить пользователя")
        print("0. Выйти")
        
        choice = input("Выберите действие (0-3): ")
        
        if choice == '0' or choice.lower() == 'q':
            print("Завершение работы. Удачи!")
            break
            
        elif choice == '1':
            list_users()
            
        elif choice == '2':
            print("\n--- СОЗДАНИЕ ---")
            uname = input("Введите логин: ")
            if not uname.strip():
                print("[-] Логин не может быть пустым!")
                continue
                
            pwd = input("Введите пароль: ")
            
            temp_input = input("Срок действия в днях (нажми Enter, если аккаунт навсегда): ")
            days = int(temp_input) if temp_input.strip() else None
            
            admin_input = input("Сделать пользователя администратором? (y/n, по умолчанию n): ")
            is_admin_flag = admin_input.lower() in ['y', 'yes', 'д', 'да']
            
            create_user(uname, pwd, days, is_admin_flag)
            
        elif choice == '3':
            print("\n--- УДАЛЕНИЕ ---")
            uname = input("Введите логин пользователя, которого нужно удалить: ")
            
            # Небольшая защита от случайного удаления
            confirm = input(f"Вы уверены, что хотите безвозвратно удалить '{uname}'? (y/n): ")
            if confirm.lower() in ['y', 'yes', 'д', 'да']:
                delete_user(uname)
            else:
                print("[-] Удаление отменено.")
                
        else:
            print("[-] Неверный выбор. Пожалуйста, введите цифру от 0 до 3.")