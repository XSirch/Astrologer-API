module.exports = {
  apps: [
    {
      name: "astrologer-api",
      script: "gunicorn",
      args: [
        "-k", "uvicorn.workers.UvicornWorker",
        "-w", "4",
        "-b", "0.0.0.0:8080",
        "--access-logfile", "-",
        "--error-logfile", "-",
        "--capture-output",
        "--enable-stdio-inheritance",
        "app.main:app"
      ],
      cwd: "/var/www/astrologer-api",
      env: {
        ENV_TYPE: "production",
        PYTHONUNBUFFERED: "1"
      },
      env_production: {
        ENV_TYPE: "production"
      },
      instances: 1,
      exec_mode: "fork",
      autorestart: true,
      watch: false,
      max_memory_restart: "1G",
      min_uptime: "10s",
      max_restarts: 10,
      error_file: "./logs/err.log",
      out_file: "./logs/out.log",
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      merge_logs: true,
      kill_timeout: 5000,
      listen_timeout: 10000,
      // Graceful shutdown handling
      shutdown_with_message: true,
      // Ensure proper signal handling
      interpreter: "none"
    }
  ]
};
