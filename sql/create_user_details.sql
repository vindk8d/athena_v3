-- Create user_details table
CREATE TABLE IF NOT EXISTS user_details (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    first_name TEXT,
    last_name TEXT,
    email TEXT,
    working_hours_start TIME DEFAULT '09:00:00',
    working_hours_end TIME DEFAULT '17:00:00',
    meeting_duration INTEGER DEFAULT 30,
    buffer_time INTEGER DEFAULT 15,
    default_timezone TEXT DEFAULT 'UTC', -- Added default timezone column
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    
    -- Ensure one record per user
    UNIQUE (user_id)
);

-- Create calendar_list table to store user calendars with inclusion preferences
CREATE TABLE IF NOT EXISTS calendar_list (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    calendar_id TEXT NOT NULL,
    calendar_name TEXT NOT NULL,
    calendar_type TEXT DEFAULT 'google',
    is_primary BOOLEAN DEFAULT FALSE,
    access_role TEXT,
    calendar_timezone TEXT DEFAULT 'UTC', -- Added calendar timezone column
    to_include_in_check BOOLEAN DEFAULT TRUE,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    
    -- Ensure one record per user per calendar
    UNIQUE (user_id, calendar_id, calendar_type)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_user_details_user_id ON user_details(user_id);
CREATE INDEX IF NOT EXISTS idx_calendar_list_user_id ON calendar_list(user_id);
CREATE INDEX IF NOT EXISTS idx_calendar_list_user_include ON calendar_list(user_id, to_include_in_check) WHERE to_include_in_check = TRUE;
CREATE INDEX IF NOT EXISTS idx_calendar_list_primary ON calendar_list(user_id, is_primary) WHERE is_primary = TRUE;

-- Add comments for documentation
COMMENT ON TABLE user_details IS 'Stores user preferences and settings';
COMMENT ON COLUMN user_details.default_timezone IS 'User''s default timezone for all calendar operations';
COMMENT ON TABLE calendar_list IS 'Stores user calendars with preferences for availability checking';
COMMENT ON COLUMN calendar_list.calendar_timezone IS 'Calendar''s native timezone from the provider';

-- Add RLS policies
ALTER TABLE user_details ENABLE ROW LEVEL SECURITY;
ALTER TABLE calendar_list ENABLE ROW LEVEL SECURITY; 