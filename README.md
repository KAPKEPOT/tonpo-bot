<div align="center">

# FX Signal Copier Bot 📈🤖

[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Rust](https://img.shields.io/badge/Rust-Gateway-000000?logo=rust&logoColor=white)](https://www.cipherbridge.cloud/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white)](https://redis.io/)
[![FX-SIGNAL-COPIER](https://img.shields.io/badge/FX-SIGNAL-COPIER26A5E4?logo=telegram)](https://t.me/fxsignalcopier1bot)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Telegram](https://img.shields.io/badge/Cipher-Trading%20Group-26A5E4?logo=telegram)](https://t.me/CipherTrade1)

**A self-hosted Telegram trading bot that executes forex trades on MetaTrader 5 — powered by its own high-performance Rust gateway. No third-party APIs. No monthly fees. You own everything.**

[Try the Bot](https://t.me/fxsignalcopier1bot) · [Join Community](https://t.me/CipherTrade1) · [Report Bug](https://github.com/KAPKEPOT/fx-signal-copier/issues)

</div>

---

## How It Works

```
User sends signal ──→ Telegram Bot ──→ CipherBridge Gateway ──→ MT5 Terminal
     via Telegram        (Python)          (Rust/axum)          (via Bridge DLL)
```

The bot parses trading signals, calculates position sizes based on your risk rules, and executes trades on your MT5 account — all in under 2 seconds. No MetaAPI. No cloud dependencies. Your credentials never leave your infrastructure.

## Features

### Trading
- **Automated Execution** — send a signal, bot executes on MT5 instantly
- **Smart Risk Management** — automatic position sizing based on balance, SL distance, and your risk %
- **All Order Types** — market, limit, stop, stop-limit (buy and sell)
- **Multiple Take Profits** — split positions across up to 3 TP levels
- **Risk Calculator** — preview trade risk before committing

### Account Management
- **Live Dashboard** — check balance, equity, margin, open positions
- **Trade History** — review past trades with P&L tracking
- **Per-User Settings** — customizable risk %, allowed symbols, notifications
- **Multi-Account** — each user connects their own MT5 account

### Subscriptions & Payments
- **Tiered Plans** — Free, Basic, Pro, Enterprise with configurable limits
- **Crypto Payments** — pay with USDT (ERC-20) or BTC
- **Auto-Verification** — on-chain payment detection via Etherscan/Blockchain.info
- **Unique Amounts** — each payment uses a distinct amount for automatic matching

### Admin
- **User Management** — view, ban, promote users
- **Broadcast** — send announcements to all users
- **System Monitoring** — track errors, performance, connection health
- **Usage Analytics** — trades per day, active users, revenue

### Infrastructure
- **Self-Hosted Gateway** — Rust/axum server, no third-party trading APIs
- **Bridge DLL** — C++ WebSocket bridge running inside MT5
- **Dual Provisioning** — Docker (Wine+MT5) or native Windows VPS
- **Zero Inbound Ports** — bridge and node agent connect outbound
- **AES-256-GCM** — credential encryption at rest
- **PostgreSQL** — persistent storage for accounts, tokens, audit logs

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                        Linux VPS                               │
│                                                                │
│   ┌─────────────────┐    ┌──────────────┐    ┌─────────────┐ │
│   │  Telegram Bot    │───▶│  CMG Gateway  │◀───│ PostgreSQL  │ │
│   │  (Python)        │    │  (Rust/axum)  │    │             │ │
│   └─────────────────┘    └──────┬───────┘    └─────────────┘ │
│                                 │                              │
└─────────────────────────────────┼──────────────────────────────┘
                                  │ WSS (outbound)
                    ┌─────────────┼─────────────┐
                    │             │              │
             ┌──────▼──────┐  ┌──▼───────────┐  │
             │ Docker+Wine │  │ Windows VPS  │  │
             │ Container   │  │ Node Agent   │  │
             │ (MT5+DLL)   │  │ (MT5+DLL)    │  │
             └─────────────┘  └──────────────┘  │
                                                 │
                              ┌──────────────────▼┐
                              │  MT5 Broker       │
                              │  (executes trade) │
                              └───────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.12+
- PostgreSQL 16
- Redis 7
- A Telegram Bot Token ([get one from @BotFather](https://t.me/BotFather))
- A MetaTrader 5 account with any broker

### 1. Clone & Setup

```bash
git clone https://github.com/KAPKEPOT/fx-signal-copier.git
cd fx-signal-copier

python -m venv fx
source fx/bin/activate        # Linux/Mac
# fx\Scripts\activate         # Windows

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
ADMIN_USER_IDS=your_telegram_user_id

# Database
DATABASE_URL=postgresql://fxuser:yourpassword@localhost:5432/fx_signal_copier

# Redis
REDIS_URL=redis://localhost:6379/0

# Security — generate these:
ENCRYPTION_KEY=   # python3 -c "import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
JWT_SECRET=       # python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Gateway (CipherTrade)
GATEWAY_HOST=localhost
GATEWAY_PORT=8080
GATEWAY_USE_SSL=false
```

### 3. Setup Database

```bash
# Create database (if not exists)
sudo -u postgres psql -c "CREATE USER fxuser WITH PASSWORD 'yourpassword';"
sudo -u postgres psql -c "CREATE DATABASE fx_signal_copier OWNER fxuser;"

# Run migrations
make migrate
```

### 4. Start Redis

```bash
sudo apt install redis-server -y
sudo systemctl enable redis-server
sudo systemctl start redis-server
```

### 5. Run

```bash
make run
```

The bot is now live. Open Telegram, find your bot, and send `/start`.

## Bot Commands

### User Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/register` | Connect your MT5 account |
| `/trade` | Place a new trade |
| `/calculate` | Calculate risk without executing |
| `/balance` | Check account balance |
| `/positions` | View open positions |
| `/history` | View trade history |
| `/settings` | Configure risk, notifications, symbols |
| `/profile` | View your profile and stats |
| `/upgrade` | View subscription plans |
| `/help` | Show help and examples |

### Admin Commands

| Command | Description |
|---------|-------------|
| `/admin` | Admin dashboard |
| `/stats` | System statistics |
| `/broadcast` | Send message to all users |

## Trade Signal Format

```
BUY/SELL [LIMIT/STOP] SYMBOL
Entry PRICE or NOW
SL PRICE
TP1 PRICE
TP2 PRICE (optional)
TP3 PRICE (optional)
```

**Examples:**

```
BUY GBPUSD
Entry NOW
SL 1.25000
TP 1.26000
```

```
SELL LIMIT EURUSD
Entry 1.10500
SL 1.11000
TP1 1.10000
TP2 1.09500
```

## Subscription Plans

| Feature | Free | Basic | Pro | Enterprise |
|---------|------|-------|-----|------------|
| Trades/day | 5 | 10 | 20 | 50 |
| Multiple TPs | — | ✅ | ✅ | ✅ |
| Auto-trading | — | — | ✅ | ✅ |
| API access | — | — | — | ✅ |
| MT5 accounts | 1 | 1 | 3 | 10 |
| Priority support | — | — | ✅ | ✅ |
| Price | Free | $9.99/mo | $29.99/mo | $99.99/mo |

Payments accepted in **USDT (ERC-20)** and **BTC**. Plans activate automatically after on-chain confirmation.

## Project Structure

```
fx-signal-copier/
├── bot/                    # Telegram bot
│   ├── main.py             # Bot initialization + handler registration
│   ├── handlers.py         # Command handlers (/start, /help, /balance...)
│   ├── registration.py     # /register conversation flow
│   ├── trading.py          # /trade conversation flow
│   ├── settings.py         # /settings conversation flow
│   ├── admin.py            # Admin dashboard + user management
│   ├── callbacks.py        # Inline keyboard callback router
│   ├── keyboards.py        # All inline keyboards
│   ├── middleware.py        # Auth, rate limiting, error handling
│   └── message_utils.py    # Safe message editing utilities
├── gateway_client/         # CMG Gateway SDK
│   ├── client.py           # REST + WebSocket client
│   └── adapter.py          # Adapter layer for gateway integration
├── services/               # Business logic
│   ├── trade_executor.py   # Trade execution pipeline
│   ├── signal_processor.py # Signal parsing + validation
│   ├── risk_service.py     # Position size calculation
│   ├── payment.py          # Crypto payment processing
│   ├── subscription.py     # Plan management
│   ├── notification.py     # Telegram notifications
│   ├── auth.py             # Authentication + encryption
│   ├── analytics.py        # Usage tracking
│   ├── cache.py            # Redis cache layer
│   ├── monitoring.py       # Health + metrics
│   └── queue.py            # Background task queue
├── database/               # Persistence
│   ├── models.py           # SQLAlchemy models
│   ├── repositories.py     # Data access layer
│   ├── database.py         # Connection management
│   └── migrations/         # Alembic migrations
├── core/                   # Domain models
│   ├── models.py           # TradeSignal, CalculatedTrade
│   ├── parser.py           # Signal text parser
│   ├── validators.py       # Input validation
│   └── exceptions.py       # Custom exceptions
├── config/                 # Configuration
│   ├── settings.py         # Pydantic settings
│   └── constants.py        # Pip multipliers, symbols, enums
├── utils/                  # Helpers
│   └── formatters.py       # Message formatting
├── main.py                 # Entry point
├── Makefile                # Dev commands
├── requirements.txt        # Python dependencies
├── alembic.ini             # Migration config
└── .env.example            # Environment template
```

## CipherBridge Gateway

The bot connects to the [CipherBridge Gateway](https://github.com/KAPKEPOT/CMG) — a self-hosted Rust server that bridges Telegram to MetaTrader 5. The gateway handles:

- Credential encryption + secure storage
- MT5 connection provisioning (Docker or Windows native)
- Trade execution via WebSocket bridge
- Account lifecycle (create, pause, resume, delete)
- Heartbeat monitoring + auto-recovery

See the [CMG repository](https://github.com/KAPKEPOT/CMG) for gateway setup instructions.

## Database Migrations

```bash
# Apply all pending migrations
make migrate

# Create a new migration
make create-migration message="description here"

# Rollback one migration
alembic downgrade -1
```

## Security

- **Credentials** — MT5 passwords encrypted with AES-256-GCM, stored only on the gateway
- **Bot DB** — stores `GATEWAY_MANAGED` placeholder, never the actual password
- **Authentication** — JWT tokens + API keys with SHA-256 hashing
- **Rate Limiting** — per-user, per-IP, configurable by subscription tier
- **Input Validation** — all user input sanitized before processing
- **Zero Inbound Ports** — MT5 bridges connect outbound to gateway

## Makefile Commands

```bash
make run              # Start the bot
make migrate          # Run database migrations
make create-migration # Create new migration
make install          # Install dependencies
make test             # Run test suite
make lint             # Run linters
make format           # Format code (black + isort)
make clean            # Remove cache files
make start-services   # Start PostgreSQL + Redis
make status           # Check service status
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

Distributed under the MIT License. See [LICENSE](LICENSE) for details.

## Support

- **Bot:** [@fxsignalcopier1bot](https://t.me/fxsignalcopier1bot)
- **Community:** [CipherTrade Group](https://t.me/CipherTrade1)
- **Issues:** [GitHub Issues](https://github.com/KAPKEPOT/fx-signal-copier/issues)

---

<div align="center">

**Built with ❤️ by [KAPKEPOT](https://github.com/KAPKEPOT)**

⭐ Star this repo if it helps you trade smarter

[![Star History Chart](https://api.star-history.com/svg?repos=KAPKEPOT/fx-signal-copier&type=Date)](https://star-history.com/#KAPKEPOT/fx-signal-copier&Date)

</div>
