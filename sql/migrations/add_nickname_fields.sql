-- Migration: Add nickname fields to user_details and contacts tables
-- Created: 2024-01-xx
-- Description: Add nickname fields for personalized addressing by Athena

-- Add nickname field to user_details table
ALTER TABLE user_details 
ADD COLUMN IF NOT EXISTS nickname text;

-- Add comment for the user_details nickname column
COMMENT ON COLUMN user_details.nickname IS 'User''s preferred nickname for personal address by Athena and colleagues';

-- Add nickname field to contacts table  
ALTER TABLE contacts
ADD COLUMN IF NOT EXISTS nickname text;

-- Add comment for the contacts nickname column
COMMENT ON COLUMN contacts.nickname IS 'Contact''s preferred nickname for friendly addressing by Athena';

-- Update any existing records to set nickname to name if nickname is empty
-- (Optional - can be run separately if needed)
-- UPDATE user_details SET nickname = name WHERE nickname IS NULL OR nickname = '';
-- UPDATE contacts SET nickname = name WHERE nickname IS NULL OR nickname = ''; 