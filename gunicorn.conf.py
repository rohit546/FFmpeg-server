# Gunicorn configuration for Render free tier (512MB memory limit)
bind = "0.0.0.0:10000"
workers = 1  # Single worker to minimize memory usage
timeout = 300  # 5 minutes for video processing
keepalive = 2
max_requests = 50  # Restart worker after 50 requests to prevent memory leaks
max_requests_jitter = 10
worker_class = "sync"
worker_connections = 50  # Limit concurrent connections
