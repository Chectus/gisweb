import os
import glob
import subprocess
from datetime import datetime

# --- НАСТРОЙКИ ---
BACKUP_DIR = '/home/cmp_mpi_2026/cloud_data/__SYSTEM_CRITICAL_DO_NOT_TOUCH__'
MAX_BACKUPS = 30 # Храним ровно месяц

# Строка подключения к PostgreSQL (Точно такая же, как в .env файле)
DB_URL = "postgresql://geo_user:my_secure_password@localhost:5432/geo_db"

def cleanup_old_backups(backup_dir):
    # Ищем все файлы бэкапов с новым расширением .dump
    search_pattern = os.path.join(backup_dir, 'users_backup_*.dump')
    backups = glob.glob(search_pattern)
    
    # Сортируем файлы по дате (самые старые в начале)
    backups.sort(key=os.path.getmtime)
    
    # Удаляем старые, если превышен лимит
    while len(backups) > MAX_BACKUPS:
        oldest_backup = backups.pop(0)
        os.remove(oldest_backup)
        print(f"[-] Удален старый бэкап: {os.path.basename(oldest_backup)}")

if __name__ == '__main__':
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
        
    # Генерируем имя с датой и временем
    date_str = datetime.now().strftime('%Y-%m-%d_%H-%M')
    backup_filename = f'users_backup_{date_str}.dump'
    backup_file_path = os.path.join(BACKUP_DIR, backup_filename)
    
    print(f"[{datetime.now()}] Начинаю создание бэкапа PostgreSQL...")
    
    try:
        # Вызываем системную утилиту pg_dump
        # -F c : указывает на custom формат (сжатый бинарный, идеально для бэкапов)
        # -f : указывает путь, куда сохранить файл
        result = subprocess.run(
            ['pg_dump', DB_URL, '-F', 'c', '-f', backup_file_path],
            check=True,
            capture_output=True,
            text=True
        )
        print(f"[{datetime.now()}] Бэкап успешно создан: {backup_filename}")
        
        # Если бэкап создался без ошибок, чистим старые файлы
        cleanup_old_backups(BACKUP_DIR)
        
    except subprocess.CalledProcessError as e:
        # Если база недоступна или пароль неверный, скрипт выведет ошибку
        print(f"[{datetime.now()}] АЛАРМ! Ошибка при создании бэкапа!")
        print(f"Детали ошибки: {e.stderr}")