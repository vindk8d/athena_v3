# Environment-Aware Configuration

This project automatically detects whether you're running in development or production and uses appropriate URLs accordingly.

## How It Works

The application uses environment variables with smart fallbacks:

- **Development** (`NODE_ENV=development`): Uses `localhost` URLs
- **Production** (`NODE_ENV=production`): Uses production URLs

## Files with Environment Detection

1. **`app/src/lib/calendar-management.ts`** - Backend API calls
2. **`python-server/config.py`** - Frontend URL configuration  
3. **`app/src/app/auth/callback/route.ts`** - Auth redirect URLs
4. **`app/src/scripts/setup-telegram-webhook.ts`** - Webhook setup
5. **`app/src/scripts/setup-telegram-webhook.js`** - Webhook setup (JS version)

## Local Development Setup

Your `.env.local` file should contain:

```bash
# Local development URLs (override production defaults)
PYTHON_SERVER_URL=http://localhost:8000
FRONTEND_URL=http://localhost:3000
NODE_ENV=development
TELEGRAM_WEBHOOK_URL=http://localhost:3000/api/telegram/webhook
NEXT_PUBLIC_TELEGRAM_BOT_USERNAME=athena_ea_bot
```

## Production Setup

In production, set these environment variables:

```bash
NODE_ENV=production
PYTHON_SERVER_URL=https://athena-v3-1.onrender.com
FRONTEND_URL=https://athena-v3-rwuk.onrender.com
TELEGRAM_WEBHOOK_URL=https://athena-v3-rwuk.onrender.com/api/telegram/webhook
```

## Benefits

✅ **No more manual code changes** when switching environments  
✅ **Automatic environment detection**  
✅ **Consistent configuration** across all services  
✅ **Easy deployment** - just set environment variables  
✅ **Safe fallbacks** to production URLs if NODE_ENV is not set

## Usage

- **Development**: Run `npm run dev` and `python3 main.py` - automatically uses localhost
- **Production**: Deploy with production environment variables - automatically uses production URLs
