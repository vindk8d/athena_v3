import { NextResponse } from 'next/server'
import { getTelegramService } from '@/lib/telegram'

export async function POST(request: Request) {
  try {
    const update = await request.json()
    const telegramService = await getTelegramService()
    await telegramService.handleUpdate(update)
    return NextResponse.json({ status: 'ok' })
  } catch (error) {
    console.error('Error handling Telegram webhook:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
} 