## FX Signal Copier Bot 📈🤖

https://img.shields.io/badge/python-3.9%2B-blue
https://img.shields.io/badge/Telegram-Bot-26A5E4?logo=telegram
https://img.shields.io/badge/MetaTrader-5-FF4B4B
https://img.shields.io/badge/license-MIT-green
https://img.shields.io/badge/docker-ready-2496ED?logo=docker

A powerful Telegram bot that automatically executes forex trades on MetaTrader 5 accounts. Users can send trading signals via Telegram, and the bot calculates position sizes based on risk management rules and executes trades automatically.

#### ✨ Features

**🎯 Core Functionality**

· **Automated Trade Execution** - Send signals via Telegram, bot executes on MT5
· **Multi-User Support** - Each user connects their own MT5 account
· **Smart Risk Management** - Automatic position sizing based on account balance
· **Multiple Take Profits** - Support for up to 2 TP levels
· **All Order Types** - Market, Limit, and Stop orders

**🔐 Security**

· **Encrypted Credentials** - User passwords securely encrypted
· **Telegram Authentication** - Only authorized users can access
· **Rate Limiting** - Prevents abuse and API overuse

#### 📊 User Features

· **Risk Calculator** - Preview trade risk before executing
· **Account Dashboard** - Check balance, open positions, trade history
· **Customizable Settings** - Per-user risk preferences, symbol filters
· **Real-time Notifications** - Trade confirmations and alerts

#### 👑 Admin Features

· **User Management** - View, ban, or promote users
· **Broadcast Messages** - Send announcements to all users
· **System Monitoring** - Track performance and errors
· **Usage Statistics** - View platform analytics

##### 💎 Subscription Plans

· **Free Tier** - 10 trades/day, basic features
· **Pro Tier** - 50 trades/day, multiple TPs
· **Enterprise** - Unlimited trades, API access

##### 🚀 Quick Start

**Prerequisites**

· Python 3.9+
· PostgreSQL
· Redis
· [MetaAPI account] (https://app.metaapi.cloud)
· Telegram Bot Token (from @BotFather)

**One-Line Setup**

***bash***
 **Clone repository**
 ```
git clone https://github.com/yourusername/fx-signal-copier.git
cd fx-signal-copier
```

**Run setup script**
```
chmod +x scripts/quick_start.sh
./scripts/quick_start.sh
```

#### Manual Installation

**1. Clone and setup environment**

***bash***
```
git clone https://github.com/yourusername/fx-signal-copier.git
cd fx-signal-copier
```
```
python -m venv fx
```
```
source venv/bin/activate
```
***On Windows:***
```
fx\Scripts\activate
```
```
pip install -r requirements.txt
```

1. Configure environment variables

***bash***
```
cp .env.example .env
```
 Add your credentials
```
nano .env  
```
 *Add your credentials*

**1. Start services with Docker**

***bash***
```
docker-compose up -d postgres redis
alembic upgrade head
```
```
python main.py
```

📝 Configuration

Required Environment Variables

```env
# Telegram
BOT_TOKEN=your_telegram_bot_token
ADMIN_USER_IDS=123456789,987654321

# MetaAPI
METAAPI_TOKEN=your_metaapi_api_token

# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/fx_signal_copier

# Security
ENCRYPTION_KEY=your_32_byte_base64_key
JWT_SECRET=your_jwt_secret
```

#### 🤖 Bot Commands

**User Commands**

*Command Description*
|Command|Description|
|:------|-----------:|
|/start |Welcome message|
|/help |Show help and examples|
|/register |Connect your MT5 account|
|/trade |Place a new trade|
|/calculate| Calculate risk without trading|
|/balance |Check account balance|
|/positions| View open positions|
|/history| View trade history|
|/settings |Configure preferences|
|/profile |View your profile|
|/upgrade| Upgrade subscription|

###### Admin Commands

|Command |Description|
|:-----|--------:|
|/admin |Admin dashboard|
|/stats |System statistics|
|-------|-------------|
|/broadcast |Send message to all users|

##### 📊 Trade Signal Format

**Standard Format**

```
BUY/SELL [LIMIT/STOP] SYMBOL
Entry PRICE or NOW
SL PRICE
TP1 PRICE
TP2 PRICE (optional)
```

**Examples**

```
# Market Buy
BUY GBPUSD
Entry NOW
SL 1.25000
TP 1.26000
```
**Limit Order with 2 TPs**
```
BUY LIMIT EURUSD
Entry 1.10000
SL 1.09500
TP1 1.10500
TP2 1.11000
```

#### 🐳 Docker Deployment

##### Production Setup

 **Build and start all services**
```
docker-compose up -d
```

 **View logs**
```
docker-compose logs -f
```

 **Stop services**
```
docker-compose down
```

##### Docker Compose Services

· ***postgres** - Database
· **redis** - Cache and rate limiting
· **bot** - Main Telegram bot
· **celery-worker** - Background tasks
· **celery-beat** - Scheduled tasks


#### 📁 Project Structure

```
fx-signal-copier/
├── bot/                 # Telegram bot handlers
├── core/                # Core business logic
├── database/            # Database models and repositories
├── services/            # Business services
├── utils/               # Utility functions
├── config/              # Configuration
├── tests/               # Test suite
├── scripts/             # Utility scripts
├── docker-compose.yml   # Docker configuration
├── .env.example         # Environment variables template
└── README.md            # This file
```

### 🔧 Development

**Setup Development Environment**

**bash**
##### Install dev dependencies
```
pip install -r requirements-dev.txt
```
##### Setup pre-commit hooks
```
pre-commit install
```
##### Run linters
```
make lint
```
##### Format code
```
make format
```

#### Database Migrations

**bash**
 **Create new migration**
```
alembic revision --autogenerate -m "description"
```

 **Apply migrations**
 ```
alembic upgrade head
```
**Rollback**
```
alembic downgrade -1
```

#### **📈 Performance**

· **Response Time:** < 2 seconds for trade execution
· **Concurrent Users:** Supports 1000+ users
· **Uptime:** 99.9% with proper deployment
· **Rate Limits:** Configurable per user tier

#### **🔒 Security**

· **Password Encryption:** AES-256 encryption for MT5 passwords
· **JWT Tokens:** For API authentication
· **Rate Limiting:** Prevents brute force attacks
· **Input Validation:** All user input sanitized
· **SQL Injection:** Protected by SQLAlchemy ORM

#### **🚦 Error Handling**

The bot includes comprehensive error handling:

· Connection failures
· Invalid signals
· Insufficient balance
· Rate limit exceeded
· Database errors
· API timeouts

📊 Monitoring

· Prometheus Metrics available on port 9090
· Structured Logging with JSON format
· Sentry Integration for error tracking
· Performance Tracking for all operations

#### **🤝 Contributing**

1. Fork the repository
2. Create a feature branch (git checkout -b feature/AmazingFeature)
3. Commit changes (git commit -m 'Add AmazingFeature')
4. Push to branch (git push origin feature/AmazingFeature)
5. Open a Pull Request

#### **Development Guidelines**

· Follow PEP 8 style guide
· Add tests for new features
· Update documentation
· Keep backwards compatibility

#### **📄 License**

Distributed under the MIT License. See LICENSE for more information.

📞 Support

· Telegram: [FX-SIGNAL-COPIER](https://t.me/fxsignalcopier1bot)
· Email: support@fxsignalcopier.com
· Issues: GitHub Issues

##### **🙏 Acknowledgments**

· python-telegram-bot
· MetaAPI Cloud SDK
· SQLAlchemy
· All contributors and users

**⭐ Star History**

https://api.star-history.com/svg?repos=KAPKEPOT/fx-signal-copier&type=Date
