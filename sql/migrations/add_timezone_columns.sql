-- Add default_timezone column to user_details table
ALTER TABLE user_details 
ADD COLUMN IF NOT EXISTS default_timezone TEXT DEFAULT 'UTC';

-- Add calendar_timezone column to calendar_list table
ALTER TABLE calendar_list 
ADD COLUMN IF NOT EXISTS calendar_timezone TEXT DEFAULT 'UTC';

-- Update existing records to use UTC as default timezone
UPDATE user_details 
SET default_timezone = 'UTC' 
WHERE default_timezone IS NULL;

UPDATE calendar_list 
SET calendar_timezone = 'UTC' 
WHERE calendar_timezone IS NULL;

-- Add comments for documentation
COMMENT ON COLUMN user_details.default_timezone IS 'User''s default timezone for all calendar operations';
COMMENT ON COLUMN calendar_list.calendar_timezone IS 'Calendar''s native timezone from the provider'; 