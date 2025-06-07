import { calendar_v3, google } from 'googleapis'
import { createClient } from './supabase'

// Rate limiting configuration
const RATE_LIMIT = {
  maxRequests: 100,
  perMinute: 1,
  retryAfter: 60, // seconds
}

// Retry configuration
const RETRY_CONFIG = {
  maxRetries: 3,
  initialDelay: 1000, // ms
  maxDelay: 10000, // ms
}

export class CalendarService {
  private calendar: calendar_v3.Calendar
  private requestCount: number = 0
  private lastRequestTime: number = 0
  private userTimezone: string

  constructor(accessToken: string, timezone: string = 'UTC') {
    this.calendar = google.calendar({
      version: 'v3',
      auth: accessToken,
    })
    this.userTimezone = timezone
  }

  private async checkRateLimit(): Promise<void> {
    const now = Date.now()
    const timeSinceLastRequest = now - this.lastRequestTime

    if (timeSinceLastRequest < (60 * 1000) / RATE_LIMIT.maxRequests) {
      const waitTime = (60 * 1000) / RATE_LIMIT.maxRequests - timeSinceLastRequest
      await new Promise(resolve => setTimeout(resolve, waitTime))
    }

    this.lastRequestTime = Date.now()
    this.requestCount++
  }

  private async retry<T>(operation: () => Promise<T>): Promise<T> {
    let lastError: Error | null = null
    let delay = RETRY_CONFIG.initialDelay

    for (let attempt = 0; attempt < RETRY_CONFIG.maxRetries; attempt++) {
      try {
        await this.checkRateLimit()
        return await operation()
      } catch (error) {
        lastError = error as Error
        if (error instanceof Error && error.message.includes('rateLimitExceeded')) {
          await new Promise(resolve => setTimeout(resolve, RATE_LIMIT.retryAfter * 1000))
          continue
        }
        if (attempt < RETRY_CONFIG.maxRetries - 1) {
          await new Promise(resolve => setTimeout(resolve, delay))
          delay = Math.min(delay * 2, RETRY_CONFIG.maxDelay)
          continue
        }
        throw error
      }
    }

    throw lastError
  }

  async listCalendars(): Promise<calendar_v3.Schema$CalendarList> {
    return this.retry(async () => {
      const response = await this.calendar.calendarList.list()
      return response.data
    })
  }

  async getEvents(calendarId: string, timeMin: string, timeMax: string): Promise<calendar_v3.Schema$Events> {
    return this.retry(async () => {
      const response = await this.calendar.events.list({
        calendarId,
        timeMin,
        timeMax,
        singleEvents: true,
        orderBy: 'startTime',
        timeZone: this.userTimezone,
      })
      return response.data
    })
  }

  async createEvent(calendarId: string, event: calendar_v3.Schema$Event): Promise<calendar_v3.Schema$Event> {
    // Ensure event times are in the user's timezone
    if (event.start?.dateTime) {
      event.start.timeZone = this.userTimezone
    }
    if (event.end?.dateTime) {
      event.end.timeZone = this.userTimezone
    }

    return this.retry(async () => {
      const response = await this.calendar.events.insert({
        calendarId,
        requestBody: event,
      })
      return response.data
    })
  }

  async updateEvent(calendarId: string, eventId: string, event: calendar_v3.Schema$Event): Promise<calendar_v3.Schema$Event> {
    // Ensure event times are in the user's timezone
    if (event.start?.dateTime) {
      event.start.timeZone = this.userTimezone
    }
    if (event.end?.dateTime) {
      event.end.timeZone = this.userTimezone
    }

    return this.retry(async () => {
      const response = await this.calendar.events.update({
        calendarId,
        eventId,
        requestBody: event,
      })
      return response.data
    })
  }

  async deleteEvent(calendarId: string, eventId: string): Promise<void> {
    return this.retry(async () => {
      await this.calendar.events.delete({
        calendarId,
        eventId,
      })
    })
  }

  // Timezone handling methods
  setTimezone(timezone: string): void {
    this.userTimezone = timezone
  }

  getTimezone(): string {
    return this.userTimezone
  }

  // Helper method to convert a date to the user's timezone
  convertToUserTimezone(date: Date): Date {
    return new Date(date.toLocaleString('en-US', { timeZone: this.userTimezone }))
  }

  // Helper method to format a date in the user's timezone
  formatDate(date: Date): string {
    return date.toLocaleString('en-US', {
      timeZone: this.userTimezone,
      dateStyle: 'full',
      timeStyle: 'long',
    })
  }
}

// Helper function to get calendar service instance
export async function getCalendarService(timezone?: string): Promise<CalendarService> {
  const supabase = createClient()
  const { data: { session } } = await supabase.auth.getSession()
  
  if (!session?.provider_token) {
    throw new Error('No provider token available')
  }

  return new CalendarService(session.provider_token, timezone)
} 