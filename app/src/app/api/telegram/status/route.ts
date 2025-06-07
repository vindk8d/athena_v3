import { NextResponse } from 'next/server'
import { getTelegramService } from '../../../lib/telegram'

export async function GET() {
  try {
    const telegramService = await getTelegramService()
    const webhookInfo = await telegramService.getWebhookInfo()

    return NextResponse.json({
      status: 'ok',
      webhook: {
        url: webhookInfo.url,
        isActive: webhookInfo.isActive,
        lastError: webhookInfo.lastError,
        pendingUpdates: webhookInfo.pendingUpdateCount,
        maxConnections: webhookInfo.maxConnections,
        ipAddress: webhookInfo.ipAddress
      },
      environment: {
        webhookUrl: process.env.TELEGRAM_WEBHOOK_URL,
        hasBotToken: !!process.env.TELEGRAM_BOT_TOKEN
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