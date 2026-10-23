import os
import glob
import subprocess
from datetime import datetime
from dotenv import load_dotenv

# Загружаем переменные из .env из папки проекта
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))

# --- НАСТРОЙКИ ---
BACKUP_DIR = '/home/cmp_mpi_2026/cloud_data/__SYSTEM_CRITICAL_DO_NOT_TOUCH__'
MAX_BACKUPS = 30  # Храним ровно 30 реальных бэкапов

# Берем точно ту же строку подключения, на которой работает сам сайт
DB_URL = os.environ.get('DATABASE_URL')

def cleanup_old_backups(backup_dir):
    search_pattern = os.path.join(backup_dir, 'users_backup_*.dump')
    # Учитываем и оставляем только непустые файлы (> 0 байт)
    backups = [f for f in glob.glob(search_pattern) if os.path.getsize(f) > 0]
    backups.sort(key=os.path.getmtime)
    
    while len(backups) > MAX_BACKUPS:
        oldest_backup = backups.pop(0)
        os.remove(oldest_backup)
        print(f"[-] Удален старый бэкап: {os.path.basename(oldest_backup)}")

if __name__ == '__main__':
    if not DB_URL:
        print(f"[{datetime.now()}] АЛАРМ! В файле .env не найден DATABASE_URL!")
        exit(1)

    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
        
    date_str = datetime.now().strftime('%Y-%m-%d_%H-%M')
    backup_filename = f'users_backup_{date_str}.dump'
    backup_file_path = os.path.join(BACKUP_DIR, backup_filename)
    
    print(f"[{datetime.now()}] Начинаю создание бэкапа PostgreSQL...")
    
    try:
        subprocess.run(
            ['pg_dump', DB_URL, '-F', 'c', '-f', backup_file_path],
            check=True,
            capture_output=True,
            text=True
        )
        
        # Проверяем, что файл реально весит больше 0 байт
        file_size = os.path.getsize(backup_file_path)
        if file_size == 0:
            os.remove(backup_file_path)
            print(f"[{datetime.now()}] АЛАРМ! Файл бэкапа оказался пустым (0 B) и был удален.")
        else:
            print(f"[{datetime.now()}] Бэкап успешно создан: {backup_filename} ({file_size // 1024} KB)")
            cleanup_old_backups(BACKUP_DIR)
        
    except subprocess.CalledProcessError as e:
        print(f"[{datetime.now()}] АЛАРМ! Ошибка pg_dump при создании бэкапа!")
        print(f"Детали ошибки: {e.stderr}")
        # Сносим пустой 0-байтовый файл, который успел создать pg_dump
        if os.path.exists(backup_file_path):
            os.remove(backup_file_path)