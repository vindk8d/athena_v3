-- Create calendar_list table to store user calendars with inclusion preferences
CREATE TABLE IF NOT EXISTS calendar_list (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    calendar_id TEXT NOT NULL, -- Google Calendar ID (e.g., "jose.alvin.perez@gmail.com")
    calendar_name TEXT NOT NULL, -- Display name (e.g., "Vin's Calendar")
    calendar_type TEXT DEFAULT 'google', -- Provider type for future extensibility
    is_primary BOOLEAN DEFAULT FALSE, -- Whether this is the user's primary calendar
    access_role TEXT, -- Google Calendar access role (owner, reader, freeBusyReader, etc.)
    timezone TEXT DEFAULT 'UTC', -- Calendar timezone
    to_include_in_check BOOLEAN DEFAULT TRUE, -- Whether to include in availability checks
    metadata JSONB DEFAULT '{}', -- Additional calendar metadata
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    
    -- Ensure one record per user per calendar
    UNIQUE (user_id, calendar_id, calendar_type)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_calendar_list_user_id ON calendar_list(user_id);
CREATE INDEX IF NOT EXISTS idx_calendar_list_user_include ON calendar_list(user_id, to_include_in_check) WHERE to_include_in_check = TRUE;
CREATE INDEX IF NOT EXISTS idx_calendar_list_primary ON calendar_list(user_id, is_primary) WHERE is_primary = TRUE;

-- Add comments for documentation
COMMENT ON TABLE calendar_list IS 'Stores user calendars with preferences for availability checking';
COMMENT ON COLUMN calendar_list.calendar_id IS 'Provider-specific calendar identifier (e.g., Google Calendar ID)';
COMMENT ON COLUMN calendar_list.to_include_in_check IS 'Whether this calendar should be included in availability checks';
COMMENT ON COLUMN calendar_list.metadata IS 'Additional provider-specific calendar information';

-- Add RLS policy for multi-user security
ALTER TABLE calendar_list ENABLE ROW LEVEL SECURITY;

-- Drop existing policies if they exist
DROP POLICY IF EXISTS "Users can manage their own calendars" ON calendar_list;
DROP POLICY IF EXISTS "Service role can manage all calendars" ON calendar_list;

-- Policy: Users can only access their own calendars
CREATE POLICY "Users can manage their own calendars" ON calendar_list
    FOR ALL USING (auth.uid() = user_id);

-- Policy: Service role can manage all calendars
CREATE POLICY "Service role can manage all calendars" ON calendar_list
    FOR ALL USING (auth.role() = 'service_role'); 