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
    const { error } = await supabase.auth.exchangeCodeForSession(code)
    
    // If successful (no error), redirect to homepage at domain root
    // Based on the page.tsx file, this will show a welcome page with user info and sign out button
    // e.g. if running locally: http://localhost:3000/
    // e.g. in production: https://your-domain.com/
    if (!error) {
      return NextResponse.redirect(new URL('/', requestUrl.origin))
    }
  }

  // Return the user to an error page with some instructions
  return NextResponse.redirect(new URL('/auth/auth-error', requestUrl.origin))
} 