#!/data/data/com.termux/files/usr/bin/bash
# Runs the bot every 15 min in Termux. Settings come from ~/.binance_env (kept OUTSIDE the git folder).
termux-wake-lock
source ~/.binance_env
cd ~/trade_cloud || exit 1
while true; do
  python run.py >> ~/bot_live.log 2>&1
  sleep 900
done
