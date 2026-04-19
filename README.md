<div align="center">

# Tonpo Bot

[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white)](https://redis.io/)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?logo=telegram&logoColor=white)](https://t.me/TonpoBot)
[![License](https://img.shields.io/badge/License-Proprietary-red.svg)](LICENSE)

**A Telegram trading bot for MetaTrader 5 powered by Tonpo Gateway. Executes forex trades automatically from signals — no third-party trading APIs, no cloud dependencies. Your credentials never leave your infrastructure.**

</div>

---

## The Tonpo Stack

| Component | Role |
|---|---|
| **Tonpo Gateway** | Rust/Axum API server on Linux VPS |
| **Tonpo Node** | Windows agent — manages MT5 instances |
| **Tonpo Bridge** | C++ DLL + MQL5 EA inside MT5 |
| **Tonpo Bot** (this repo) | Telegram frontend |
| **tonpo-py** | Python SDK used by this bot |

---

## How It Works

```
User sends signal
      │
      │  Telegram
      ▼
Tonpo Bot (Python)
      │
      │  HTTPS (tonpo-py SDK)
      ▼
Tonpo Gateway (Rust/axum)
      │
      │  WebSocket
      ▼
Tonpo Bridge (C++ DLL + MQL5 EA)
      │
      ▼
MT5 Terminal → Broker
```

The bot parses trading signals, calculates position sizes based on risk rules, and executes trades on the user's MT5 account — all in under 2 seconds.

---

## Features

### Trading
- **Automated execution** — send a signal, bot executes on MT5 instantly
- **Smart risk management** — automatic position sizing based on balance, SL distance, and configured risk %
- **All order types** — market, limit, stop (buy and sell)
- **Multiple take profits** — split positions across up to 3 TP levels
- **Risk calculator** — preview trade risk before committing

### Account Management
- **Live dashboard** — check balance, equity, margin, open positions
- **Trade history** — review past trades with P&L tracking
- **Per-user settings** — customizable risk %, allowed symbols, notifications
- **Multi-account** — each user connects their own MT5 account

### Subscriptions & Payments
- **Tiered plans** — Free, Basic, Pro, Enterprise with configurable limits
- **Crypto payments** — pay with USDT (ERC-20) or BTC
- **Auto-verification** — on-chain payment detection via Etherscan / Blockchain.info
- **Unique amounts** — each payment uses a distinct amount for automatic matching

### Admin
- **User management** — view, ban, promote users
- **Broadcast** — send announcements to all users
- **System monitoring** — errors, performance, connection health
- **Usage analytics** — trades per day, active users, revenue

### Infrastructure
- **Tonpo Gateway** — Rust/axum server, zero third-party trading APIs
- **Tonpo Bridge** — C++ WebSocket bridge inside MT5
- **Dual provisioning** — Docker (Wine+MT5) or Windows VPS via Tonpo Node Agent
- **Zero inbound ports** — bridge and node agent connect outbound to gateway
- **AES-256-GCM** — MT5 credential encryption at rest
- **PostgreSQL** — persistent storage for users, accounts, tokens, audit logs

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                      Linux VPS                        │
│                                                       │
│  ┌──────────────┐    ┌───────────────┐    ┌────────┐ │
│  │  Tonpo Bot    │───▶│ Tonpo Gateway │◀───│  PgSQL │ │
│  │  (Python)     │    │ (Rust/axum)   │    │        │ │
│  └──────────────┘    └──────┬────────┘    └────────┘ │
│                             │                         │
└─────────────────────────────┼─────────────────────────┘
                              │  WSS (outbound)
               ┌──────────────┴──────────────┐
               │                              │
        ┌──────▼──────┐              ┌────────▼──────┐
        │ Docker+Wine  │              │  Windows VPS  │
        │ Container    │              │  Tonpo Node   │
        │ (MT5 + DLL)  │              │  (MT5 + DLL)  │
        └─────────────┘              └───────────────┘
```

---

## Quick Start

### Prerequisites

- Python 3.12+
- PostgreSQL 16
- Redis 7
- A Telegram Bot Token — get one from [@BotFather](https://t.me/BotFather)
- A running [Tonpo Gateway](https://github.com/TonpoLabs/CMG) instance
- At least one MT5 account with any broker

### 1. Clone & Install

```bash
git clone https://github.com/TonpoLabs/tonpo-bot.git
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

**Required variables:**

```env
# Telegram
BOT_TOKEN=your_bot_token_from_botfather
ADMIN_USER_IDS=your_telegram_user_id   # comma-separated for multiple admins

# Database
DATABASE_URL=postgresql://tonpo:yourpassword@localhost:5432/tonpo_bot

# Redis
REDIS_URL=redis://localhost:6379/0

# Security — generate these:
# python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
ENCRYPTION_KEY=your-32-byte-base64-key

# Tonpo Gateway
GATEWAY_HOST=gateway.cipherbridge.cloud
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

### 5. Start Redis

```bash
sudo apt install redis-server -y
sudo systemctl enable --now redis-server
```

### 6. Start the Bot

```bash
make run
```

Open Telegram, find your bot, and send `/start`.

---

## Bot Commands

### User Commands

| Command | Description |
|---|---|
| `/start` | Welcome message and main menu |
| `/register` | Connect your MT5 account to the gateway |
| `/trade` | Place a new trade from a signal |
| `/calculate` | Calculate position size and risk without executing |
| `/balance` | Check live account balance and equity |
| `/positions` | View all open positions |
| `/history` | View trade history with P&L |
| `/settings` | Configure risk %, symbols, notifications |
| `/profile` | View your profile and stats |
| `/upgrade` | View subscription plans and payment |
| `/help` | Show commands and signal format examples |

### Admin Commands

| Command | Description |
|---|---|
| `/admin` | Admin dashboard |
| `/stats` | System statistics — trades, users, errors |
| `/broadcast` | Send announcement to all users |

---

## Trade Signal Format

```
BUY/SELL [LIMIT/STOP] SYMBOL
Entry PRICE or NOW
SL PRICE
TP PRICE
TP2 PRICE  (optional — up to 3 TPs)
TP3 PRICE  (optional)
```

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

**Multiple take profits (position split across TP levels):**

```
BUY XAUUSD
Entry NOW
SL 2280.00
TP1 2310.00
TP2 2330.00
TP3 2350.00
```

---

## Subscription Plans

| Feature | Free | Basic | Pro | Enterprise |
|---|---|---|---|---|
| Trades/day | 10 | 50 | 200 | Unlimited |
| Multiple TPs | — | ✅ | ✅ | ✅ |
| Auto-trading | — | — | ✅ | ✅ |
| API access | — | — | — | ✅ |
| MT5 accounts | 1 | 1 | 3 | 10 |
| Priority support | — | — | ✅ | ✅ |
| Price | Free | $9.99/mo | $29.99/mo | $99.99/mo |

Payments accepted in **USDT (ERC-20)** and **BTC**. Plans activate automatically after on-chain confirmation.

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `BOT_TOKEN` | ✅ | Telegram Bot token from @BotFather |
| `ADMIN_USER_IDS` | ✅ | Comma-separated Telegram user IDs for admins |
| `DATABASE_URL` | ✅ | PostgreSQL connection string |
| `REDIS_URL` | ✅ | Redis connection URL |
| `ENCRYPTION_KEY` | ✅ | 32-byte base64 key for local encryption |
| `GATEWAY_HOST` | ✅ | Tonpo Gateway hostname |
| `GATEWAY_PORT` | ✅ | `443` for SSL, `8080` for plain HTTP |
| `GATEWAY_USE_SSL` | ✅ | `true` or `false` |
| `GATEWAY_API_KEY_HEADER` | ❌ | Header name (default: `X-API-Key`) |
| `WEBHOOK_MODE` | ❌ | `true` to use Telegram webhooks instead of polling |
| `WEBHOOK_URL` | ❌ | Public HTTPS URL for webhook mode |
| `LOG_LEVEL` | ❌ | `DEBUG` / `INFO` / `WARNING` (default: `INFO`) |

---

## Project Structure

```
tonpo-bot/
├── bot/
│   ├── main.py              # Bot initialization + handler registration
│   ├── handlers.py          # Command handlers (/start, /help, /balance…)
│   ├── registration.py      # /register conversation flow
│   ├── trading.py           # /trade conversation flow
│   ├── settings.py          # /settings conversation flow
│   ├── admin.py             # Admin dashboard + user management
│   ├── callbacks.py         # Inline keyboard callback router
│   ├── keyboards.py         # All inline keyboards
│   ├── middleware.py        # Auth, rate limiting, error handling
│   └── message_utils.py     # Safe message editing utilities
├── gateway_client/
│   ├── client.py            # tonpo-py SDK wrapper
│   └── adapter.py           # Adapter layer for gateway integration
├── services/
│   ├── trade_executor.py    # Trade execution pipeline
│   ├── signal_processor.py  # Signal parsing + validation
│   ├── risk_service.py      # Position size calculation
│   ├── payment.py           # Crypto payment processing
│   ├── subscription.py      # Plan management
│   ├── notification.py      # Telegram notifications
│   ├── auth.py              # Authentication + encryption
│   ├── analytics.py         # Usage tracking
│   ├── cache.py             # Redis cache layer
│   ├── monitoring.py        # Health + metrics
│   └── queue.py             # Background task queue
├── database/
│   ├── models.py            # SQLAlchemy models
│   ├── repositories.py      # Data access layer
│   ├── database.py          # Connection management
│   └── migrations/          # Alembic migrations
├── core/
│   ├── models.py            # TradeSignal, CalculatedTrade dataclasses
│   ├── parser.py            # Signal text parser
│   ├── validators.py        # Input validation
│   └── exceptions.py        # Custom exceptions
├── config/
│   ├── settings.py          # Pydantic settings
│   └── constants.py         # Pip multipliers, symbols, enums
├── utils/
│   └── formatters.py        # Message formatting helpers
├── main.py                  # Entry point
├── Makefile                 # Dev commands
├── requirements.txt
├── alembic.ini
└── .env.example
```

---

## How the Gateway Integration Works

The bot uses the **tonpo-py** SDK to communicate with the Tonpo Gateway. The gateway owns the MT5 credentials — the bot never stores or transmits them after registration.

**Registration flow (once per user):**

```python
# 1. Create a gateway user — get api_key
user = await gateway.create_user()

# 2. Provision MT5 account — gateway encrypts and stores credentials
account = await gateway.create_account(mt5_login, mt5_password, mt5_server)

# 3. Wait for MT5 to connect (2–4 minutes on Windows VPS cold start)
await gateway.wait_for_active(account.account_id, timeout=180)

# Store in bot DB — credentials never needed again
db.save(user_id, tonpo_api_key=user.api_key, tonpo_account_id=account.account_id)
```

**Trade execution (every trade):**

```python
# Look up stored credentials
row = db.get(telegram_id)

# Execute via tonpo-py
result = await gateway.place_market_buy("EURUSD", volume=calculated_lots)
```

The bot database stores only `tonpo_api_key` and `tonpo_account_id` — never the MT5 password.

---

## Database Migrations

```bash
# Apply all pending migrations
make migrate

# Create a new migration after changing models
make create-migration message="add subscription table"

# Roll back one migration
alembic downgrade -1
```

---

## Security

| Layer | Implementation |
|---|---|
| **MT5 credentials** | Encrypted with AES-256-GCM on the gateway — bot never stores the password |
| **Bot database** | Stores `tonpo_api_key` and `tonpo_account_id` only |
| **API key auth** | SHA-256 hashed on gateway, sent as `X-API-Key` header |
| **Rate limiting** | Per-user, per-IP, configurable by subscription tier |
| **Input validation** | All user input sanitized before processing |
| **Zero inbound ports** | MT5 bridge and node agent connect outbound to gateway |
| **TLS** | All gateway communication over HTTPS/WSS |

---

## Makefile Commands

```bash
make run              # Start the bot (polling mode)
make migrate          # Run database migrations
make create-migration # Create a new Alembic migration
make install          # Install/update dependencies
make test             # Run test suite
make lint             # Run linters (ruff, mypy)
make format           # Format code (black + isort)
make clean            # Remove __pycache__ and .pyc files
make start-services   # Start PostgreSQL + Redis
make status           # Check service status
```

---

## Running as a System Service

```bash
sudo tee /etc/systemd/system/tonpo-bot.service << 'EOF'
[Unit]
Description=Tonpo Telegram Bot
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
sudo journalctl -u tonpo-bot -f
```

---

## License

Proprietary — All rights reserved. © Tonpo. Unauthorised copying, distribution, or use is strictly prohibited.
