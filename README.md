# FX
 #### Setup Instructions

##### Option A: Local Development Setup

### bash
#####  1. Clone the repository
```
git clone https://github.com/KAPKEPOT/fx-signal-copier.git
cd fx-signal-copier
```

##### 2. Create virtual environment
```
python3 -m venv fx
```
```
source fx/bin/activate
```
##### On Windows:
```
venv\Scripts\activate
```

##### 3. Install dependencies
```
make install
```
**or**
```
pip install -r requirements.txt
```

##### 4. Copy environment file
```
cp .env.example .env
```

##### 5. Edit .env with your credentials
```
nano .env
```

###### 6. Setup database (using Docker for local)
```
docker-compose up -d postgres redis
```
##### 7. Run migrations
```
alembic upgrade head
```

##### 8. Run the bot
```
make run
```

**or**
```
python3 main.py
```

#### Option B: Docker Deployment

###### bash
# 1. Clone and setup
git clone https://github.com/yourusername/fx-signal-copier.git
cd fx-signal-copier

# 2. Create .env file with your credentials
cp .env.example .env
nano .env

# 3. Build and start all services
docker-compose up -d

# 4. Check logs
docker-compose logs -f

# 5. Run migrations (first time only)
docker-compose exec bot alembic upgrade head

# 6. Stop services
docker-compose down
```

Option C: Production Deployment on VPS

```bash
# 1. SSH into your VPS
ssh user@your-vps-ip

# 2. Install Docker and Docker Compose
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# 3. Clone repository
git clone https://github.com/yourusername/fx-signal-copier.git
cd fx-signal-copier

# 4. Configure environment
cp .env.example .env
nano .env
# Set production values:
# - DEBUG=false
# - USE_WEBHOOK=true (if using webhooks)
# - WEBHOOK_URL=https://your-domain.com
# - Strong ENCRYPTION_KEY and JWT_SECRET

# 5. Start services
docker-compose up -d

# 6. Setup Nginx reverse proxy (if using webhooks)
sudo apt install nginx
sudo nano /etc/nginx/sites-available/fx-bot

# Add configuration:
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://localhost:8443;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}

# 7. Setup SSL with Let's Encrypt
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com

# 8. Monitor logs
docker-compose logs -f bot
```

3. First Run Checklist

Before First Run:

· Create Telegram bot via @BotFather and get BOT_TOKEN
· Get MetaAPI token from https://app.metaapi.cloud
· Generate strong encryption key: python -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
· Generate JWT secret: python -c "import secrets; print(secrets.token_urlsafe(32))"
· Set ADMIN_USER_IDS to your Telegram user ID
· Configure database (PostgreSQL recommended)

Testing the Bot:

1. Start the bot:

```bash
make run
```

1. Test in Telegram:

· Find your bot on Telegram
· Send /start - Should see welcome message
· Send /register - Start registration flow
· Enter your MT5 demo account credentials
· Send /trade to test trading

1. Check logs:

```bash
tail -f logs/bot.log
```

4. Common Commands

Database Management

```bash
# Create new migration
make create-migration message="add_new_field"

# Run migrations
make migrate

# Rollback migration
alembic downgrade -1

# Reset database (dev only)
alembic downgrade base
alembic upgrade head
```

Monitoring

```bash
# Check bot status
docker-compose ps

# View logs
docker-compose logs -f bot

# Check database
docker-compose exec postgres psql -U fxuser -d fx_signal_copier

# Check Redis
docker-compose exec redis redis-cli ping
```

Admin Commands in Telegram

Once running, admins can use:

· /admin - Admin dashboard
· /stats - Quick stats
· /broadcast Hello everyone! - Send broadcast

5. Troubleshooting

Common Issues:

1. Database connection error:

```bash
# Check if PostgreSQL is running
docker-compose ps postgres

# Check logs
docker-compose logs postgres

# Verify connection string in .env
echo $DATABASE_URL
```

1. Redis connection error:

```bash
# Check Redis
docker-compose exec redis redis-cli ping
# Should return "PONG"
```

1. Bot not responding:

```bash
# Check bot logs
docker-compose logs -f bot

# Verify token in .env
grep BOT_TOKEN .env

# Test token manually
curl https://api.telegram.org/bot$BOT_TOKEN/getMe
```

1. MetaAPI connection issues:

```bash
# Check MetaAPI token
curl -H "auth-token: $METAAPI_TOKEN" https://mt-client-api-v1.agiliumtrade.agiliumtrade.ai/users/current/accounts
```

1. Permission errors:

```bash
# Fix log directory permissions
sudo chown -R $USER:$USER logs/
chmod 755 logs/
```

6. Production Checklist

Security:

· Use strong ENCRYPTION_KEY (32+ bytes)
· Use strong JWT_SECRET
· Enable SSL/TLS for webhooks
· Restrict database access
· Use environment variables, never hardcode secrets
· Regular security updates: docker-compose pull

Monitoring:

· Set up Prometheus metrics (port 9090)
· Configure Sentry for error tracking
· Set up log rotation
· Monitor disk space
· Set up alerts for critical errors

Backup:

```bash
# Backup database daily
docker-compose exec postgres pg_dump -U fxuser fx_signal_copier > backup_$(date +%Y%m%d).sql

# Backup .env file
cp .env .env.backup
```

Performance:

· Adjust connection pool sizes based on users
· Monitor Redis memory usage
· Set up database indexes
· Enable database query logging in development


Now you're ready to run your FX Signal Copier bot! 🚀
