import os
import sys
from app import app, db, User, Role, UserLayer
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta

def init_roles():
    """Создает базовые роли в пустой БД, если их нет"""
    with app.app_context():
        db.create_all() 
        
        if Role.query.count() == 0:
            roles = [
                # Админ: Раздает задачи, но сам их не получает
                Role(name='admin', can_assign_tasks=True, can_receive_tasks=False),
                
                # Лаборант: Получает задачи, но сам не раздает
                Role(name='worker', can_assign_tasks=False, can_receive_tasks=True),
                
                # Инвестор: Ничего не может в плане задач
                Role(name='viewer', can_assign_tasks=False, can_receive_tasks=False)
            ]
            db.session.bulk_save_objects(roles)
            db.session.commit()
            print("[+] Базовые роли (admin, worker, viewer) успешно инициализированы в БД.")

def create_user(username, password, role_id, days_valid=None, email=None, layers_input="*"):
    with app.app_context():
        if User.query.filter_by(username=username).first():
            print(f"[-] Пользователь {username} уже существует!")
            return

        hashed_pw = generate_password_hash(password)
        expiration_date = datetime.now() + timedelta(days=days_valid) if days_valid else None
        has_all = (layers_input.strip() == "*")

        new_user = User(
            username=username, 
            password_hash=hashed_pw, 
            expires_at=expiration_date,
            role_id=role_id,
            email=email,
            has_all_layers=has_all
        )
        db.session.add(new_user)
        db.session.commit() # Сохраняем, чтобы получить user.id для слоев
        
        # Если слои указаны конкретные, прописываем их в UserLayer
        if not has_all:
            try:
                layer_ids = [int(x.strip()) for x in layers_input.split(',')]
                for lid in layer_ids:
                    db.session.add(UserLayer(user_id=new_user.id, layer_id=lid))
                db.session.commit()
            except ValueError:
                print("[-] Ошибка парсинга слоев. Пользователь создан без доступа к закрытым слоям.")

        role = Role.query.get(role_id)
        auth_type = f"с 2FA ({email})" if email else "без 2FA"
        
        if days_valid:
            print(f"[+] Временный {role.name} '{username}' ({auth_type}) создан! Истекает: {expiration_date.strftime('%Y-%m-%d %H:%M')}")
        else:
            print(f"[+] Постоянный {role.name} '{username}' ({auth_type}) успешно создан!")

def delete_user(username):
    with app.app_context():
        user_to_delete = User.query.filter_by(username=username).first()
        if not user_to_delete:
            print(f"[-] Ошибка: Пользователь '{username}' не найден в базе!")
            return
            
        db.session.delete(user_to_delete)
        db.session.commit()
        print(f"[+] Пользователь '{username}' был успешно удален (связи со слоями удалены каскадно).")

def edit_user():
    print("\n--- РЕДАКТИРОВАНИЕ ПОЛЬЗОВАТЕЛЯ ---")
    uname_search = input("Введите логин пользователя для редактирования: ")
    
    with app.app_context():
        target_user = User.query.filter_by(username=uname_search).first()
        
        if not target_user:
            print(f"[-] Ошибка: Пользователь '{uname_search}' не найден в базе!")
            return
            
        print(f"\n[ Редактирование пользователя: {target_user.username} ]")
        print("💡 Подсказка: Нажимайте Enter, чтобы оставить текущее значение без изменений.")
        
        # 1. Логин
        new_uname = input(f"Новый логин [{target_user.username}]: ")
        if new_uname.strip():
            if new_uname.strip() != target_user.username and User.query.filter_by(username=new_uname.strip()).first():
                print("[-] Ошибка: Этот логин уже занят другим пользователем!")
            else:
                target_user.username = new_uname.strip()
                
        # 2. Email
        curr_email = target_user.email if target_user.email else "Нет"
        new_email = input(f"Новый Email для 2FA [{curr_email}] (введите 'clear' чтобы удалить почту): ")
        if new_email.strip():
            if new_email.strip().lower() == 'clear':
                target_user.email = None
            else:
                target_user.email = new_email.strip()
                
        # 3. Пароль
        new_pwd = input("Новый пароль [*** скрыто ***]: ")
        if new_pwd.strip():
            target_user.password_hash = generate_password_hash(new_pwd.strip())
            
        # 4. Роль
        print("\nДоступные роли:")
        print("1 - Admin (Руководитель)")
        print("2 - Worker (Лаборант/Геолог)")
        print("3 - Viewer (Инвестор)")
        role_map = {'1': 'admin', '2': 'worker', '3': 'viewer'}
        new_role_choice = input(f"Выберите новую роль (1-3) [Текущая: {target_user.role.name}]: ")
        
        if new_role_choice.strip() in role_map:
            role_obj = Role.query.filter_by(name=role_map[new_role_choice.strip()]).first()
            if role_obj:
                target_user.role_id = role_obj.id
            
        # 5. Таймер
        curr_exp = target_user.expires_at.strftime('%Y-%m-%d %H:%M') if target_user.expires_at else "Бессрочный"
        new_days = input(f"\nДобавить срок в днях от ТЕКУЩЕГО момента [{curr_exp}] (введите 'inf' для бессрочного): ")
        if new_days.strip():
            if new_days.strip().lower() == 'inf':
                target_user.expires_at = None
            elif new_days.strip().isdigit():
                target_user.expires_at = datetime.now() + timedelta(days=int(new_days.strip()))
            else:
                print("[-] Ошибка: Введено не число, срок действия не изменен.")
                
        # 6. Слои (дата-румы)
        curr_layers = "*" if target_user.has_all_layers else ",".join([str(l.layer_id) for l in target_user.specific_layers])
        new_layers = input(f"Доступные слои (ID через запятую, либо * для всех) [{curr_layers}]: ")
        if new_layers.strip():
            val = new_layers.strip()
            # Очищаем старые привязки
            UserLayer.query.filter_by(user_id=target_user.id).delete()
            
            if val == '*':
                target_user.has_all_layers = True
            else:
                target_user.has_all_layers = False
                try:
                    layers_list = [int(x.strip()) for x in val.split(',')]
                    for lid in layers_list:
                        db.session.add(UserLayer(user_id=target_user.id, layer_id=lid))
                except ValueError:
                    print("[-] Ошибка ввода слоев. Права сброшены, доступ закрыт.")

        db.session.commit()
        print(f"[+] Пользователь '{target_user.username}' успешно обновлен!")

def list_users():
    with app.app_context():
        users = User.query.all()
        
        print(f"\n--- СПИСОК АККАУНТОВ (Всего пользователей: {len(users)}) ---")
        if not users:
            print("База пуста. Самое время кого-нибудь добавить!")
        else:
            for u in users:
                status = "Бессрочный" if u.expires_at is None else u.expires_at.strftime('%d.%m.%Y %H:%M')
                mail_status = u.email if u.email else "Нет"
                layers = "*" if u.has_all_layers else ",".join([str(l.layer_id) for l in u.specific_layers])
                role_name = u.role.name if u.role else "Unknown"
                
                print(f"ID: {u.id} | Логин: {u.username} | Роль: {role_name} | Почта: {mail_status} | Годен до: {status} | Слои: {layers}")
        print("-" * 50)

def restore_database():
    print("\n--- ВОССТАНОВЛЕНИЕ БАЗЫ ДАННЫХ ИЗ ОБЛАКА ---")
    print("[-] ВНИМАНИЕ: Проект переведен на PostgreSQL.")
    print("[-] Прямое копирование файлов .db больше не работает.")
    print("[-] Скрипт облачных бэкапов (pg_dump / pg_restore) будет настроен позже.")

if __name__ == '__main__':
    # При запуске скрипта сразу проверяем и создаем базовую структуру БД
    init_roles()
    
    while True:
        print("\n=== ГЛАВНОЕ МЕНЮ УПРАВЛЕНИЯ ДОСТУПОМ ===")
        print("1. Посмотреть всех пользователей")
        print("2. Создать нового пользователя")
        print("3. Удалить пользователя")
        print("4. Редактировать пользователя")
        print("5. Восстановить базу данных (Отключено)")
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
            
            print("\nВыберите роль:")
            print("1 - Admin (Руководитель)")
            print("2 - Worker (Лаборант/Геолог)")
            print("3 - Viewer (Инвестор)")
            role_choice = input("Ваш выбор (1-3): ")
            
            role_map = {'1': 'admin', '2': 'worker', '3': 'viewer'}
            if role_choice.strip() not in role_map:
                print("[-] Неверный выбор роли. Отмена.")
                continue
                
            with app.app_context():
                role_obj = Role.query.filter_by(name=role_map[role_choice.strip()]).first()
                role_id = role_obj.id
            
            temp_input = input("Срок действия в днях (нажми Enter, если аккаунт навсегда): ")
            days = int(temp_input) if temp_input.strip() else None
            
            email_input = input("Введите email для 2FA (или нажми Enter, если это общий аккаунт без 2FA): ")
            email_val = email_input.strip() if email_input.strip() else None
            
            layers_input = input("Доступные слои (ID через запятую, либо * для всех) [*]: ")
            if not layers_input.strip():
                layers_input = "*"
            
            create_user(uname, pwd, role_id, days, email_val, layers_input)
            
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