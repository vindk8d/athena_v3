-- Add default_timezone column to user_details table
ALTER TABLE user_details 
ADD COLUMN IF NOT EXISTS default_timezone TEXT DEFAULT 'UTC';

-- Update existing records to use UTC as default timezone
UPDATE user_details 
SET default_timezone = 'UTC' 
WHERE default_timezone IS NULL;

-- Add comment for documentation
COMMENT ON COLUMN user_details.default_timezone IS 'User''s default timezone for all calendar operations'; 