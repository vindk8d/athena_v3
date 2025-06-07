import { TelegramService } from '../lib/telegram'

async function setupWebhook() {
  try {
    const botToken = process.env.TELEGRAM_BOT_TOKEN
    const webhookUrl = process.env.TELEGRAM_WEBHOOK_URL || 'https://athena-v3-rwuk.onrender.com/api/telegram/webhook'

    if (!botToken) {
      throw new Error('TELEGRAM_BOT_TOKEN is not set in environment variables')
    }

    if (!webhookUrl) {
      throw new Error('TELEGRAM_WEBHOOK_URL is not set in environment variables')
    }

    const telegramService = new TelegramService(botToken, webhookUrl)
    await telegramService.setupWebhook()
    await telegramService.setupCommands()
    
    console.log('✅ Webhook and commands set up successfully!')
  } catch (error) {
    console.error('❌ Error setting up webhook:', error)
    process.exit(1)
  }
}

setupWebhook() 