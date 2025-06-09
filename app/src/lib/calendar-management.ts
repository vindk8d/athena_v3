import { createClient } from './supabase'

export interface CalendarInfo {
  id: string
  name: string
  primary: boolean
  accessRole: string
  timezone: string
  selected?: boolean
}

export interface CalendarListEntry {
  id: string
  user_id: string
  calendar_id: string
  calendar_name: string
  calendar_type: string
  is_primary: boolean
  access_role: string
  timezone: string
  to_include_in_check: boolean
  metadata: any
  created_at: string
  updated_at: string
}

const PYTHON_BACKEND_URL = process.env.PYTHON_SERVER_URL || 'https://athena-v3-1.onrender.com';

/**
 * Sync user's calendars by calling the Python backend
 */
export async function syncUserCalendars(userId: string): Promise<{ success: boolean; error?: string }> {
  try {
    const res = await fetch(`${PYTHON_BACKEND_URL}/sync-calendars?user_id=${encodeURIComponent(userId)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });
    const data = await res.json();
    return data;
  } catch (error) {
    return { success: false, error: error instanceof Error ? error.message : 'Unknown error' };
  }
}

/**
 * Get user's calendar list from the Python backend
 */
export async function getUserCalendars(userId: string): Promise<CalendarListEntry[]> {
  try {
    const res = await fetch(`${PYTHON_BACKEND_URL}/get-calendars?user_id=${encodeURIComponent(userId)}`);
    const data = await res.json();
    if (data.success) return data.calendars;
    return [];
  } catch (error) {
    return [];
  }
}

/**
 * Update calendar inclusion preference in Supabase directly (no change needed)
 */
export async function updateCalendarInclusion(
  userId: string, 
  calendarId: string, 
  toInclude: boolean
): Promise<{ success: boolean; error?: string }> {
  const supabase = createClient()
  const { error } = await supabase
    .from('calendar_list')
    .update({ 
      to_include_in_check: toInclude,
      updated_at: new Date().toISOString()
    })
    .eq('user_id', userId)
    .eq('calendar_id', calendarId)
    .eq('calendar_type', 'google')
  if (error) {
    return { success: false, error: error.message }
  }
  return { success: true }
}

/**
 * Get calendars that should be included in availability checks (from Supabase)
 */
export async function getIncludedCalendars(userId: string): Promise<string[]> {
  const supabase = createClient()
  const { data: calendars, error } = await supabase
    .from('calendar_list')
    .select('calendar_id')
    .eq('user_id', userId)
    .eq('calendar_type', 'google')
    .eq('to_include_in_check', true)
  if (error) {
    return []
  }
  return calendars?.map(cal => cal.calendar_id) || []
} 