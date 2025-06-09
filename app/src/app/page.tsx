'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { createClient } from '../utils/supabase/client'
import { User } from '@supabase/supabase-js'
import { 
  syncUserCalendars, 
  getUserCalendars, 
  updateCalendarInclusion, 
  CalendarListEntry 
} from '../lib/calendar-management'

export default function Home() {
  const router = useRouter()
  const supabase = createClient()
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [calendarConnected, setCalendarConnected] = useState(false)
  const [calendars, setCalendars] = useState<CalendarListEntry[]>([])
  const [syncingCalendars, setSyncingCalendars] = useState(false)
  const [syncMessage, setSyncMessage] = useState('')

  useEffect(() => {
    const checkUser = async () => {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session) {
        router.push('/auth/signin')
        return
      }
      setUser(session.user)
      
      // Check if calendar access is available by querying user_auth_credentials
      try {
        const { data: userCred, error } = await supabase
          .from('user_auth_credentials')
          .select('access_token')
          .eq('user_id', session.user.id)
          .eq('provider', 'google')
          .maybeSingle()
        
        if (error) {
          console.warn('Error checking calendar connection:', error.message)
          setCalendarConnected(false)
        } else {
          const hasCalendarAccess = userCred?.access_token !== null && userCred?.access_token !== undefined
          setCalendarConnected(hasCalendarAccess)
          
          // If calendar is connected, sync calendars and load them
          if (hasCalendarAccess) {
            await syncCalendarsAndLoad(session.user.id)
          }
        }
      } catch (error) {
        console.error('Error checking calendar connection:', error)
        setCalendarConnected(false)
      }
      
      setLoading(false)
    }
    checkUser()
  }, [router, supabase])

  const syncCalendarsAndLoad = async (userId: string) => {
    setSyncingCalendars(true)
    setSyncMessage('Syncing calendars...')
    
    try {
      // Sync calendars from Google
      const syncResult = await syncUserCalendars(userId)
      if (syncResult.success) {
        setSyncMessage('Calendars synced successfully!')
        // Load calendars from database
        const userCalendars = await getUserCalendars(userId)
        setCalendars(userCalendars)
      } else {
        setSyncMessage(`Sync failed: ${syncResult.error}`)
      }
    } catch (error) {
      console.error('Error syncing calendars:', error)
      setSyncMessage('Error syncing calendars')
    } finally {
      setSyncingCalendars(false)
      setTimeout(() => setSyncMessage(''), 3000) // Clear message after 3 seconds
    }
  }

  const handleCalendarToggle = async (calendarId: string, currentValue: boolean) => {
    if (!user) return
    
    const newValue = !currentValue
    const result = await updateCalendarInclusion(user.id, calendarId, newValue)
    
    if (result.success) {
      // Update local state
      setCalendars(prev => 
        prev.map(cal => 
          cal.calendar_id === calendarId 
            ? { ...cal, to_include_in_check: newValue }
            : cal
        )
      )
    } else {
      console.error('Error updating calendar inclusion:', result.error)
    }
  }

  const handleSignOut = async () => {
    await supabase.auth.signOut()
    router.push('/auth/signin')
  }

  const handleConnectCalendar = async () => {
    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: `${window.location.origin}/auth/callback`,
        scopes: 'https://www.googleapis.com/auth/calendar https://www.googleapis.com/auth/calendar.events',
        queryParams: {
          access_type: 'offline',
          prompt: 'consent'
        }
      },
    })

    if (error) {
      console.error('Error connecting calendar:', error.message)
    }
  }

  const handleRefreshCalendars = async () => {
    if (!user) return
    await syncCalendarsAndLoad(user.id)
  }

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-xl">Loading...</div>
      </div>
    )
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center py-2">
      <main className="flex w-full flex-1 flex-col items-center justify-center px-20 text-center max-w-4xl">
        <h1 className="text-4xl font-bold mb-8">
          Welcome {user?.user_metadata?.full_name || user?.email || 'User'}
        </h1>
        <div className="space-y-6 w-full">
          <p className="text-lg">
            You are signed in as: {user?.email}
          </p>
          
          {/* Calendar Connection Status */}
          <div className="p-6 rounded-lg border border-gray-200 bg-white dark:bg-neutral-900 dark:text-white shadow-sm">
            <h2 className="text-xl font-semibold mb-4">Calendar Connection Status</h2>
            <div className="flex items-center justify-center space-x-2 mb-4">
              <div className={`w-3 h-3 rounded-full ${calendarConnected ? 'bg-green-500' : 'bg-red-500'}`}></div>
              <span className="text-lg">
                {calendarConnected ? 'Google Calendar Connected' : 'Google Calendar Not Connected'}
              </span>
            </div>
            {!calendarConnected && (
              <button
                onClick={handleConnectCalendar}
                className="bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded"
              >
                Connect Google Calendar
              </button>
            )}
          </div>

          {/* Calendar Management */}
          {calendarConnected && (
            <div className="p-6 rounded-lg border border-gray-200 bg-white dark:bg-neutral-900 dark:text-white shadow-sm">
              <div className="flex justify-between items-center mb-4">
                <h2 className="text-xl font-semibold text-black dark:text-white">Calendar Management</h2>
                <div className="flex space-x-2">
                  <button
                    onClick={handleRefreshCalendars}
                    disabled={syncingCalendars}
                    className="bg-green-500 hover:bg-green-700 disabled:bg-gray-400 text-white font-bold py-2 px-4 rounded text-sm"
                  >
                    {syncingCalendars ? 'Syncing...' : 'Refresh Calendars'}
                  </button>
                </div>
              </div>
              
              {syncMessage && (
                <div className={`mb-4 p-3 rounded text-sm ${
                  syncMessage.includes('successfully') ? 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-200' : 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-200'
                }`}>
                  {syncMessage}
                </div>
              )}
              
              <p className="text-sm text-black dark:text-white mb-4">
                Select which calendars to include when checking your availability:
              </p>
              
              {calendars.length === 0 ? (
                <div className="text-black dark:text-white text-center py-4">
                  No calendars found. Click "Refresh Calendars" to sync from Google.
                </div>
              ) : (
                <div className="space-y-3">
                  {calendars.map((calendar) => (
                    <div key={calendar.calendar_id} className="flex items-center justify-between p-3 border rounded bg-white dark:bg-neutral-900 hover:bg-gray-50 dark:hover:bg-neutral-800">
                      <div className="flex-1">
                        <div className="flex items-center space-x-2">
                          <span className="font-medium text-black dark:text-white">{calendar.calendar_name}</span>
                          {calendar.is_primary && (
                            <span className="bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200 text-xs px-2 py-1 rounded">Primary</span>
                          )}
                        </div>
                        <div className="text-sm text-black dark:text-white">
                          {calendar.access_role} • {calendar.timezone}
                        </div>
                      </div>
                      <label className="flex items-center cursor-pointer">
                        <input
                          type="checkbox"
                          checked={calendar.to_include_in_check}
                          onChange={() => handleCalendarToggle(calendar.calendar_id, calendar.to_include_in_check)}
                          className="sr-only"
                        />
                        <div className={`relative w-11 h-6 transition-colors duration-200 ease-in-out rounded-full ${
                          calendar.to_include_in_check ? 'bg-blue-600' : 'bg-gray-300 dark:bg-gray-700'
                        }`}>
                          <span className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white dark:bg-neutral-900 rounded-full transition-transform duration-200 ease-in-out ${
                            calendar.to_include_in_check ? 'transform translate-x-5' : ''
                          }`} />
                        </div>
                        <span className="ml-2 text-sm text-black dark:text-white">
                          {calendar.to_include_in_check ? 'Included' : 'Excluded'}
                        </span>
                      </label>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          <button
            onClick={handleSignOut}
            className="bg-red-500 hover:bg-red-700 text-white font-bold py-2 px-4 rounded"
          >
            Sign Out
          </button>
        </div>
      </main>
    </div>
  )
}
