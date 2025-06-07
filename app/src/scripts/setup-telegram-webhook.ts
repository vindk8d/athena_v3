import { TelegramService } from '../lib/telegram'

async function setupWebhook() {
  try {
    const botToken = process.env.TELEGRAM_BOT_TOKEN
    const webhookUrl = process.env.TELEGRAM_WEBHOOK_URL || 'https://athena-v3-rwuk.onrender.com/api/telegram/webhook'

    console.log('Setup environment:', {
      hasToken: !!botToken,
      tokenLength: botToken?.length,
      hasWebhookUrl: !!webhookUrl,
      webhookUrl,
      timestamp: new Date().toISOString()
    })

    if (!botToken) {
      throw new Error('TELEGRAM_BOT_TOKEN is not set in environment variables')
    }

    if (!webhookUrl) {
      throw new Error('TELEGRAM_WEBHOOK_URL is not set in environment variables')
    }

    const telegramService = new TelegramService(botToken, webhookUrl)
    
    // Get current webhook info before setting
    const beforeInfo = await telegramService.getWebhookInfo()
    console.log('Webhook info before setup:', {
      url: beforeInfo.url,
      isActive: beforeInfo.isActive,
      lastError: beforeInfo.lastError,
      pendingUpdateCount: beforeInfo.pendingUpdateCount,
      maxConnections: beforeInfo.maxConnections,
      ipAddress: beforeInfo.ipAddress,
      timestamp: new Date().toISOString()
    })
    
    // Set up webhook
    await telegramService.setupWebhook()
    
    // Get webhook info after setting
    const afterInfo = await telegramService.getWebhookInfo()
    console.log('Webhook info after setup:', {
      url: afterInfo.url,
      isActive: afterInfo.isActive,
      lastError: afterInfo.lastError,
      pendingUpdateCount: afterInfo.pendingUpdateCount,
      maxConnections: afterInfo.maxConnections,
      ipAddress: afterInfo.ipAddress,
      timestamp: new Date().toISOString()
    })
    
    // Set up commands
    await telegramService.setupCommands()
    
    console.log('✅ Webhook and commands set up successfully!')
  } catch (error) {
    console.error('❌ Error setting up webhook:', error)
    process.exit(1)
  }
}

setupWebhook() 