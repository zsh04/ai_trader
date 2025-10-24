module.exports = {
  apps: [
    {
      name: "ai_trader",
      script: ".venv/bin/python",
      // use -m so Python launches uvicorn as a module
      args: "-m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload",
      exec_mode: "fork",
      exec_interpreter: "none",   // <— critical: do NOT use Node
      cwd: process.env.PWD || ".",
      env: {
        PYTHONUNBUFFERED: "1",
        TZ: "America/Los_Angeles",
      },
      out_file: process.env.HOME + "/ai_trader_logs/uvicorn.out.log",
      error_file: process.env.HOME + "/ai_trader_logs/uvicorn.err.log",
      merge_logs: true,
      autorestart: true,
      max_restarts: 10,
    },
    {
      name: "ngrok",
      script: "ngrok",
      args: "http 8000 --region us",
      exec_interpreter: "none",
      out_file: process.env.HOME + "/ai_trader_logs/ngrok.out.log",
      error_file: process.env.HOME + "/ai_trader_logs/ngrok.err.log",
      merge_logs: true,
      autorestart: true,
    },
  ],
};