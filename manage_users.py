import os
import shutil
from app import app, db, User
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta
import glob

# --- НАСТРОЙКИ ПУТЕЙ ДЛЯ ВОССТАНОВЛЕНИЯ БД ---
BACKUP_DIR = '/home/cmp_mpi_2026/cloud_data/__SYSTEM_CRITICAL_DO_NOT_TOUCH__'
TARGET_DB_PATH = '/home/cmp_mpi_2026/gis_project/instance/users.db'

def create_user(username, password, days_valid=None, is_admin=False, email=None):
    with app.app_context():
        db.create_all() 
        
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
            is_admin=is_admin,
            email=email
        )
        
        db.session.add(new_user)
        db.session.commit()
        
        role = "Администратор" if is_admin else "Пользователь"
        auth_type = f"с 2FA ({email})" if email else "без 2FA"
        
        if days_valid:
            print(f"[+] Временный {role} '{username}' ({auth_type}) создан! Истекает: {expiration_date.strftime('%Y-%m-%d %H:%M')}")
        else:
            print(f"[+] Постоянный {role} '{username}' ({auth_type}) успешно создан!")

def delete_user(username):
    with app.app_context():
        db.create_all() 
        
        user_to_delete = User.query.filter_by(username=username).first()
        
        if not user_to_delete:
            print(f"[-] Ошибка: Пользователь '{username}' не найден в базе!")
            return
            
        db.session.delete(user_to_delete)
        db.session.commit()
        print(f"[+] Пользователь '{username}' был успешно удален и больше не сможет зайти на карту.")

def list_users():
    with app.app_context():
        db.create_all() 
        
        users = User.query.all()
        
        print(f"\n--- СПИСОК АККАУНТОВ (Всего пользователей: {len(users)}) ---")
        if not users:
            print("База пуста. Самое время кого-нибудь добавить!")
        else:
            for u in users:
                status = "Бессрочный" if u.expires_at is None else u.expires_at.strftime('%d.%m.%Y %H:%M')
                role = "Админ" if u.is_admin else "Гость"
                mail_status = u.email if u.email else "Нет"
                print(f"ID: {u.id} | Логин: {u.username} | Роль: {role} | Почта (2FA): {mail_status} | Годен до: {status}")
        print("-" * 50)

def restore_database():
    print("\n--- ВОССТАНОВЛЕНИЕ БАЗЫ ДАННЫХ ИЗ ОБЛАКА ---")
    
    if not os.path.exists(BACKUP_DIR):
        print(f"[-] ОШИБКА: Папка с бэкапами не найдена:\n{BACKUP_DIR}")
        return
        
    # Ищем все бэкапы
    search_pattern = os.path.join(BACKUP_DIR, 'users_backup_*.db')
    backups = glob.glob(search_pattern)
    
    if not backups:
        print("[-] В облаке нет доступных бэкапов для восстановления!")
        return
        
    # Сортируем от самых старых к самым новым
    backups.sort(key=os.path.getmtime)
    
    print("Доступные резервные копии:")
    for i, backup_path in enumerate(backups, 1):
        filename = os.path.basename(backup_path)
        # Получаем размер в килобайтах
        size_kb = os.path.getsize(backup_path) // 1024
        print(f"{i}. {filename} ({size_kb} KB)")
        
    choice = input(f"\nВыберите номер бэкапа (1-{len(backups)}) или 0 для отмены: ")
    
    try:
        choice_idx = int(choice)
        if choice_idx == 0:
            print("[-] Восстановление отменено.")
            return
            
        if 1 <= choice_idx <= len(backups):
            selected_backup = backups[choice_idx - 1]
            selected_filename = os.path.basename(selected_backup)
            
            print(f"\nВНИМАНИЕ! Текущая база данных будет ПЕРЕЗАПИСАНА файлом '{selected_filename}'.")
            confirm = input("Точно продолжить? (y/n): ")
            
            if confirm.lower() in ['y', 'yes', 'д', 'да']:
                # Копируем выбранный файл и автоматом переименовываем его обратно в users.db
                shutil.copy2(selected_backup, TARGET_DB_PATH)
                print(f"[+] БД успешно восстановлена из {selected_filename}!")
                print("[!] Обязательно перезапусти Flask-сервер (app.py) в tmux, чтобы изменения вступили в силу.")
            else:
                print("[-] Восстановление отменено.")
        else:
            print("[-] Ошибка: Неверный номер бэкапа!")
    except ValueError:
        print("[-] Ошибка: Нужно ввести число!")

if __name__ == '__main__':
    while True:
        print("\n=== ГЛАВНОЕ МЕНЮ УПРАВЛЕНИЯ ДОСТУПОМ ===")
        print("1. Посмотреть всех пользователей")
        print("2. Создать нового пользователя")
        print("3. Удалить пользователя")
        print("4. Восстановить базу данных из резервной копии")
        print("0. Выйти")
        
        choice = input("Выберите действие (0-4): ")
        
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
            
            email_input = input("Введите email для 2FA (или нажми Enter, если это общий аккаунт без 2FA): ")
            email_val = email_input.strip() if email_input.strip() else None
            
            admin_input = input("Сделать пользователя администратором? (y/n, по умолчанию n): ")
            is_admin_flag = admin_input.lower() in ['y', 'yes', 'д', 'да']
            
            create_user(uname, pwd, days, is_admin_flag, email_val)
            
        elif choice == '3':
            print("\n--- УДАЛЕНИЕ ---")
            uname = input("Введите логин пользователя, которого нужно удалить: ")
            
            confirm = input(f"Вы уверены, что хотите безвозвратно удалить '{uname}'? (y/n): ")
            if confirm.lower() in ['y', 'yes', 'д', 'да']:
                delete_user(uname)
            else:
                print("[-] Удаление отменено.")
                
        elif choice == '4':
            restore_database()
                
        else:
            print("[-] Неверный выбор. Пожалуйста, введите цифру от 0 до 4.")