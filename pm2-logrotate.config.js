module.exports = {
  apps: [
    {
      name: "ai_trader",
      script: "uvicorn",
      args: "app.main:app --host 0.0.0.0 --port 8000 --reload",
      interpreter: "python3",
      env: {
        PYTHONPATH: ".",
        ENV: "production",
      },
    },
  ],

  // PM2 Logrotate module configuration
  deploy: {},
  pm2: {
    modules: {
      "pm2-logrotate": {
        max_size: "20M",             // rotate when logs reach 20MB
        retain: 7,                   // keep 7 rotated logs
        compress: true,              // compress old logs
        dateFormat: "YYYY-MM-DD_HH-mm-ss",
        workerInterval: 60,          // check every 60 seconds
        rotateInterval: "0 0 * * *", // rotate daily at midnight
        rotateModule: true,          // rotate module logs too
        keepDays: 7,                 // remove logs older than 7 days
      },
    },
  },
};