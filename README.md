<div align="center">

# Tonpo Bot

[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white)](https://redis.io/)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?logo=telegram&logoColor=white)](https://t.me/BotFather)
[![License](https://img.shields.io/badge/License-MIT-red.svg)](LICENSE)

**A Telegram trading bot for MetaTrader 5. Executes forex trades automatically from signals with smart risk management and subscription tiers.**

*Built using the [Tonpo SDK](https://github.com/TonpoLabs/tonpo-py)*

</div>

---

## What is Tonpo Bot?

Tonpo Bot is a **Telegram trading bot** that:

- 🤖 **Executes trades automatically** — send a signal, bot executes on your MT5 instantly
- 📊 **Smart risk management** — automatic position sizing based on your configured risk %
- 💰 **Subscriptions** — Free, Basic, Pro, Enterprise tiers with usage limits
- 💳 **Crypto payments** — USDT and BTC with automatic on-chain verification
- 📈 **Live dashboard** — check balance, positions, P&L directly from Telegram
- 🔐 **Secure** — your MT5 credentials never stored locally

This bot uses the **[Tonpo SDK](https://github.com/TonpoLabs/tonpo-py)** to communicate with the Tonpo Gateway to execute trades.

---

## Features

### Trading
- **Automated execution** — send a signal, bot executes on MT5 in < 2 seconds
- **Smart position sizing** — automatic lot calculation based on balance, SL distance, risk %
- **All order types** — market, limit, stop (BUY and SELL)
- **Multiple take profits** — split positions across up to 3 TP levels
- **Risk calculator** — preview trade impact before executing

### Account Management
- **Live dashboard** — balance, equity, margin, open positions
- **Trade history** — full P&L tracking with trade details
- **Per-user settings** — customize risk %, allowed symbols, notifications
- **Multi-account support** — connect multiple MT5 accounts (based on plan)

### Subscriptions & Payments
- **Tiered plans** — Free (10 trades/day) to Enterprise (unlimited)
- **Crypto payments** — USDT (ERC-20) or BTC
- **Auto-verification** — on-chain payment detection
- **Usage limits** — configurable per plan (trades/day, accounts, features)

### Admin
- **User management** — view, ban, promote, monitor users
- **Broadcast** — send announcements to all users
- **System monitoring** — errors, performance, connection health
- **Analytics** — trades per day, active users, revenue tracking

---

## Prerequisites

### Requirements

- **Python 3.12+**
- **PostgreSQL 16** — for users, trades, subscriptions, audit logs
- **Redis 7** — for caching and rate limiting
- **Telegram Bot Token** — get one from [@BotFather](https://t.me/BotFather)
- **MT5 Account** — from any broker (demo or live account)

## Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/KAPKEPOT/tonpo-bot.git
cd tonpo-bot

python -m venv venv
source venv/bin/activate       # Linux/macOS
# venv\Scripts\activate        # Windows

pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
nano .env
```

**Essential variables:**

```env
# Telegram
BOT_TOKEN=your_bot_token_from_botfather
ADMIN_USER_IDS=your_telegram_user_id   # comma-separated for multiple admins

# Database
DATABASE_URL=postgresql://tonpo:yourpassword@localhost:5432/tonpo_bot

# Redis
REDIS_URL=redis://localhost:6379/0

# Security (generate with: python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())")
ENCRYPTION_KEY=your-32-byte-base64-key

# Tonpo Gateway (the service this bot uses)
GATEWAY_HOST=your-tonpo-gateway-host.com
GATEWAY_PORT=443
GATEWAY_USE_SSL=true
```

### 3. Create Database

```bash
sudo -u postgres psql -c "CREATE USER tonpo WITH PASSWORD 'yourpassword';"
sudo -u postgres psql -c "CREATE DATABASE tonpo_bot OWNER tonpo;"
sudo -u postgres psql -d tonpo_bot -c "GRANT ALL ON SCHEMA public TO tonpo;"
```

### 4. Run Migrations

```bash
make migrate
```

### 5. Start Services

```bash
# PostgreSQL + Redis
make start-services

# Start the bot (in new terminal)
make run
```

Open Telegram, find your bot, send `/start`.

---

## Commands

### User Commands

| Command | Description |
|---|---|
| `/start` | Welcome message and main menu |
| `/register` | Connect your MT5 account |
| `/trade` | Place a new trade from a signal |
| `/calculate` | Calculate position size without executing |
| `/balance` | Check live account balance and equity |
| `/positions` | View all open positions |
| `/history` | View trade history with P&L |
| `/settings` | Configure risk %, symbols, notifications |
| `/profile` | View profile and stats |
| `/upgrade` | View subscription plans and payment |
| `/help` | Show commands and signal format |

### Admin Commands

| Command | Description |
|---|---|
| `/admin` | Admin dashboard |
| `/stats` | System statistics — trades, users, errors |
| `/broadcast` | Send announcement to all users |

---

## Trade Signal Format

Send signals in this format:

```
BUY/SELL [LIMIT/STOP] SYMBOL
Entry PRICE or NOW
SL PRICE
TP PRICE
TP2 PRICE  (optional)
TP3 PRICE  (optional)
```

### Examples

**Market order (execute immediately):**
```
BUY GBPUSD
Entry NOW
SL 1.25000
TP 1.26000
```

**Limit order (execute at specific price):**
```
SELL LIMIT EURUSD
Entry 1.10500
SL 1.11000
TP1 1.10000
TP2 1.09500
```

**Multiple take profits:**
```
BUY XAUUSD
Entry NOW
SL 2280.00
TP1 2310.00
TP2 2330.00
TP3 2350.00
```


## How the Bot Works

```
User sends signal via Telegram
        │
        ▼
Bot parses signal
        │
        ▼
Bot calculates position size (smart risk management)
        │
        ▼
Bot calls Tonpo SDK (tonpo-py)
        │
        ▼
Tonpo Gateway executes on MT5
        │
        ▼
Trade executed in < 2 seconds
```

### Registration Flow

1. User sends `/register`
2. Bot creates user on Tonpo Gateway (receives API key)
3. User enters MT5 credentials
4. Bot provisions account on Tonpo Gateway (credentials encrypted at rest)
5. Bot stores only: `tonpo_api_key` and `tonpo_account_id`
6. **MT5 password is never stored by bot**

### Trade Execution Flow

1. User sends trade signal
2. Bot validates signal format
3. Bot calculates position size (smart risk management)
4. Bot calls Tonpo SDK with calculated parameters
5. Tonpo Gateway executes trade on MT5
6. Bot stores trade in database with result

---

## Configuration

### Environment Variables

| Variable | Required | Description |
|---|---|---|
| `BOT_TOKEN` | ✅ | Telegram Bot token from @BotFather |
| `ADMIN_USER_IDS` | ✅ | Comma-separated Telegram user IDs |
| `DATABASE_URL` | ✅ | PostgreSQL connection string |
| `REDIS_URL` | ✅ | Redis connection URL |
| `ENCRYPTION_KEY` | ✅ | 32-byte base64 key for local encryption |
| `GATEWAY_HOST` | ✅ | Tonpo Gateway hostname |
| `GATEWAY_PORT` | ✅ | `443` for SSL, `8080` for plain HTTP |
| `GATEWAY_USE_SSL` | ✅ | `true` or `false` |
| `GATEWAY_API_KEY_HEADER` | ❌ | Header name (default: `X-API-Key`) |
| `WEBHOOK_MODE` | ❌ | `true` for webhooks, `false` for polling |
| `WEBHOOK_URL` | ❌ | Public HTTPS URL for webhook mode |
| `LOG_LEVEL` | ❌ | `DEBUG` / `INFO` / `WARNING` (default: `INFO`) |
---

## Development

### Makefile Commands

```bash
make run              # Start the bot (polling mode)
make migrate          # Run database migrations
make create-migration # Create new Alembic migration
make install          # Install/update dependencies
make test             # Run test suite
make lint             # Run linters (ruff, mypy)
make format           # Format code (black + isort)
make clean            # Remove __pycache__ and .pyc files
make start-services   # Start PostgreSQL + Redis
make status           # Check service status
```

### Database Migrations

```bash
# Apply pending migrations
make migrate

# Create new migration after changing models
make create-migration message="add subscription table"

# Roll back one migration
alembic downgrade -1
```

---

## Deployment

### As a System Service

```bash
sudo tee /etc/systemd/system/tonpo-bot.service << 'EOF'
[Unit]
Description=Tonpo Bot
After=network.target postgresql.service redis.service

[Service]
Type=simple
User=tonpo
WorkingDirectory=/home/tonpo/tonpo-bot
EnvironmentFile=/home/tonpo/tonpo-bot/.env
ExecStart=/home/tonpo/tonpo-bot/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now tonpo-bot
sudo journalctl -u tonpo-bot -f   # View logs
```

---

## Troubleshooting

### Bot doesn't respond to commands

**Check:**
- Bot token is correct in `.env`
- Bot is running: `ps aux | grep python`
- Check logs: `journalctl -u tonpo-bot -f`

```bash
# Restart
systemctl restart tonpo-bot
```

### Trades execute slowly (> 2 seconds)

**Check:**
- Gateway connection: `ping $GATEWAY_HOST`
- Gateway is responsive
- Redis is running: `redis-cli ping`
- Network latency to gateway

```bash
# Enable debug logging
LOG_LEVEL=DEBUG make run
```

### Database migration fails

**Check:**
- PostgreSQL is running: `sudo systemctl status postgresql`
- Database user exists: `sudo -u postgres psql -l`
- Connection string is correct
- User has permissions

```bash
# Verify connection
psql $DATABASE_URL -c "SELECT 1"
```

### "Cannot connect to Tonpo Gateway"

**Check:**
- `GATEWAY_HOST` and `GATEWAY_PORT` in `.env`
- Gateway is running and accessible
- SSL setting matches (`GATEWAY_USE_SSL`)
- Firewall allows outbound on that port

```bash
# Test connection
nc -zv $GATEWAY_HOST $GATEWAY_PORT
```

### Memory usage is high

**Check:**
- Redis memory: `redis-cli INFO memory`
- Python process: `ps aux | grep python`
- Database connections: `psql $DATABASE_URL -c "SELECT count(*) FROM pg_stat_activity;"`

```bash
# Clear Redis cache
redis-cli FLUSHDB
```

### Trades are rejected by gateway

**Check:**
- Account balance sufficient
- Symbol is tradeable on broker
- Stop loss and take profit are valid
- Risk % configuration

Enable debug logging to see error details:
```bash
LOG_LEVEL=DEBUG make run
```

---

## Security

| Layer | Implementation |
|---|---|
| **MT5 credentials** | Never stored by bot — encrypted on Tonpo Gateway |
| **Bot database** | Stores only `tonpo_api_key` and `tonpo_account_id` |
| **API authentication** | API key sent as `X-API-Key` header to gateway |
| **Rate limiting** | Per-user, per-IP, configurable by plan |
| **Input validation** | All user input sanitized before processing |
| **Encryption at rest** | Sensitive data encrypted with AES-256-GCM |
| **TLS/HTTPS** | All communication with gateway over HTTPS/WSS |

---

## Examples

### Example 1: Setting Risk %

```
User: /settings
Bot: What's your risk % per trade? (e.g., 2 for 2%)
User: 2
Bot: ✅ Risk set to 2%
```

Now when user sends a trade signal, bot automatically calculates lots based on:
- Account balance
- Stop loss distance
- Risk % (2%)

### Example 2: Forex Scalping

```
User sends signal:
  BUY EURUSD
  Entry NOW
  SL 1.09500
  TP 1.09600

Bot:
  1. Calculates: balance=$1000, SL dist=100 pips, risk=2% → buy 0.20 lots
  2. Executes BUY 0.20 EURUSD
  3. Sets SL at 1.09500
  4. Sets TP at 1.09600
  5. Sends confirmation to user
```

### Example 3: Multi-TP Strategy

```
User sends signal:
  BUY XAUUSD
  Entry NOW
  SL 2280.00
  TP1 2310.00
  TP2 2330.00
  TP3 2350.00

Bot:
  1. Calculates total lots needed: 0.60 lots
  2. Splits: 0.20 lots → TP1, 0.20 → TP2, 0.20 → TP3
  3. Executes three limit sell orders at different prices
  4. Tracks P&L as each level fills
```

---

## Support & Resources

### Getting Help
- **Tonpo SDK** — https://github.com/TonpoLabs/tonpo-py
- **Report Issues** — https://github.com/KAPKEPOT/tonpo-bot/issues
- **Discussions** — https://github.com/KAPKEPOT/tonpo-bot/discussions
---

## Contributing

We welcome contributions! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request
---

## Disclaimer

**This bot is for educational and development purposes.** It is not financial advice. Forex trading carries risk. Always test thoroughly in demo mode before using with real money. The author assumes no responsibility for trading losses.
