import { NextResponse } from 'next/server'
import TelegramBot from 'node-telegram-bot-api'

export async function GET() {
  try {
    const botToken = process.env.TELEGRAM_BOT_TOKEN
    const webhookUrl = process.env.TELEGRAM_WEBHOOK_URL

    if (!botToken) {
      throw new Error('TELEGRAM_BOT_TOKEN is not configured')
    }

    const bot = new TelegramBot(botToken, { webHook: true })
    const info = await bot.getWebHookInfo()

    return NextResponse.json({
      status: 'ok',
      webhook: {
        url: info.url || '',
        isActive: info.url === webhookUrl,
        lastError: info.last_error_message,
        pendingUpdates: info.pending_update_count || 0,
        maxConnections: info.max_connections || 40,
        ipAddress: info.ip_address
      },
      environment: {
        webhookUrl: webhookUrl,
        hasBotToken: !!botToken
      }
    })
  } catch (error) {
    console.error('Error checking webhook status:', error)
    return NextResponse.json(
      { 
        status: 'error',
        error: error instanceof Error ? error.message : 'Unknown error'
      },
      { status: 500 }
    )
  }
} 