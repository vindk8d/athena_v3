import { NextResponse } from 'next/server'
import { getTelegramService } from '../../../../lib/telegram'
import { createClient } from '../../../../utils/supabase/server'

export async function POST(request: Request) {
  try {
    const update = await request.json()
    const supabase = await createClient()

    // Log the webhook event in Supabase
    const { error: logError } = await supabase
      .from('webhook_logs')
      .insert({
        type: 'telegram',
        payload: update,
        timestamp: new Date().toISOString()
      })

    if (logError) {
      console.error('Error logging webhook:', logError)
    }

    // Get Telegram service instance and handle the update
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