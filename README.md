# trade-cloud: AI paper trader that runs on GitHub's servers (no phone, no VPS)

Every 15 min GitHub Actions: fetch live crypto/stock candles -> 3 strategies (liquidity sweep, trend pullback,
breakout+retest) -> news blackout (ForexFactory USD) -> optional Gemini review -> PAPER trade -> Telegram alert ->
dashboard on GitHub Pages. Daily it backtests and auto-blocks strategies that lose.

PAPER = simulated money. Nothing here places real orders. Go live only after weeks of positive paper results.

## Setup (all free, from your phone)
1. github.com: create account, new PUBLIC repo `trade-cloud` (public = unlimited free Actions minutes; data/dashboard are public).
2. github.com/settings/tokens: new classic token with `repo` + `workflow` scopes. Never paste it in chats.
3. Termux:
   pkg install git unzip
   cd ~/storage/downloads && unzip -o trade_cloud.zip -d ~ && cd ~/trade_cloud
   git init -b main && git add -A && git commit -m init
   git remote add origin https://github.com/YOUR_USER/trade-cloud.git
   git push -u origin main        (username = your GitHub name, password = the token)
4. Repo > Settings > Secrets and variables > Actions > New secret:
   TELEGRAM_BOT_TOKEN (new one from @BotFather), TELEGRAM_CHAT_ID (your numeric id), GEMINI_API_KEY (optional).
   Variables tab (optional): SYMBOLS = BTC,ETH,SOL,DOGE,AAPL  (crypto: BTC ETH SOL DOGE XRP; anything else = stock ticker)
5. Repo > Settings > Actions > General > Workflow permissions > Read and write.
6. Repo > Settings > Pages > Deploy from a branch > main > /docs.
7. Actions tab > trade-cloud > Run workflow. Dashboard: https://YOUR_USER.github.io/trade-cloud/

Notes: GitHub cron can run late; scheduled jobs pause after ~60 days without repo activity (check Actions tab).
Stock data comes from Yahoo's unofficial endpoint and only trades while the US market is open.
