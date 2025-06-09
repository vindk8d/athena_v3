'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { createClient } from '../utils/supabase/client'
import { User } from '@supabase/supabase-js'

export default function Home() {
  const router = useRouter()
  const supabase = createClient()
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [calendarConnected, setCalendarConnected] = useState(false)

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
        }
      } catch (error) {
        console.error('Error checking calendar connection:', error)
        setCalendarConnected(false)
      }
      
      setLoading(false)
    }
    checkUser()
  }, [router, supabase])

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

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-xl">Loading...</div>
      </div>
    )
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center py-2">
      <main className="flex w-full flex-1 flex-col items-center justify-center px-20 text-center">
        <h1 className="text-4xl font-bold mb-8">
          Welcome {user?.user_metadata?.full_name || user?.email || 'User'}
        </h1>
        <div className="space-y-4">
          <p className="text-lg">
            You are signed in as: {user?.email}
          </p>
          
          {/* Calendar Connection Status */}
          <div className="mt-6 p-4 rounded-lg border border-gray-200">
            <h2 className="text-xl font-semibold mb-2">Calendar Connection Status</h2>
            <div className="flex items-center justify-center space-x-2">
              <div className={`w-3 h-3 rounded-full ${calendarConnected ? 'bg-green-500' : 'bg-red-500'}`}></div>
              <span className="text-lg">
                {calendarConnected ? 'Google Calendar Connected' : 'Google Calendar Not Connected'}
              </span>
            </div>
            {!calendarConnected && (
              <button
                onClick={handleConnectCalendar}
                className="mt-4 bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded"
              >
                Connect Google Calendar
              </button>
            )}
          </div>

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
