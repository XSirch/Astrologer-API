# Development
web: uvicorn app.main:app --host=0.0.0.0 --port=8080 --log-level info

# Production (use this on VPS with PM2 or systemd)
# web: gunicorn -k uvicorn.workers.UvicornWorker -w 4 -b 0.0.0.0:8080 --access-logfile - --error-logfile - --capture-output --enable-stdio-inheritance app.main:app
