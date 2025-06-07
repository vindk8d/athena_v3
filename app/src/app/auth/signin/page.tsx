'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { createClient } from '../../../utils/supabase/client';

export default function SignIn() {
  const supabase = createClient();

  useEffect(() => {
    const signInWithGoogle = async () => {
      const { error } = await supabase.auth.signInWithOAuth({
        provider: 'google',
        options: {
          redirectTo: `${window.location.origin}/auth/callback`,
        },
      });

      if (error) {
        console.error('Error signing in with Google:', error.message);
      }
    };

    signInWithGoogle();
  }, [supabase.auth]);

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="text-center">
        <h1 className="text-2xl font-bold mb-4">Signing in...</h1>
        <p>Please wait while we redirect you to Google.</p>
      </div>
    </div>
  );
} 