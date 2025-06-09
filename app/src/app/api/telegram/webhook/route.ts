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
      let userDetails = null
      let userId = null

      // Always initialize supabase client
      const supabase = await createClient()
      
      try {
        // First, get the single user details (there should only be one user in the system)
        const { data: userDetailsData, error: userError } = await supabase
          .from('user_details')
          .select('*')
          .limit(1)
          .maybeSingle()

        if (userError) {
          console.warn('Error getting user details:', userError.message)
          await bot.sendMessage(chatId, "I'm sorry, but the system isn't properly configured yet. Please contact your administrator.")
          return new Response(JSON.stringify({ status: 'ok' }), {
            status: 200,
            headers: RESPONSE_HEADERS
          })
        }

        if (!userDetailsData) {
          console.warn('No user found in user_details table')
          await bot.sendMessage(chatId, "Hello! The system hasn't been set up yet. Please contact your administrator to configure the executive assistant.")
          return new Response(JSON.stringify({ status: 'ok' }), {
            status: 200,
            headers: RESPONSE_HEADERS
          })
        }

        userDetails = userDetailsData
        userId = userDetailsData.user_id
        console.log(`Acting as executive assistant for user: ${userDetails.name}`)

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
            // No contact found, insert new contact associated with the user
            const now = new Date().toISOString()
            const newContact = {
              telegram_id: telegramUserId,
              first_name: message.from?.first_name || null,
              last_name: message.from?.last_name || null,
              username: message.from?.username || null,
              language_code: message.from?.language_code || null,
              name: [message.from?.first_name, message.from?.last_name].filter(Boolean).join(' ') || message.from?.username || 'Unknown',
              user_contact_id: userDetails.id, // Link contact to the user via user_contact_id
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
              console.log(`Inserted new contact for telegram_id ${telegramUserId}, associated with user ${userDetails.name}`)
            }
          }
        }
      } catch (err) {
        console.warn('Supabase error during user/contact lookup:', err)
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
        // Send message to Python Executive Assistant server for processing
        let response = `Hello! I'm ${userDetails?.name || "your executive"}'s assistant. How may I help you?`
        
        if (contactId && messageText && userDetails && userId) {
          try {
            const pythonServerUrl = process.env.PYTHON_SERVER_URL || 'http://localhost:8000'
            
            // Get OAuth token for user's calendar access
            let oauthToken = null
            let oauthRefreshToken = null
            let oauthTokenExpiresAt = null
            let oauthMetadata = null
            try {
              // Get OAuth tokens from user_auth_credentials for Google
              const { data: userCred, error: tokenError } = await supabase
                .from('user_auth_credentials')
                .select('access_token, refresh_token, token_expires_at, metadata')
                .eq('user_id', userId)
                .eq('provider', 'google')
                .maybeSingle()

              if (tokenError) {
                console.warn('Error getting OAuth token from user_auth_credentials:', tokenError.message)
                oauthToken = null
              } else if (userCred?.access_token) {
                oauthToken = userCred.access_token
                oauthRefreshToken = userCred.refresh_token
                oauthTokenExpiresAt = userCred.token_expires_at
                oauthMetadata = userCred.metadata
                console.log('OAuth token found for user calendar access (user_auth_credentials)')
              } else {
                console.log('No OAuth token available for calendar access')
                response = `Hello! I'm ${userDetails.name}'s executive assistant. I notice the calendar isn't connected yet. To enable full scheduling capabilities, please:\n\n1. Visit the web interface at https://athena-v3-rwuk.onrender.com\n2. Sign in with Google account\n3. Grant calendar access permissions\n\nFor now, I can still help with general scheduling coordination!`
                // Continue processing even without calendar access for basic assistant functions
              }
            } catch (tokenError) {
              console.warn('Error getting OAuth token:', tokenError)
              oauthToken = null // Continue without calendar access
            }
            
            const langchainResponse = await fetch(`${pythonServerUrl}/process-message`, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
              },
              body: JSON.stringify({
                telegram_message: {
                  message_id: message.message_id,
                  chat_id: chatId,
                  user_id: telegramUserId ? parseInt(telegramUserId) : 0,
                  text: messageText,
                  timestamp: messageDate,
                  user_info: message.from
                },
                contact_id: contactId,
                user_id: userId, // The authenticated user's ID
                user_details: { // User details for executive assistant context
                  first_name: userDetails.name?.split(' ')[0] || userDetails.name,
                  last_name: userDetails.name?.split(' ').slice(1).join(' ') || '',
                  name: userDetails.name,
                  email: userDetails.email,
                  working_hours_start: userDetails.working_hours_start,
                  working_hours_end: userDetails.working_hours_end,
                  meeting_duration: userDetails.meeting_duration,
                  buffer_time: userDetails.buffer_time
                },
                conversation_history: [],
                oauth_access_token: oauthToken,
                oauth_refresh_token: oauthRefreshToken,
                oauth_token_expires_at: oauthTokenExpiresAt,
                oauth_metadata: oauthMetadata
              })
            })

            if (langchainResponse.ok) {
              const langchainData = await langchainResponse.json()
              response = langchainData.response
              console.log('Executive assistant response received:', {
                intent: langchainData.intent,
                extracted_info: langchainData.extracted_info,
                tools_used: langchainData.tools_used?.map((tool: any) => tool.tool) || []
              })
            } else {
              console.warn('Executive assistant server error:', langchainResponse.status)
              const errorText = await langchainResponse.text()
              console.warn('Error details:', errorText)
              response = `Hello! I'm ${userDetails.name}'s executive assistant. I'm experiencing some technical difficulties right now. Please try again in a moment, or let me know how I can help you coordinate with ${userDetails.name}.`
            }
          } catch (fetchError) {
            console.warn('Failed to connect to Executive Assistant server:', fetchError)
            // Fallback to executive assistant responses if server is unavailable
            const userName = userDetails.name || "your executive"
            if (messageText) {
              const text = messageText.toLowerCase()
              if (text.includes('/start') || text.includes('hello') || text.includes('hi')) {
                response = `Hello! I'm ${userName}'s executive assistant. I can help you:

• Schedule meetings with ${userName}
• Check ${userName}'s availability
• Coordinate meeting details
• Manage ${userName}'s calendar

How may I assist you in coordinating with ${userName} today?`
              } else if (text.includes('/help')) {
                response = `I'm ${userName}'s executive assistant. Here's how I can help:

📅 **Meeting Coordination**
• Schedule meetings with ${userName}
• Check availability
• Propose meeting times
• Send calendar invitations

💬 **Communication**
• Relay messages to ${userName}
• Coordinate meeting details
• Handle scheduling requests

Just tell me what meeting you'd like to schedule with ${userName}, and I'll take care of it!`
              } else if (text.includes('schedule') || text.includes('meeting') || text.includes('meet')) {
                response = `I'd be happy to help you schedule a meeting with ${userName}! 

To get started, please let me know:
• What's the purpose of the meeting?
• How long do you need (30 mins, 1 hour, etc.)?
• Any preferred dates or times?

I'll check ${userName}'s availability and propose suitable times.`
              } else {
                response = `Hello! I'm ${userName}'s executive assistant. I received your message: "${messageText}"

I can help you schedule meetings with ${userName}. Just let me know what you need, and I'll coordinate everything!`
              }
            }
          }
        } else {
          // Fallback response when user details aren't available
          response = "Hello! I'm an executive assistant, but I'm having trouble accessing the system configuration. Please try again or contact support."
        }

        await bot.sendMessage(chatId, response)
        console.log('Response sent successfully to chat:', chatId)
        
        // Log outgoing assistant response if contact found
        if (contactId) {
          try {
            const { error: logBotMsgError } = await supabase
              .from('messages')
              .insert({
                contact_id: contactId,
                sender: 'assistant',
                channel: 'telegram',
                content: response,
                status: 'delivered',
                metadata: { chatId, response, acting_for_user: userDetails?.name },
                created_at: new Date().toISOString()
              })
            if (logBotMsgError) {
              console.warn('Failed to log outgoing assistant message:', logBotMsgError.message)
            } else {
              console.log('Outgoing assistant message logged to messages table')
            }
          } catch (err) {
            console.warn('Error logging outgoing assistant message:', err)
          }
        }
      } catch (botError) {
        console.error('Error sending assistant response:', botError)
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