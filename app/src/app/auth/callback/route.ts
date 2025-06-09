import { createServerClient, type CookieOptions } from '@supabase/ssr'
import { cookies } from 'next/headers'
import { NextResponse } from 'next/server'

export async function GET(request: Request) {
  const requestUrl = new URL(request.url)
  const code = requestUrl.searchParams.get('code')

  if (code) {
    const cookieStore = await cookies()
    const supabase = createServerClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL!,
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
      {
        cookies: {
          get(name: string) {
            return cookieStore.get(name)?.value
          },
          set(name: string, value: string, options: CookieOptions) {
            cookieStore.set({ name, value, ...options })
          },
          remove(name: string, options: CookieOptions) {
            cookieStore.set({ name, value: '', ...options })
          },
        },
      }
    )

    // Exchange the temporary auth code for a session
    const { data, error } = await supabase.auth.exchangeCodeForSession(code)
    
    // If successful (no error), store OAuth tokens in user_auth_credentials and redirect to homepage
    if (!error && data.session && data.session.user) {
      try {
        const user = data.session.user
        const accessToken = data.session.provider_token
        const refreshToken = data.session.provider_refresh_token
        
        // Calculate token expiration (typically 1 hour for Google)
        const expiresAt = new Date(Date.now() + 3600 * 1000) // 1 hour from now
        
        if (accessToken) {
          // Store or update OAuth tokens in user_auth_credentials table
          const { error: upsertError } = await supabase
            .from('user_auth_credentials')
            .upsert({
              user_id: user.id,
              provider: 'google',
              access_token: accessToken,
              refresh_token: refreshToken,
              token_expires_at: expiresAt.toISOString(),
              metadata: {},
              updated_at: new Date().toISOString(),
              created_at: new Date().toISOString()
            }, {
              onConflict: 'user_id,provider'
            })
          
          if (upsertError) {
            console.error('Error storing OAuth tokens:', upsertError.message)
          } else {
            console.log('OAuth tokens stored successfully for user:', user.id)
          }
        }
      } catch (tokenError) {
        console.error('Error processing OAuth tokens:', tokenError)
      }
      
      return NextResponse.redirect(new URL('/', requestUrl.origin))
    }
  }

  // Return the user to an error page with some instructions
  return NextResponse.redirect(new URL('/auth/auth-error', requestUrl.origin))
} 