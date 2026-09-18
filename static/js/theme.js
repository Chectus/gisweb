/**
 * Файл: theme.js (JavaScript)
 * Описание: Клиентский контроллер цветовой темы приложения.
 * Управляет переключением между светлой и темной темами, синхронизацией иконок 
 * и сохранением пользовательских предпочтений в браузере (localStorage).
 */

document.addEventListener('DOMContentLoaded', () => {
    
    // Инициализация элементов управления темой
    const themeToggleBtn = document.getElementById('theme-toggle');
    const themeIcon = document.getElementById('theme-icon');
    const body = document.body;

    // Синхронизация графического индикатора с активным состоянием интерфейса
    function updateIcon() {
        if (!themeIcon) return;
        
        if (body.classList.contains('dark-theme')) {
            themeIcon.classList.remove('bi-moon-stars-fill');
            themeIcon.classList.add('bi-sun-fill');
        } else {
            themeIcon.classList.remove('bi-sun-fill');
            themeIcon.classList.add('bi-moon-stars-fill');
        }
    }

    // Регистрация обработчиков событий (выполняется только при наличии интерфейса управления)
    if (themeToggleBtn) {
        
        updateIcon();

        themeToggleBtn.addEventListener('click', () => {
            body.classList.toggle('dark-theme');
            updateIcon();
            
            // Персистентное сохранение выбранного режима
            if (body.classList.contains('dark-theme')) {
                localStorage.setItem('app-theme', 'dark');
            } else {
                localStorage.setItem('app-theme', 'light');
            }
        });
    }
});