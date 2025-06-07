import { NextResponse } from 'next/server'
import TelegramBot from 'node-telegram-bot-api'
import { createClient } from '../../../../utils/supabase/server'

// Initialize bot with token - use polling: false to avoid internal webhook server
const bot = new TelegramBot(process.env.TELEGRAM_BOT_TOKEN!, { polling: false })

// Define headers that will be used for all responses
const RESPONSE_HEADERS = {
  'Content-Type': 'application/json',
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
  'Cache-Control': 'no-store, no-cache, must-revalidate, proxy-revalidate',
  'Pragma': 'no-cache',
  'Expires': '0',
  'X-Content-Type-Options': 'nosniff',
  'X-Frame-Options': 'DENY',
  'X-XSS-Protection': '1; mode=block'
}

export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

export async function POST(request: Request) {
  try {
    // Log request details
    console.log('Webhook request received:', {
      method: request.method,
      url: request.url,
      headers: Object.fromEntries(request.headers.entries()),
      timestamp: new Date().toISOString()
    })
    
    const update = await request.json()
    console.log('Webhook payload:', JSON.stringify(update, null, 2))

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

    // Handle the message directly
    if (update.message) {
      const { message } = update
      const chatId = message.chat.id

      // Send a simple response
      await bot.sendMessage(chatId, 'Message received!')
    }

    // Create a direct response without using NextResponse
    const response = new Response(JSON.stringify({ status: 'ok' }), {
      status: 200,
      headers: RESPONSE_HEADERS
    })
    
    console.log('Sending response:', {
      status: response.status,
      headers: Object.fromEntries(response.headers.entries()),
      timestamp: new Date().toISOString()
    })
    
    return response
  } catch (error) {
    console.error('Error handling Telegram webhook:', error)
    
    // Create a direct error response
    const response = new Response(
      JSON.stringify({ 
        error: 'Internal server error',
        details: error instanceof Error ? error.message : 'Unknown error'
      }),
      { 
        status: 500,
        headers: RESPONSE_HEADERS
      }
    )
    
    console.log('Sending error response:', {
      status: response.status,
      headers: Object.fromEntries(response.headers.entries()),
      timestamp: new Date().toISOString()
    })
    
    return response
  }
}

// Handle OPTIONS requests for CORS
export async function OPTIONS() {
  console.log('OPTIONS request received for webhook')
  
  // Create a direct response for OPTIONS
  const response = new Response(null, {
    status: 204,
    headers: RESPONSE_HEADERS
  })
  
  console.log('Sending OPTIONS response:', {
    status: response.status,
    headers: Object.fromEntries(response.headers.entries()),
    timestamp: new Date().toISOString()
  })
  
  return response
} 