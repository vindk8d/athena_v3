-- Migration: Add telegram_onboard_token field to contacts table
-- Created: 2024-01-16
-- Description: Add telegram onboarding token field for mapping invited contacts to their database entries

-- Add telegram_onboard_token field to contacts table
DO $$ 
BEGIN 
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'contacts' 
        AND column_name = 'telegram_onboard_token'
    ) THEN 
        ALTER TABLE contacts ADD COLUMN telegram_onboard_token uuid;
        COMMENT ON COLUMN contacts.telegram_onboard_token IS 'Temporary UUID token used for mapping invited contacts when they first interact with the Telegram bot';
        RAISE NOTICE 'Added telegram_onboard_token column to contacts table';
    ELSE
        RAISE NOTICE 'Column telegram_onboard_token already exists in contacts table';
    END IF; 
END $$;

-- Create index for performance on telegram_onboard_token lookups
CREATE INDEX IF NOT EXISTS idx_contacts_telegram_onboard_token 
ON contacts(telegram_onboard_token) 
WHERE telegram_onboard_token IS NOT NULL;

-- Verify the changes
SELECT 
    table_name, 
    column_name, 
    data_type, 
    is_nullable,
    col_description(pgc.oid, a.attnum) as column_comment
FROM information_schema.columns a
JOIN pg_class pgc ON pgc.relname = a.table_name
WHERE table_name = 'contacts' 
AND column_name = 'telegram_onboard_token'; 