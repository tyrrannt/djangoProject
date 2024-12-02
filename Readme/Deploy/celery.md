Для автоматического запуска и перезапуска планировщика Celery в Django можно использовать систему инициализации и управления службами, такую как systemd в Linux. systemd позволяет создать службу, которая будет автоматически запускать Celery при загрузке системы и перезапускать его каждый день.

Шаги для настройки автоматического запуска и перезапуска Celery с помощью systemd:
Создайте файл службы для Celery:

Создайте файл службы для Celery в директории /etc/systemd/system/. Например, назовите его **celery.service**.
```bash
sudo nano /etc/systemd/system/celery.service
```

Вставьте следующий контент в файл:
```ini
[Unit]
Description=Celery Service
After=network.target

[Service]
Type=forking
User=your_user
Group=your_group
Environment="PATH=/path/to/your/virtualenv/bin"
Environment="DJANGO_SETTINGS_MODULE=your_project.settings"
WorkingDirectory=/path/to/your/django/project
ExecStart=/path/to/your/virtualenv/bin/celery -A your_project worker -l info --beat
ExecReload=/bin/kill -HUP $MAINPID
ExecStop=/bin/kill -TERM $MAINPID
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Замените следующие переменные на соответствующие значения:

`your_user`: имя пользователя, от которого будет запускаться Celery.

`your_group`: группа пользователя.

`/path/to/your/virtualenv/bin`: путь к вашему виртуальному окружению.

`your_project.settings`: модуль настроек вашего Django проекта.

`/path/to/your/django/project`: путь к корневой директории вашего Django проекта.

`your_project`: имя вашего Django проекта.

Создайте таймер для ежедневного перезапуска Celery:

Создайте файл таймера для Celery в директории `/etc/systemd/system/`. Например, назовите его **celery.timer**.

```bash
sudo nano /etc/systemd/system/celery.timer
```

Вставьте следующий контент в файл:

```ini
[Unit]
Description=Celery Daily Restart Timer

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
```

Создайте файл службы для ежедневного перезапуска Celery:

Создайте файл службы для ежедневного перезапуска Celery в директории `/etc/systemd/system/`. Например, назовите его `celery-restart.service`.

```bash
sudo nano /etc/systemd/system/celery-restart.service
```

Вставьте следующий контент в файл:

```ini
[Unit]
Description=Restart Celery Service Daily

[Service]
Type=oneshot
ExecStart=/bin/systemctl restart celery.service
```

Включите и запустите службы:

Включите и запустите службу Celery и таймер:

```bash
sudo systemctl daemon-reload
sudo systemctl enable celery.service
sudo systemctl start celery.service
sudo systemctl enable celery.timer
sudo systemctl start celery.timer
```

Проверьте работу служб:

Проверьте, что службы запущены и работают корректно:

```bash
sudo systemctl status celery.service
sudo systemctl status celery.timer
```

Объяснение:
Файл службы `celery.service`:

`[Unit]`: Описание службы и зависимости.

`[Service]`: Конфигурация службы, включая команды запуска, перезапуска и остановки.

`[Install]`: Указывает, что служба должна быть запущена при загрузке системы.

Файл таймера `celery.timer`:

`[Timer]`: Указывает, что таймер должен запускаться ежедневно (OnCalendar=daily).

Файл службы `celery-restart.service`:

`[Service]`: Определяет команду для перезапуска службы Celery.

Теперь Celery будет автоматически запускаться при загрузке системы и перезапускаться каждый день в соответствии с настройками таймера.