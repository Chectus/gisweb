├── app.py                 # Главный файл приложения (роутинг, базовая авторизация)  
├── README.md              # Документация разработчика  
└── templates/             # HTML-шаблоны (View)    
&nbsp;&nbsp;&nbsp;&nbsp;├── login.html         # Страница авторизации пользователей  
&nbsp;&nbsp;&nbsp;&nbsp;├── hub.html           # Главное меню (навигационный хаб проекта)  
&nbsp;&nbsp;&nbsp;&nbsp;├── docs.html          # Пользовательская документация по работе с ГИС  
&nbsp;&nbsp;&nbsp;&nbsp;├── map.html           # Ядро фронтенда: интерактивная веб-карта и ГИС-логика  
&nbsp;&nbsp;&nbsp;&nbsp;└── admin.html         # Панель администратора, для добавления/удаления аккаунтов  
└── static/             # Разделение стилей и скриптов       
&nbsp;&nbsp;&nbsp;&nbsp;└── css/            # Стили  
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└── style.css             # Главный стиль (оформление для всех страниц)  
&nbsp;&nbsp;&nbsp;&nbsp;└── js/             # Скрипты  
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;└── map_logic.js          # Скрипт для карты (логика прорисовки слоев, сапбордов и тд.)  
