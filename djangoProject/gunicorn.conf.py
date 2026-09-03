# gunicorn.conf.py - Оптимизированная конфигурация для нагруженного сервера

bind = '127.0.0.1:8000'
workers = 5
threads = 4
worker_class = 'gthread'
worker_connections = 1000
timeout = 90
graceful_timeout = 30
max_requests = 1000
max_requests_jitter = 100
user = "nobody"