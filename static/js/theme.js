document.addEventListener('DOMContentLoaded', () => {
    // Ищем кнопку переключения темы (если она есть на текущей странице)
    const themeToggleBtn = document.getElementById('theme-toggle');
    const themeIcon = document.getElementById('theme-icon');
    const body = document.body;

    // Функция применения иконки
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

    // Если кнопка есть на странице, вешаем на нее клик
    if (themeToggleBtn) {
        // При загрузке страницы ставим правильную иконку
        updateIcon();

        themeToggleBtn.addEventListener('click', () => {
            body.classList.toggle('dark-theme');
            updateIcon();
            
            // Сохраняем выбор
            if (body.classList.contains('dark-theme')) {
                localStorage.setItem('app-theme', 'dark');
            } else {
                localStorage.setItem('app-theme', 'light');
            }
        });
    }
});