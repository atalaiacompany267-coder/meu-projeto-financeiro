# Gunicorn Configuration File
# Para deploy no Render, Heroku, Railway, etc.

import os

# Binding
bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"

# Workers
workers = int(os.environ.get('WORKERS', '2'))
worker_class = 'sync'
worker_connections = 1000
timeout = 120
keepalive = 5

# Logging
accesslog = '-'
errorlog = '-'
loglevel = 'info'
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Process naming
proc_name = 'financeiro_app'

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# SSL (descomente se usar HTTPS)
# keyfile = None
# certfile = None
