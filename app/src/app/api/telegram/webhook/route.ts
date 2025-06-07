<<<<<<< HEAD
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
=======
import { NextResponse } from 'next/server';
import { createClient } from '../../../../utils/supabase/server';

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const supabase = createClient();
    // Handle the webhook logic here, e.g., verify/update user, log event, etc.
    // Example: const { data, error } = await supabase.from('users').select('*');
    return NextResponse.json({ success: true });
  } catch (error) {
    console.error('Error handling Telegram webhook:', error);
    return NextResponse.json({ success: false, error: 'Internal Server Error' }, { status: 500 });
>>>>>>> athena-renamed
  }
} 