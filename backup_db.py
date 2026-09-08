import os
import shutil
import sqlite3
from datetime import datetime

# --- НАСТРОЙКИ ПУТЕЙ (ОБЯЗАТЕЛЬНО ПОМЕНЯЙ ПОД СЕБЯ) ---
# Путь к текущей базе (может быть gis_project/users.db или gis_project/instance/users.db)
# --- НАСТРОЙКИ ПУТЕЙ ---
DB_PATH = '/home/cmp_mpi_2026/gis_project/instance/users.db' 
BACKUP_DIR = '/home/cmp_mpi_2026/cloud_data/__SYSTEM_CRITICAL_DO_NOT_TOUCH__' 
BACKUP_FILE = os.path.join(BACKUP_DIR, 'users_backup.db')

def is_db_valid(path):
    # 1. Проверяем, существует ли файл и весит ли он больше 8 КБ (пустая база весит мало)
    if not os.path.exists(path) or os.path.getsize(path) < 8192:
        return False
    
    # 2. Пробуем подключиться и посчитать юзеров (защита от битого файла)
    try:
        conn = sqlite3.connect(path)
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM user") # 'user' - название таблицы в БД
        count = cursor.fetchone()[0]
        conn.close()
        return count > 0 # Если юзеров больше нуля - база живая
    except Exception as e:
        return False

if __name__ == '__main__':
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
        
    if is_db_valid(DB_PATH):
        # shutil.copy2 перезаписывает файл с сохранением метаданных
        shutil.copy2(DB_PATH, BACKUP_FILE) 
        print(f"[{datetime.now()}] Бэкап успешно обновлен!")
    else:
        print(f"[{datetime.now()}] АЛАРМ! База пустая или повреждена! Копирование отменено.")