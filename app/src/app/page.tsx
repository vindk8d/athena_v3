'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { createClient } from '../utils/supabase/client'
import { User } from '@supabase/supabase-js'
import { 
  syncUserCalendars, 
  getUserCalendars, 
  updateCalendarAgentAccess, 
  CalendarListEntry 
} from '../lib/calendar-management'

// Contact interface based on the database schema
interface Contact {
  id: string
  name: string
  email?: string
  telegram_id?: string
  telegram_onboard_token?: string
  first_name?: string
  last_name?: string
  nickname?: string
  user_contact_id?: string
  created_at: string
  updated_at: string
}

export default function Home() {
  const router = useRouter()
  const supabase = createClient()
  const [user, setUser] = useState<User | null>(null)
  const [userDetails, setUserDetails] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [calendarConnected, setCalendarConnected] = useState(false)
  const [calendars, setCalendars] = useState<CalendarListEntry[]>([])
  const [syncingCalendars, setSyncingCalendars] = useState(false)
  const [syncMessage, setSyncMessage] = useState('')
  
  // Contacts management state
  const [contacts, setContacts] = useState<Contact[]>([])
  const [loadingContacts, setLoadingContacts] = useState(false)
  const [editingContactId, setEditingContactId] = useState<string | null>(null)
  const [isAddingContact, setIsAddingContact] = useState(false)
  const [editForm, setEditForm] = useState<Partial<Contact>>({})
  const [newContactForm, setNewContactForm] = useState<Partial<Contact>>({
    name: '',
    email: '',
    first_name: '',
    last_name: '',
    nickname: ''
  })
  
  // Invitation state management
  const [inviteStates, setInviteStates] = useState<Record<string, {
    isGenerating: boolean
    inviteLink: string | null
    showCopied: boolean
  }>>({})

  useEffect(() => {
    const checkUser = async () => {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session) {
        router.push('/auth/signin')
        return
      }
      setUser(session.user)
      
      // Get user details
      try {
        const { data: userDetailsData, error } = await supabase
          .from('user_details')
          .select('*')
          .eq('user_id', session.user.id)
          .maybeSingle()
        
        if (userDetailsData) {
          setUserDetails(userDetailsData)
        }
      } catch (error) {
        console.error('Error fetching user details:', error)
      }
      
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
          
          // If calendar is connected, load calendars from database first
          if (hasCalendarAccess) {
            // Try to load existing calendars from database first
            const userCalendars = await getUserCalendars(session.user.id)
            if (userCalendars.length > 0) {
              // If calendars exist in database, just load them
              setCalendars(userCalendars)
            } else {
              // If no calendars in database, sync from Google
              await syncCalendarsAndLoad(session.user.id)
            }
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

  // Load contacts when userDetails is available
  useEffect(() => {
    if (userDetails?.id) {
      loadContacts()
    }
  }, [userDetails])

  const loadContacts = async () => {
    if (!userDetails?.id) return
    
    setLoadingContacts(true)
    try {
      const { data: contactsData, error } = await supabase
        .from('contacts')
        .select('*')
        .eq('user_contact_id', userDetails.id)
        .order('name', { ascending: true })
      
      if (error) {
        console.error('Error loading contacts:', error)
      } else {
        setContacts(contactsData || [])
      }
    } catch (error) {
      console.error('Error loading contacts:', error)
    } finally {
      setLoadingContacts(false)
    }
  }

  const syncCalendarsAndLoad = async (userId: string) => {
    setSyncingCalendars(true)
    
    try {
      // First, load existing calendars from database to show current settings quickly
      setSyncMessage('Loading current settings...')
      const existingCalendars = await getUserCalendars(userId)
      if (existingCalendars.length > 0) {
        setCalendars(existingCalendars)
      }
      
      // Then sync calendars from Google to ensure everything is up to date
      setSyncMessage('Syncing with Google Calendar...')
      const syncResult = await syncUserCalendars(userId)
      if (syncResult.success) {
        setSyncMessage('Calendars synced successfully!')
        // Load updated calendars from database
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
    const result = await updateCalendarAgentAccess(user.id, calendarId, newValue)
    
    if (result.success) {
      // Update local state
      setCalendars(prev => 
        prev.map(cal => 
          cal.calendar_id === calendarId 
            ? { ...cal, to_read_by_agent: newValue }
            : cal
        )
      )
    } else {
      console.error('Error updating calendar agent access:', result.error)
    }
  }

  const handleEditContact = (contact: Contact) => {
    setEditingContactId(contact.id)
    setEditForm(contact)
  }

  const handleCancelEdit = () => {
    setEditingContactId(null)
    setEditForm({})
  }

  const handleSaveContact = async () => {
    if (!editingContactId) return
    
    try {
      const { error } = await supabase
        .from('contacts')
        .update({
          name: editForm.name,
          email: editForm.email,
          first_name: editForm.first_name,
          last_name: editForm.last_name,
          nickname: editForm.nickname,
          updated_at: new Date().toISOString()
        })
        .eq('id', editingContactId)
      
      if (error) {
        console.error('Error updating contact:', error)
      } else {
        // Update local state
        setContacts(prev => 
          prev.map(contact => 
            contact.id === editingContactId 
              ? { ...contact, ...editForm }
              : contact
          )
        )
        setEditingContactId(null)
        setEditForm({})
      }
    } catch (error) {
      console.error('Error saving contact:', error)
    }
  }

  const handleAddContact = async () => {
    if (!userDetails?.id || !newContactForm.name) return
    
    try {
      const { data, error } = await supabase
        .from('contacts')
        .insert({
          name: newContactForm.name,
          email: newContactForm.email,
          first_name: newContactForm.first_name,
          last_name: newContactForm.last_name,
          nickname: newContactForm.nickname,
          user_contact_id: userDetails.id,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString()
        })
        .select()
        .single()
      
      if (error) {
        console.error('Error adding contact:', error)
      } else {
        setContacts(prev => [...prev, data])
        setNewContactForm({
          name: '',
          email: '',
          first_name: '',
          last_name: '',
          nickname: ''
        })
        setIsAddingContact(false)
      }
    } catch (error) {
      console.error('Error adding contact:', error)
    }
  }

  const generateInviteToken = () => {
    // Generate a UUID v4 token
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
      const r = Math.random() * 16 | 0
      const v = c == 'x' ? r : (r & 0x3 | 0x8)
      return v.toString(16)
    })
  }

  const handleGenerateTelegramInvite = async (contact: Contact) => {
    // Set generating state
    setInviteStates(prev => ({
      ...prev,
      [contact.id]: {
        isGenerating: true,
        inviteLink: null,
        showCopied: false
      }
    }))

    try {
      // Generate a unique onboard token
      const onboardToken = generateInviteToken()
      
      // Update the contact with the onboard token
      const { error } = await supabase
        .from('contacts')
        .update({
          telegram_onboard_token: onboardToken,
          updated_at: new Date().toISOString()
        })
        .eq('id', contact.id)

      if (error) {
        console.error('Error updating contact with onboard token:', error)
        throw error
      }

      // Generate the Telegram invite link with the token
      const botUsername = process.env.NEXT_PUBLIC_TELEGRAM_BOT_USERNAME || 'athena_ea_bot'
      const telegramLink = `https://t.me/${botUsername}?start=onboard_${onboardToken}`

      // Update local state
      setContacts(prev => 
        prev.map(c => 
          c.id === contact.id 
            ? { ...c, telegram_onboard_token: onboardToken }
            : c
        )
      )

      // Set the invite link state
      setInviteStates(prev => ({
        ...prev,
        [contact.id]: {
          isGenerating: false,
          inviteLink: telegramLink,
          showCopied: false
        }
      }))

    } catch (error) {
      console.error('Error generating invite:', error)
      setInviteStates(prev => ({
        ...prev,
        [contact.id]: {
          isGenerating: false,
          inviteLink: null,
          showCopied: false
        }
      }))
      alert('Failed to generate invite link. Please try again.')
    }
  }

  const handleCopyInviteLink = async (contact: Contact) => {
    const inviteState = inviteStates[contact.id]
    if (!inviteState?.inviteLink) return

    try {
      await navigator.clipboard.writeText(inviteState.inviteLink)
      
      // Show copied state
      setInviteStates(prev => ({
        ...prev,
        [contact.id]: {
          ...prev[contact.id],
          showCopied: true
        }
      }))

      // Reset copied state after 2 seconds
      setTimeout(() => {
        setInviteStates(prev => ({
          ...prev,
          [contact.id]: {
            ...prev[contact.id],
            showCopied: false
          }
        }))
      }, 2000)

    } catch (error) {
      // Fallback for browsers that don't support clipboard API
      const message = `Hi ${contact.name}! You can chat with my assistant here: ${inviteState.inviteLink}`
      prompt(`Copy and share this message with ${contact.name}:`, message)
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
                Control which calendars the AI agent can read for availability checks and scheduling:
              </p>
              
              {calendars.length === 0 ? (
                <div className="text-black dark:text-white text-center py-4">
                  No calendars found. Click "Refresh Calendars" to sync from Google.
                </div>
              ) : (
                <div className="space-y-3">
                  {calendars
                    .sort((a, b) => {
                      // Always place primary calendar first
                      if (a.is_primary && !b.is_primary) return -1;
                      if (!a.is_primary && b.is_primary) return 1;
                      // Then sort by calendar name
                      return a.calendar_name.localeCompare(b.calendar_name);
                    })
                    .map((calendar) => (
                    <div key={calendar.calendar_id} className="flex items-center justify-between p-3 border rounded bg-white dark:bg-neutral-900 hover:bg-gray-50 dark:hover:bg-neutral-800">
                      <div className="flex-1">
                        <div className="flex items-center space-x-2">
                          <span className="font-medium text-black dark:text-white">{calendar.calendar_name}</span>
                          {calendar.is_primary && (
                            <span className="bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200 text-xs px-2 py-1 rounded">Primary</span>
                          )}
                        </div>
                        <div className="text-xs text-gray-600 dark:text-gray-400 mt-1 text-left">
                          {calendar.access_role} • {calendar.timezone}
                        </div>
                      </div>
                      <label className="flex items-center cursor-pointer">
                        <input
                          type="checkbox"
                          checked={calendar.to_read_by_agent}
                          onChange={() => handleCalendarToggle(calendar.calendar_id, calendar.to_read_by_agent)}
                          className="sr-only"
                        />
                        <div className={`relative w-11 h-6 transition-colors duration-200 ease-in-out rounded-full ${
                          calendar.to_read_by_agent ? 'bg-blue-600' : 'bg-gray-300 dark:bg-gray-700'
                        }`}>
                          <span className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white dark:bg-neutral-900 rounded-full transition-transform duration-200 ease-in-out ${
                            calendar.to_read_by_agent ? 'transform translate-x-5' : ''
                          }`} />
                        </div>
                      </label>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Contacts Management */}
          <div className="p-6 rounded-lg border border-gray-200 bg-white dark:bg-neutral-900 dark:text-white shadow-sm">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-xl font-semibold text-black dark:text-white">Contacts Management</h2>
              <button
                onClick={() => loadContacts()}
                disabled={loadingContacts}
                className="bg-green-500 hover:bg-green-700 disabled:bg-gray-400 text-white font-bold py-2 px-4 rounded text-sm"
              >
                {loadingContacts ? 'Loading...' : 'Refresh Contacts'}
              </button>
            </div>
            
            <p className="text-sm text-black dark:text-white mb-4">
              Manage your contacts for scheduling meetings through Athena:
            </p>
            
            {contacts.length === 0 ? (
              <div className="text-black dark:text-white text-center py-4">
                No contacts found. Add your first contact below.
              </div>
            ) : (
              <div className="space-y-3 mb-4">
                {contacts.map((contact) => (
                  <div key={contact.id} className="flex items-center justify-between p-3 border rounded bg-white dark:bg-neutral-900 hover:bg-gray-50 dark:hover:bg-neutral-800">
                    <div className="flex-1">
                      {editingContactId === contact.id ? (
                        <div className="space-y-2">
                          <input
                            type="text"
                            value={editForm.name || ''}
                            onChange={(e) => setEditForm(prev => ({ ...prev, name: e.target.value }))}
                            placeholder="Full Name *"
                            className="w-full p-2 border rounded text-black dark:text-white bg-white dark:bg-neutral-800 dark:border-neutral-700"
                          />
                          <div className="grid grid-cols-2 gap-2">
                            <input
                              type="text"
                              value={editForm.first_name || ''}
                              onChange={(e) => setEditForm(prev => ({ ...prev, first_name: e.target.value }))}
                              placeholder="First Name"
                              className="p-2 border rounded text-black dark:text-white bg-white dark:bg-neutral-800 dark:border-neutral-700"
                            />
                            <input
                              type="text"
                              value={editForm.last_name || ''}
                              onChange={(e) => setEditForm(prev => ({ ...prev, last_name: e.target.value }))}
                              placeholder="Last Name"
                              className="p-2 border rounded text-black dark:text-white bg-white dark:bg-neutral-800 dark:border-neutral-700"
                            />
                          </div>
                          <input
                            type="email"
                            value={editForm.email || ''}
                            onChange={(e) => setEditForm(prev => ({ ...prev, email: e.target.value }))}
                            placeholder="Email"
                            className="w-full p-2 border rounded text-black dark:text-white bg-white dark:bg-neutral-800 dark:border-neutral-700"
                          />
                          <input
                            type="text"
                            value={editForm.nickname || ''}
                            onChange={(e) => setEditForm(prev => ({ ...prev, nickname: e.target.value }))}
                            placeholder="Nickname"
                            className="w-full p-2 border rounded text-black dark:text-white bg-white dark:bg-neutral-800 dark:border-neutral-700"
                          />
                        </div>
                      ) : (
                        <div>
                          <div className="font-medium text-black dark:text-white">
                            {contact.name}
                            {contact.nickname && contact.nickname !== contact.name && (
                              <span className="text-sm text-gray-600 dark:text-gray-400 ml-2">({contact.nickname})</span>
                            )}
                          </div>
                          <div className="text-sm text-gray-600 dark:text-gray-400">
                            {contact.email && (
                              <span>{contact.email}</span>
                            )}
                            {contact.first_name && contact.last_name && (
                              <span className="ml-2">• {contact.first_name} {contact.last_name}</span>
                            )}
                            {contact.telegram_id && (
                              <span className="ml-2 text-green-600">• Telegram Connected</span>
                            )}
                                                     </div>
                         </div>
                       )}
                       
                       {/* Show invite link if generated */}
                       {inviteStates[contact.id]?.inviteLink && (
                         <div className="mt-2 p-2 bg-blue-50 dark:bg-blue-900/20 rounded border border-blue-200 dark:border-blue-800">
                           <div className="text-xs text-blue-700 dark:text-blue-300 mb-1">
                             Telegram Invite Link:
                           </div>
                           <div className="text-sm font-mono text-blue-800 dark:text-blue-200 break-all">
                             {inviteStates[contact.id].inviteLink}
                           </div>
                         </div>
                       )}
                     </div>
                                         <div className="flex items-center space-x-2 ml-4">
                       {(() => {
                         const inviteState = inviteStates[contact.id]
                         const hasInviteLink = inviteState?.inviteLink
                         const isGenerating = inviteState?.isGenerating
                         const showCopied = inviteState?.showCopied

                         if (hasInviteLink) {
                           return (
                             <button
                               onClick={() => handleCopyInviteLink(contact)}
                               className={`${
                                 showCopied 
                                   ? 'bg-green-500 hover:bg-green-700' 
                                   : 'bg-blue-500 hover:bg-blue-700'
                               } text-white font-bold py-1 px-3 rounded text-sm flex items-center space-x-1`}
                               title={showCopied ? "Copied!" : "Copy Invite Link"}
                             >
                               <span>{showCopied ? '✓' : '📋'}</span>
                               <span>{showCopied ? 'Copied' : 'Copy Link'}</span>
                             </button>
                           )
                         } else {
                           return (
                             <button
                               onClick={() => handleGenerateTelegramInvite(contact)}
                               disabled={isGenerating}
                               className="bg-blue-500 hover:bg-blue-700 disabled:bg-gray-400 text-white font-bold py-1 px-3 rounded text-sm flex items-center space-x-1"
                               title="Generate Telegram Invite"
                             >
                               <span>📱</span>
                               <span>{isGenerating ? 'Generating...' : 'Invite'}</span>
                             </button>
                           )
                         }
                       })()}
                      {editingContactId === contact.id ? (
                        <div className="flex space-x-1">
                                                     <button
                             onClick={handleSaveContact}
                             className="bg-green-500 hover:bg-green-700 text-white font-bold py-1 px-3 rounded text-sm flex items-center space-x-1"
                             title="Save Changes"
                           >
                             <span>✓</span>
                             <span>Save</span>
                           </button>
                           <button
                             onClick={handleCancelEdit}
                             className="bg-gray-500 hover:bg-gray-700 text-white font-bold py-1 px-3 rounded text-sm flex items-center space-x-1"
                             title="Cancel Edit"
                           >
                             <span>✕</span>
                             <span>Cancel</span>
                           </button>
                        </div>
                      ) : (
                                                 <button
                           onClick={() => handleEditContact(contact)}
                           className="bg-orange-500 hover:bg-orange-700 text-white font-bold py-1 px-3 rounded text-sm flex items-center space-x-1"
                           title="Edit Contact"
                         >
                           <span>✏️</span>
                           <span>Edit</span>
                         </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Add Contact Section */}
            {isAddingContact ? (
              <div className="border rounded p-4 bg-gray-50 dark:bg-neutral-800">
                <h3 className="text-lg font-medium text-black dark:text-white mb-3">Add New Contact</h3>
                <div className="space-y-2">
                  <input
                    type="text"
                    value={newContactForm.name || ''}
                    onChange={(e) => setNewContactForm(prev => ({ ...prev, name: e.target.value }))}
                    placeholder="Full Name *"
                    className="w-full p-2 border rounded text-black dark:text-white bg-white dark:bg-neutral-700 dark:border-neutral-600"
                  />
                  <div className="grid grid-cols-2 gap-2">
                    <input
                      type="text"
                      value={newContactForm.first_name || ''}
                      onChange={(e) => setNewContactForm(prev => ({ ...prev, first_name: e.target.value }))}
                      placeholder="First Name"
                      className="p-2 border rounded text-black dark:text-white bg-white dark:bg-neutral-700 dark:border-neutral-600"
                    />
                    <input
                      type="text"
                      value={newContactForm.last_name || ''}
                      onChange={(e) => setNewContactForm(prev => ({ ...prev, last_name: e.target.value }))}
                      placeholder="Last Name"
                      className="p-2 border rounded text-black dark:text-white bg-white dark:bg-neutral-700 dark:border-neutral-600"
                    />
                  </div>
                  <input
                    type="email"
                    value={newContactForm.email || ''}
                    onChange={(e) => setNewContactForm(prev => ({ ...prev, email: e.target.value }))}
                    placeholder="Email"
                    className="w-full p-2 border rounded text-black dark:text-white bg-white dark:bg-neutral-700 dark:border-neutral-600"
                  />
                  <input
                    type="text"
                    value={newContactForm.nickname || ''}
                    onChange={(e) => setNewContactForm(prev => ({ ...prev, nickname: e.target.value }))}
                    placeholder="Nickname"
                    className="w-full p-2 border rounded text-black dark:text-white bg-white dark:bg-neutral-700 dark:border-neutral-600"
                  />
                </div>
                <div className="flex space-x-2 mt-4">
                                     <button
                     onClick={handleAddContact}
                     disabled={!newContactForm.name}
                     className="bg-green-500 hover:bg-green-700 disabled:bg-gray-400 text-white font-bold py-2 px-4 rounded text-sm flex items-center space-x-1"
                   >
                     <span>✓</span>
                     <span>Add Contact</span>
                   </button>
                   <button
                     onClick={() => {
                       setIsAddingContact(false)
                       setNewContactForm({
                         name: '',
                         email: '',
                         first_name: '',
                         last_name: '',
                         nickname: ''
                       })
                     }}
                     className="bg-gray-500 hover:bg-gray-700 text-white font-bold py-2 px-4 rounded text-sm flex items-center space-x-1"
                   >
                     <span>✕</span>
                     <span>Cancel</span>
                   </button>
                </div>
              </div>
            ) : (
              <button
                onClick={() => setIsAddingContact(true)}
                className="w-full bg-blue-500 hover:bg-blue-700 text-white font-bold py-3 px-4 rounded text-sm border-2 border-dashed border-blue-300 dark:border-blue-600"
              >
                + Add New Contact
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
