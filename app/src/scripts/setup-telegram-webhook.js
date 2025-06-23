require('dotenv').config({ path: '.env.local' });
const TelegramBot = require('node-telegram-bot-api');

async function setupWebhook() {
  try {
    const botToken = process.env.TELEGRAM_BOT_TOKEN;
    // Environment-aware webhook URL configuration
    const webhookUrl = process.env.TELEGRAM_WEBHOOK_URL || (process.env.NODE_ENV === 'production' ? 'https://athena-v3-rwuk.onrender.com/api/telegram/webhook' : 'http://localhost:3000/api/telegram/webhook');

    // Debug print
    console.log('Loaded TELEGRAM_BOT_TOKEN:', botToken);
    console.log('Using webhook URL:', webhookUrl);

    if (!botToken) {
      throw new Error('TELEGRAM_BOT_TOKEN is not set in environment variables');
    }

    if (!webhookUrl) {
      throw new Error('TELEGRAM_WEBHOOK_URL is not set in environment variables');
    }

    // Initialize bot with explicit API endpoint - use polling: false to avoid internal webhook server
    const bot = new TelegramBot(botToken, {
      apiRoot: 'https://api.telegram.org',
      polling: false
    });

    // Set webhook
    await bot.setWebHook(webhookUrl);
    console.log('✅ Webhook set successfully!');

    // Set commands
    const commands = [
      { command: 'start', description: 'Start the bot' },
      { command: 'help', description: 'Show help information' },
      { command: 'schedule', description: 'Schedule a new meeting' },
      { command: 'meetings', description: 'List your upcoming meetings' },
      { command: 'cancel', description: 'Cancel a meeting' },
      { command: 'settings', description: 'Configure your preferences' }
    ];

    await bot.setMyCommands(commands);
    console.log('✅ Commands set successfully!');

  } catch (error) {
    console.error('❌ Error setting up webhook:', error);
    process.exit(1);
  }
}

setupWebhook(); 