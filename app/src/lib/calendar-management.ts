import { createClient } from './supabase'
import { getCalendarService } from './calendar'

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

/**
 * Sync user's calendars from Google Calendar API to calendar_list table
 */
export async function syncUserCalendars(userId: string): Promise<{ success: boolean; error?: string }> {
  try {
    const supabase = createClient()
    
    // Get calendar service to fetch calendars from Google
    const calendarService = await getCalendarService()
    const calendarResponse = await calendarService.listCalendars()
    
    // Handle Google Calendar API response structure
    const calendars = Array.isArray(calendarResponse) ? calendarResponse : calendarResponse?.items || []
    
    if (!calendars || calendars.length === 0) {
      return { success: false, error: 'No calendars found' }
    }
    
    // Get existing calendars from database
    const { data: existingCalendars, error: fetchError } = await supabase
      .from('calendar_list')
      .select('*')
      .eq('user_id', userId)
      .eq('calendar_type', 'google')
    
    if (fetchError) {
      return { success: false, error: `Database error: ${fetchError.message}` }
    }
    
    const existingCalendarIds = new Set(existingCalendars?.map(cal => cal.calendar_id) || [])
    
    // Prepare calendar entries for upsert
    const calendarEntries = calendars.map((calendar: any) => ({
      user_id: userId,
      calendar_id: calendar.id || '',
      calendar_name: calendar.summary || calendar.name || 'Unnamed Calendar',
      calendar_type: 'google',
      is_primary: calendar.primary || false,
      access_role: calendar.accessRole || 'reader',
      timezone: calendar.timeZone || calendar.timezone || 'UTC',
      to_include_in_check: existingCalendarIds.has(calendar.id) 
        ? existingCalendars?.find(cal => cal.calendar_id === calendar.id)?.to_include_in_check ?? true
        : true, // Default to true for new calendars
      metadata: {
        backgroundColor: calendar.backgroundColor,
        foregroundColor: calendar.foregroundColor,
        description: calendar.description
      },
      updated_at: new Date().toISOString()
    }))
    
    // Upsert calendars
    const { error: upsertError } = await supabase
      .from('calendar_list')
      .upsert(calendarEntries, {
        onConflict: 'user_id,calendar_id,calendar_type'
      })
    
    if (upsertError) {
      return { success: false, error: `Upsert error: ${upsertError.message}` }
    }
    
    return { success: true }
  } catch (error) {
    console.error('Error syncing calendars:', error)
    return { success: false, error: error instanceof Error ? error.message : 'Unknown error' }
  }
}

/**
 * Get user's calendar list with inclusion preferences
 */
export async function getUserCalendars(userId: string): Promise<CalendarListEntry[]> {
  const supabase = createClient()
  
  const { data: calendars, error } = await supabase
    .from('calendar_list')
    .select('*')
    .eq('user_id', userId)
    .eq('calendar_type', 'google')
    .order('is_primary', { ascending: false })
    .order('calendar_name')
  
  if (error) {
    console.error('Error fetching user calendars:', error)
    return []
  }
  
  return calendars || []
}

/**
 * Update calendar inclusion preference
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
 * Get calendars that should be included in availability checks
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
    console.error('Error fetching included calendars:', error)
    return []
  }
  
  return calendars?.map(cal => cal.calendar_id) || []
} 