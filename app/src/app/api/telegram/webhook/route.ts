import { NextResponse } from 'next/server'
import TelegramBot from 'node-telegram-bot-api'
import { createClient } from '../../../../utils/supabase/server'

// Initialize bot with token
const bot = new TelegramBot(process.env.TELEGRAM_BOT_TOKEN!, { webHook: true })

export async function POST(request: Request) {
  try {
    const update = await request.json()
    const supabase = createClient()

    // Handle the message
    if (update.message) {
      const { message } = update
      const chatId = message.chat.id

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

      // Send a simple response
      await bot.sendMessage(chatId, 'Message received!')
    }

    return NextResponse.json({ status: 'ok' })
  } catch (error) {
    console.error('Error handling Telegram webhook:', error)
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    )
  }
} 