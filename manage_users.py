import os
import shutil
from app import app, db, User
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta
import glob

# --- НАСТРОЙКИ ПУТЕЙ ДЛЯ ВОССТАНОВЛЕНИЯ БД ---
BACKUP_DIR = '/home/cmp_mpi_2026/cloud_data/__SYSTEM_CRITICAL_DO_NOT_TOUCH__'
TARGET_DB_PATH = '/home/cmp_mpi_2026/gis_project/instance/users.db'

def create_user(username, password, days_valid=None, is_admin=False, email=None, allowed_layers="*"):
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
            email=email,
            allowed_layers=allowed_layers
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

def edit_user():
    print("\n--- РЕДАКТИРОВАНИЕ ПОЛЬЗОВАТЕЛЯ ---")
    uname_search = input("Введите логин пользователя для редактирования: ")
    
    with app.app_context():
        db.create_all()
        target_user = User.query.filter_by(username=uname_search).first()
        
        if not target_user:
            print(f"[-] Ошибка: Пользователь '{uname_search}' не найден в базе!")
            return
            
        print(f"\n[ Редактирование пользователя: {target_user.username} ]")
        print("💡 Подсказка: Нажимайте Enter, чтобы оставить текущее значение без изменений.")
        
        # Логин
        new_uname = input(f"Новый логин [{target_user.username}]: ")
        if new_uname.strip():
            if new_uname.strip() != target_user.username and User.query.filter_by(username=new_uname.strip()).first():
                print("[-] Ошибка: Этот логин уже занят другим пользователем!")
            else:
                target_user.username = new_uname.strip()
                
        # Email
        curr_email = target_user.email if target_user.email else "Нет"
        new_email = input(f"Новый Email для 2FA [{curr_email}] (введите 'clear' чтобы удалить почту): ")
        if new_email.strip():
            if new_email.strip().lower() == 'clear':
                target_user.email = None
            else:
                target_user.email = new_email.strip()
                
        # Пароль
        new_pwd = input("Новый пароль [*** скрыто ***]: ")
        if new_pwd.strip():
            target_user.password_hash = generate_password_hash(new_pwd.strip())
            
        # Роль
        curr_role = "y" if target_user.is_admin else "n"
        new_role = input(f"Сделать администратором? (y/n) [{curr_role}]: ")
        if new_role.strip():
            target_user.is_admin = new_role.strip().lower() in ['y', 'yes', 'д', 'да']
            
        # Таймер
        curr_exp = target_user.expires_at.strftime('%Y-%m-%d %H:%M') if target_user.expires_at else "Бессрочный"
        new_days = input(f"Добавить срок в днях от ТЕКУЩЕГО момента [{curr_exp}] (введите 'inf' для бессрочного): ")
        if new_days.strip():
            if new_days.strip().lower() == 'inf':
                target_user.expires_at = None
            elif new_days.strip().isdigit():
                target_user.expires_at = datetime.now() + timedelta(days=int(new_days.strip()))
            else:
                print("[-] Ошибка: Введено не число, срок действия не изменен.")
                
        # Слои (дата-румы)
        curr_layers = target_user.allowed_layers
        new_layers = input(f"Доступные слои (ID через запятую, либо * для всех) [{curr_layers}]: ")
        if new_layers.strip():
            val = new_layers.strip()
            if val == '*':
                target_user.allowed_layers = "*"
            else:
                try:
                    layers_list = [int(x.strip()) for x in val.split(',')]
                    target_user.allowed_layers = layers_list
                except ValueError:
                    print("[-] Ошибка ввода слоев. Права не изменены. Нужно вводить только цифры через запятую.")

        db.session.commit()
        print(f"[+] Пользователь '{target_user.username}' успешно обновлен!")

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
                layers = u.allowed_layers if u.allowed_layers != "*" else "Все (*)"
                print(f"ID: {u.id} | Логин: {u.username} | Роль: {role} | Почта: {mail_status} | Годен до: {status} | Слои: {layers}")
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
        print("4. Редактировать пользователя")
        print("5. Восстановить базу данных из резервной копии")
        print("0. Выйти")
        
        choice = input("Выберите действие (0-5): ")
        
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
            
            # --- НОВОЕ: Запрос прав на слои при создании ---
            layers_input = input("Доступные слои (ID через запятую, либо * для всех) [*]: ")
            if layers_input.strip() and layers_input.strip() != '*':
                try:
                    allowed_layers = [int(x.strip()) for x in layers_input.split(',')]
                except ValueError:
                    print("[-] Ошибка ввода слоев. Выданы права на все слои (*).")
                    allowed_layers = "*"
            else:
                allowed_layers = "*"
            
            create_user(uname, pwd, days, is_admin_flag, email_val, allowed_layers)
            
        elif choice == '3':
            print("\n--- УДАЛЕНИЕ ---")
            uname = input("Введите логин пользователя, которого нужно удалить: ")
            
            confirm = input(f"Вы уверены, что хотите безвозвратно удалить '{uname}'? (y/n): ")
            if confirm.lower() in ['y', 'yes', 'д', 'да']:
                delete_user(uname)
            else:
                print("[-] Удаление отменено.")
                
        elif choice == '4':
            edit_user()
            
        elif choice == '5':
            restore_database()
                
        else:
            print("[-] Неверный выбор. Пожалуйста, введите цифру от 0 до 5.")