const path = require("path");

const LOG_DIR =
  process.env.LOG_DIR ||
  (process.env.HOME ? path.join(process.env.HOME, "ai_trader_logs") : path.join(process.cwd(), "logs"));

module.exports = {
  apps: [
    {
      name: "ai_trader",
      script: "-m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1",
      exec_mode: "fork",
      exec_interpreter: path.join(process.cwd(), ".venv/bin/python"),
      cwd: process.env.PWD || ".",
      env: {
        PYTHONUNBUFFERED: "1",
        TZ: "America/Los_Angeles",
        PORT: process.env.PORT || "8000",
        LOG_DIR: LOG_DIR,
      },
      out_file: path.join(LOG_DIR, "uvicorn.out.log"),
      error_file: path.join(LOG_DIR, "uvicorn.err.log"),
      merge_logs: true,
      autorestart: true,
      max_restarts: 10,
    },
    {
      name: "ngrok",
      script: "ngrok",
      args: "http 8000 --region us",
      exec_interpreter: "none",
      out_file: path.join(LOG_DIR, "ngrok.out.log"),
      error_file: path.join(LOG_DIR, "ngrok.err.log"),
      merge_logs: true,
      autorestart: true,
    },
    {
      name: "pm2-logrotate",
      script: "pm2-logrotate",
      exec_interpreter: "none",
      autorestart: true,
      env: {
        PM2_LOGROTATE_ENABLE: true,
        PM2_LOGROTATE_CRON: "0 0 * * *",
        PM2_LOGROTATE_RETENTION: "7",
        PM2_LOGROTATE_DATE_FORMAT: "YYYY-MM-DD",
        PM2_LOGROTATE_COMPRESS: true,
      },
    },
  ],
};
