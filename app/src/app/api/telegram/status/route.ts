import { NextResponse } from 'next/server'
import TelegramBot from 'node-telegram-bot-api'

export async function GET() {
  try {
    const botToken = process.env.TELEGRAM_BOT_TOKEN
    const webhookUrl = process.env.TELEGRAM_WEBHOOK_URL

    // Debug logging
    console.log('Environment check:', {
      hasToken: !!botToken,
      tokenLength: botToken?.length,
      hasWebhookUrl: !!webhookUrl,
      webhookUrl,
      timestamp: new Date().toISOString()
    })

    if (!botToken) {
      throw new Error('TELEGRAM_BOT_TOKEN is not configured')
    }

    // Validate token format
    if (!botToken.match(/^\d+:[A-Za-z0-9_-]{35}$/)) {
      throw new Error('TELEGRAM_BOT_TOKEN format is invalid')
    }

    // Use polling: false to avoid starting internal webhook server
    const bot = new TelegramBot(botToken, { polling: false })
    const info = await bot.getWebHookInfo()
    
    console.log('Webhook info from Telegram:', {
      url: info.url,
      has_custom_certificate: info.has_custom_certificate,
      pending_update_count: info.pending_update_count,
      last_error_date: info.last_error_date ? new Date(info.last_error_date * 1000).toISOString() : null,
      last_error_message: info.last_error_message,
      max_connections: info.max_connections,
      ip_address: info.ip_address,
      timestamp: new Date().toISOString()
    })

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
        hasBotToken: !!botToken,
        tokenFormat: 'valid'
      }
    })
  } catch (error) {
    console.error('Error checking webhook status:', error)
    return NextResponse.json(
      { 
        status: 'error',
        error: error instanceof Error ? error.message : 'Unknown error',
        debug: {
          hasToken: !!process.env.TELEGRAM_BOT_TOKEN,
          tokenLength: process.env.TELEGRAM_BOT_TOKEN?.length,
          hasWebhookUrl: !!process.env.TELEGRAM_WEBHOOK_URL,
          webhookUrl: process.env.TELEGRAM_WEBHOOK_URL,
          timestamp: new Date().toISOString()
        }
      },
      { status: 500 }
    )
  }
} 