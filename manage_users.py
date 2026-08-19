from app import app, db, User
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta

# Добавили email=None в параметры[cite: 5]
def create_user(username, password, days_valid=None, is_admin=False, email=None):
    with app.app_context():
        if User.query.filter_by(username=username).first():
            print(f"[-] Пользователь {username} уже существует!") #[cite: 5]
            return

        hashed_pw = generate_password_hash(password) #[cite: 5]
        
        expiration_date = None #[cite: 5]
        if days_valid: #[cite: 5]
            expiration_date = datetime.now() + timedelta(days=days_valid) #[cite: 5]

        # Передаем email в базу данных[cite: 5]
        new_user = User(
            username=username, 
            password_hash=hashed_pw, 
            expires_at=expiration_date,
            is_admin=is_admin,
            email=email
        )
        
        db.session.add(new_user) #[cite: 5]
        db.session.commit() #[cite: 5]
        
        role = "Администратор" if is_admin else "Пользователь" #[cite: 5]
        auth_type = f"с 2FA ({email})" if email else "без 2FA"
        
        if days_valid: #[cite: 5]
            print(f"[+] Временный {role} '{username}' ({auth_type}) создан! Истекает: {expiration_date.strftime('%Y-%m-%d %H:%M')}") #[cite: 5]
        else: #[cite: 5]
            print(f"[+] Постоянный {role} '{username}' ({auth_type}) успешно создан!") #[cite: 5]

def delete_user(username):
    with app.app_context():
        user_to_delete = User.query.filter_by(username=username).first() #[cite: 5]
        
        if not user_to_delete: #[cite: 5]
            print(f"[-] Ошибка: Пользователь '{username}' не найден в базе!") #[cite: 5]
            return
            
        db.session.delete(user_to_delete) #[cite: 5]
        db.session.commit() #[cite: 5]
        print(f"[+] Пользователь '{username}' был успешно удален и больше не сможет зайти на карту.") #[cite: 5]

def list_users():
    with app.app_context():
        users = User.query.all() #[cite: 5]
        
        print(f"\n--- СПИСОК АККАУНТОВ (Всего пользователей: {len(users)}) ---") #[cite: 5]
        if not users: #[cite: 5]
            print("База пуста. Самое время кого-нибудь добавить!") #[cite: 5]
        else: #[cite: 5]
            for u in users: #[cite: 5]
                status = "Бессрочный" if u.expires_at is None else u.expires_at.strftime('%d.%m.%Y %H:%M') #[cite: 5]
                role = "Админ" if u.is_admin else "Геолог" #[cite: 5]
                mail_status = u.email if u.email else "Нет"
                print(f"ID: {u.id} | Логин: {u.username} | Роль: {role} | Почта (2FA): {mail_status} | Годен до: {status}")
        print("-" * 50) #[cite: 5]

if __name__ == '__main__':
    while True:
        print("\n=== ГЛАВНОЕ МЕНЮ УПРАВЛЕНИЯ ДОСТУПОМ ===") #[cite: 5]
        print("1. Посмотреть всех пользователей") #[cite: 5]
        print("2. Создать нового пользователя") #[cite: 5]
        print("3. Удалить пользователя") #[cite: 5]
        print("0. Выйти") #[cite: 5]
        
        choice = input("Выберите действие (0-3): ") #[cite: 5]
        
        if choice == '0' or choice.lower() == 'q': #[cite: 5]
            print("Завершение работы. Удачи!") #[cite: 5]
            break
            
        elif choice == '1': #[cite: 5]
            list_users() #[cite: 5]
            
        elif choice == '2': #[cite: 5]
            print("\n--- СОЗДАНИЕ ---") #[cite: 5]
            uname = input("Введите логин: ") #[cite: 5]
            if not uname.strip(): #[cite: 5]
                print("[-] Логин не может быть пустым!") #[cite: 5]
                continue
                
            pwd = input("Введите пароль: ") #[cite: 5]
            
            temp_input = input("Срок действия в днях (нажми Enter, если аккаунт навсегда): ") #[cite: 5]
            days = int(temp_input) if temp_input.strip() else None #[cite: 5]
            
            # НОВЫЙ ЗАПРОС ПОЧТЫ
            email_input = input("Введите email для 2FA (или нажми Enter, если это общий аккаунт без 2FA): ")
            email_val = email_input.strip() if email_input.strip() else None
            
            admin_input = input("Сделать пользователя администратором? (y/n, по умолчанию n): ") #[cite: 5]
            is_admin_flag = admin_input.lower() in ['y', 'yes', 'д', 'да'] #[cite: 5]
            
            # Передаем email_val в функцию
            create_user(uname, pwd, days, is_admin_flag, email_val)
            
        elif choice == '3': #[cite: 5]
            print("\n--- УДАЛЕНИЕ ---") #[cite: 5]
            uname = input("Введите логин пользователя, которого нужно удалить: ") #[cite: 5]
            
            confirm = input(f"Вы уверены, что хотите безвозвратно удалить '{uname}'? (y/n): ") #[cite: 5]
            if confirm.lower() in ['y', 'yes', 'д', 'да']: #[cite: 5]
                delete_user(uname) #[cite: 5]
            else: #[cite: 5]
                print("[-] Удаление отменено.") #[cite: 5]
                
        else: #[cite: 5]
            print("[-] Неверный выбор. Пожалуйста, введите цифру от 0 до 3.") #[cite: 5]