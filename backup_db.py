import os
import shutil
import sqlite3
import glob
from datetime import datetime

# --- НАСТРОЙКИ ПУТЕЙ ---
DB_PATH = '/home/cmp_mpi_2026/gis_project/instance/users.db' 
BACKUP_DIR = '/home/cmp_mpi_2026/cloud_data/__SYSTEM_CRITICAL_DO_NOT_TOUCH__' 
MAX_BACKUPS = 30 # Храним ровно месяц

def is_db_valid(path):
    if not os.path.exists(path) or os.path.getsize(path) < 8192:
        return False
    try:
        conn = sqlite3.connect(path)
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM user")
        count = cursor.fetchone()[0]
        conn.close()
        return count > 0
    except Exception as e:
        return False

def cleanup_old_backups(backup_dir):
    # Ищем все файлы бэкапов в папке
    search_pattern = os.path.join(backup_dir, 'users_backup_*.db')
    backups = glob.glob(search_pattern)
    
    # Сортируем файлы по дате создания (самые старые в начале списка)
    backups.sort(key=os.path.getmtime)
    
    # Пока файлов больше 30, удаляем самый первый (самый старый)
    while len(backups) > MAX_BACKUPS:
        oldest_backup = backups.pop(0)
        os.remove(oldest_backup)
        print(f"[-] Удален старый бэкап: {os.path.basename(oldest_backup)}")

if __name__ == '__main__':
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
        
    if is_db_valid(DB_PATH):
        # Генерируем имя с датой (например: users_backup_2026-09-08.db)
        date_str = datetime.now().strftime('%Y-%m-%d')
        backup_filename = f'users_backup_{date_str}.db'
        backup_file_path = os.path.join(BACKUP_DIR, backup_filename)
        
        # Копируем базу
        shutil.copy2(DB_PATH, backup_file_path) 
        print(f"[{datetime.now()}] Бэкап успешно создан: {backup_filename}")
        
        # Запускаем чистку старых файлов
        cleanup_old_backups(BACKUP_DIR)
    else:
        print(f"[{datetime.now()}] АЛАРМ! База пустая или повреждена! Копирование отменено.")