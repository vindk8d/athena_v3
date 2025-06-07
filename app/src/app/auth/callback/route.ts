import { NextResponse } from 'next/server';
import { createClient } from '../../../utils/supabase/server';

export async function GET(request: Request) {
  const supabase = createClient();
  // Example: get the user session or handle callback logic
  // const { data: { user } } = await supabase.auth.getUser();
  // Redirect or handle as needed
  return NextResponse.redirect('/');
} 