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

    // Optional: Try to log the webhook event in Supabase (don't fail if this doesn't work)
    try {
      const supabase = await createClient()
      
      // Check if we can connect to Supabase first
      const { data, error: testError } = await supabase.from('webhook_logs').select('count').limit(1)
      
      if (!testError) {
        const { error: logError } = await supabase
          .from('webhook_logs')
          .insert({
            type: 'telegram',
            payload: update,
            timestamp: new Date().toISOString()
          })

        if (logError) {
          console.warn('Could not log webhook to database (non-critical):', logError.message)
        } else {
          console.log('Webhook logged successfully to database')
        }
      } else {
        console.warn('webhook_logs table not available (non-critical):', testError.message)
      }
    } catch (supabaseError) {
      console.warn('Database logging unavailable (non-critical):', 
        supabaseError instanceof Error ? supabaseError.message : 'Unknown error'
      )
    }

    // Handle the message directly - this is the main functionality
    if (update.message) {
      const { message } = update
      const chatId = message.chat.id
      const telegramUserId = message.from?.id?.toString() || null
      const messageText = message.text || ''
      const messageDate = message.date ? new Date(message.date * 1000).toISOString() : new Date().toISOString()

      let contactId = null
      // Always initialize supabase client
      const supabase = await createClient()
      try {
        if (telegramUserId) {
          // Look up contact by telegram_id
          const { data: contactData, error: contactError } = await supabase
            .from('contacts')
            .select('id')
            .eq('telegram_id', telegramUserId)
            .maybeSingle()
          if (contactError) {
            console.warn('Error looking up contact:', contactError.message)
          } else if (contactData) {
            contactId = contactData.id
          } else {
            // No contact found, insert new contact
            const now = new Date().toISOString()
            const newContact = {
              telegram_id: telegramUserId,
              first_name: message.from?.first_name || null,
              last_name: message.from?.last_name || null,
              username: message.from?.username || null,
              language_code: message.from?.language_code || null,
              name: [message.from?.first_name, message.from?.last_name].filter(Boolean).join(' ') || message.from?.username || 'Unknown',
              created_at: now,
              updated_at: now
            }
            const { data: inserted, error: insertError } = await supabase
              .from('contacts')
              .insert(newContact)
              .select('id')
              .maybeSingle()
            if (insertError) {
              console.warn('Failed to insert new contact:', insertError.message)
            } else if (inserted) {
              contactId = inserted.id
              console.log('Inserted new contact for telegram_id', telegramUserId)
            }
          }
        }
      } catch (err) {
        console.warn('Supabase error during contact lookup/insert:', err)
      }

      // Log incoming message if contact found
      if (contactId) {
        try {
          const { error: logMsgError } = await supabase
            .from('messages')
            .insert({
              contact_id: contactId,
              sender: 'user',
              channel: 'telegram',
              content: messageText,
              status: 'sent',
              metadata: message,
              created_at: messageDate
            })
          if (logMsgError) {
            console.warn('Failed to log incoming message:', logMsgError.message)
          } else {
            console.log('Incoming message logged to messages table')
          }
        } catch (err) {
          console.warn('Error logging incoming message:', err)
        }
      }

      try {
        // Send a response based on the message content
        let response = 'Hello! I received your message.'
        
        if (message.text) {
          const text = message.text.toLowerCase()
          if (text.includes('/start')) {
            response = `Welcome! 🤖 I'm your Executive Assistant Bot. 

I can help you with:
• /schedule - Schedule meetings
• /meetings - View upcoming meetings  
• /help - Show available commands

What would you like to do?`
          } else if (text.includes('/help')) {
            response = `Available commands:
/start - Get started
/schedule - Schedule a new meeting
/meetings - View your meetings
/cancel - Cancel a meeting
/settings - Manage preferences

How can I assist you today?`
          } else if (text.includes('hello') || text.includes('hi')) {
            response = 'Hello! How can I help you today? Use /help to see what I can do.'
          } else {
            response = `I received: "${message.text}"\n\nI'm still learning! Use /help to see what I can do.`
          }
        }

        await bot.sendMessage(chatId, response)
        console.log('Response sent successfully to chat:', chatId)
        // Log outgoing bot response if contact found
        if (contactId) {
          try {
            const { error: logBotMsgError } = await supabase
              .from('messages')
              .insert({
                contact_id: contactId,
                sender: 'bot',
                channel: 'telegram',
                content: response,
                status: 'delivered',
                metadata: { chatId, response },
                created_at: new Date().toISOString()
              })
            if (logBotMsgError) {
              console.warn('Failed to log outgoing bot message:', logBotMsgError.message)
            } else {
              console.log('Outgoing bot message logged to messages table')
            }
          } catch (err) {
            console.warn('Error logging outgoing bot message:', err)
          }
        }
      } catch (botError) {
        console.error('Error sending bot response:', botError)
        // Don't fail the webhook if bot response fails
      }
    }

    // Always return success to Telegram
    const response = new Response(JSON.stringify({ status: 'ok' }), {
      status: 200,
      headers: RESPONSE_HEADERS
    })
    
    console.log('Webhook handled successfully:', {
      status: response.status,
      timestamp: new Date().toISOString()
    })
    
    return response
  } catch (error) {
    console.error('Critical error handling Telegram webhook:', error)
    
    // Even on error, return 200 to prevent Telegram from retrying
    const response = new Response(
      JSON.stringify({ 
        status: 'error_handled',
        message: 'Error logged, webhook acknowledged'
      }),
      { 
        status: 200,
        headers: RESPONSE_HEADERS
      }
    )
    
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