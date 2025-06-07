import TelegramBot from 'node-telegram-bot-api'
import { createClient } from './supabase'

// Bot commands configuration
const BOT_COMMANDS = [
  { command: 'start', description: 'Start the bot' },
  { command: 'help', description: 'Show help information' },
  { command: 'schedule', description: 'Schedule a new meeting' },
  { command: 'meetings', description: 'List your upcoming meetings' },
  { command: 'cancel', description: 'Cancel a meeting' },
  { command: 'settings', description: 'Configure your preferences' },
]

export class TelegramService {
  private bot: TelegramBot
  private webhookUrl: string

  constructor(token: string, webhookUrl: string) {
    this.bot = new TelegramBot(token, { polling: false })
    this.webhookUrl = webhookUrl
  }

  async setupWebhook(options?: {
    url?: string;
    max_connections?: number;
    allowed_updates?: string[];
  }): Promise<void> {
    try {
      console.log('Setting up webhook:', {
        webhookUrl: options?.url || this.webhookUrl,
        options,
        timestamp: new Date().toISOString()
      })
      
      await this.bot.setWebHook(options?.url || this.webhookUrl, {
        max_connections: options?.max_connections,
        allowed_updates: options?.allowed_updates
      })
      console.log('Webhook set successfully')
    } catch (error) {
      console.error('Error setting webhook:', error)
      throw error
    }
  }

  async getWebhookInfo(): Promise<{
    url: string
    isActive: boolean
    lastError?: string
    pendingUpdateCount: number
    maxConnections: number
    ipAddress?: string
  }> {
    try {
      console.log('Getting webhook info...')
      const info = await this.bot.getWebHookInfo()
      
      const result = {
        url: info.url || '',
        isActive: info.url === this.webhookUrl,
        lastError: info.last_error_message,
        pendingUpdateCount: info.pending_update_count || 0,
        maxConnections: info.max_connections || 40,
        ipAddress: info.ip_address
      }
      
      console.log('Webhook info retrieved:', {
        ...result,
        timestamp: new Date().toISOString()
      })
      
      return result
    } catch (error) {
      console.error('Error getting webhook info:', error)
      throw error
    }
  }

  async setupCommands(): Promise<void> {
    try {
      console.log('Setting up bot commands...')
      await this.bot.setMyCommands(BOT_COMMANDS)
      console.log('Bot commands set successfully')
    } catch (error) {
      console.error('Error setting bot commands:', error)
      throw error
    }
  }

  async handleUpdate(update: TelegramBot.Update): Promise<void> {
    if (!update.message) return

    const { message } = update
    const chatId = message.chat.id

    try {
      switch (message.text) {
        case '/start':
          await this.handleStart(chatId)
          break
        case '/help':
          await this.handleHelp(chatId)
          break
        case '/schedule':
          await this.handleSchedule(chatId)
          break
        case '/meetings':
          await this.handleMeetings(chatId)
          break
        case '/cancel':
          await this.handleCancel(chatId)
          break
        case '/settings':
          await this.handleSettings(chatId)
          break
        default:
          await this.handleUnknownCommand(chatId)
      }
    } catch (error) {
      console.error('Error handling message:', error)
      await this.bot.sendMessage(chatId, 'Sorry, something went wrong. Please try again later.')
    }
  }

  private async handleStart(chatId: number): Promise<void> {
    const welcomeMessage = `
Welcome to your Executive Assistant Bot! 🤖

I can help you manage your calendar and schedule meetings. Here's what you can do:

/schedule - Schedule a new meeting
/meetings - View your upcoming meetings
/cancel - Cancel a meeting
/settings - Configure your preferences
/help - Show this help message

To get started, use /schedule to create your first meeting!
    `
    await this.bot.sendMessage(chatId, welcomeMessage)
  }

  private async handleHelp(chatId: number): Promise<void> {
    const helpMessage = `
Here's how to use the bot:

📅 Schedule a Meeting:
/schedule - Start the scheduling process
Follow the prompts to set date, time, and participants

📋 View Meetings:
/meetings - See your upcoming meetings
You'll get a list of all your scheduled meetings

❌ Cancel a Meeting:
/cancel - Cancel an existing meeting
Select the meeting you want to cancel

⚙️ Settings:
/settings - Configure your preferences
Set your timezone and notification preferences

Need more help? Contact support at support@example.com
    `
    await this.bot.sendMessage(chatId, helpMessage)
  }

  private async handleSchedule(chatId: number): Promise<void> {
    // TODO: Implement scheduling flow
    await this.bot.sendMessage(chatId, 'Scheduling feature coming soon!')
  }

  private async handleMeetings(chatId: number): Promise<void> {
    // TODO: Implement meetings list
    await this.bot.sendMessage(chatId, 'Meetings list feature coming soon!')
  }

  private async handleCancel(chatId: number): Promise<void> {
    // TODO: Implement meeting cancellation
    await this.bot.sendMessage(chatId, 'Meeting cancellation feature coming soon!')
  }

  private async handleSettings(chatId: number): Promise<void> {
    // TODO: Implement settings
    await this.bot.sendMessage(chatId, 'Settings feature coming soon!')
  }

  private async handleUnknownCommand(chatId: number): Promise<void> {
    await this.bot.sendMessage(
      chatId,
      'I don\'t understand that command. Use /help to see available commands.'
    )
  }
}

// Helper function to get Telegram service instance
export async function getTelegramService(): Promise<TelegramService> {
  const supabase = createClient()
  const { data: { session } } = await supabase.auth.getSession()
  
  if (!session?.provider_token) {
    throw new Error('No provider token available')
  }

  const botToken = process.env.TELEGRAM_BOT_TOKEN
  const webhookUrl = process.env.TELEGRAM_WEBHOOK_URL

  if (!botToken || !webhookUrl) {
    throw new Error('Telegram bot token or webhook URL not configured')
  }

  return new TelegramService(botToken, webhookUrl)
} 