#!/bin/bash
# ASX Screener - Oracle VPS Setup Script
# This script prepares an Oracle Cloud ARM instance for production.

echo "🚀 Starting Oracle VPS Setup..."

# 1. Update System
sudo apt-get update && sudo apt-get upgrade -y

# 2. Install Dependencies
sudo apt-get install -y python3-pip python3-venv nodejs npm git curl

# 3. Install PM2 (Process Manager)
sudo npm install -g pm2

# 4. Setup Python Virtual Environment
cd /home/ubuntu/asxscreener
python3 -m venv backend/venv
backend/venv/bin/pip install --upgrade pip
backend/venv/bin/pip install -r backend/requirements.txt

# 5. Build Frontend for Production
cd frontend
npm install
npm run build
cd ..

# 6. Configure Oracle Firewall (Standard Ubuntu on Oracle has a strict IPTables)
# This opens ports 8000 (Backend) and 5173 (Frontend)
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 8000 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 5173 -j ACCEPT
sudo netfilter-persistent save

# 7. Create PM2 Ecosystem File
cat <<EOT > ecosystem.config.js
module.exports = {
  apps: [
    {
      name: "asx-backend",
      script: "backend/venv/bin/uvicorn",
      args: "app.main:app --host 0.0.0.0 --port 8000",
      cwd: "backend",
      interpreter: "none",
      env: {
        NODE_ENV: "production",
      }
    },
    {
      name: "asx-frontend",
      script: "npx",
      args: "vite preview --host 0.0.0.0 --port 5173",
      cwd: "frontend",
      interpreter: "none"
    }
  ]
}
EOT

echo "✅ Setup Complete!"
echo "👉 To start the bot 24/7, run: pm2 start ecosystem.config.js"
echo "👉 To see logs, run: pm2 logs"
echo "👉 To ensure it starts on reboot, run: pm2 save && pm2 startup"
