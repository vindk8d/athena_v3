-- Migration: Add nickname fields to user_details and contacts tables
-- Created: 2024-01-15
-- Description: Add nickname fields for personalized addressing by Athena

-- Add nickname field to user_details table
DO $$ 
BEGIN 
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'user_details' 
        AND column_name = 'nickname'
    ) THEN 
        ALTER TABLE user_details ADD COLUMN nickname text;
        COMMENT ON COLUMN user_details.nickname IS 'User''s preferred nickname for personal address by Athena and colleagues';
        RAISE NOTICE 'Added nickname column to user_details table';
    ELSE
        RAISE NOTICE 'Column nickname already exists in user_details table';
    END IF; 
END $$;

-- Add nickname field to contacts table  
DO $$ 
BEGIN 
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'contacts' 
        AND column_name = 'nickname'
    ) THEN 
        ALTER TABLE contacts ADD COLUMN nickname text;
        COMMENT ON COLUMN contacts.nickname IS 'Contact''s preferred nickname for friendly addressing by Athena';
        RAISE NOTICE 'Added nickname column to contacts table';
    ELSE
        RAISE NOTICE 'Column nickname already exists in contacts table';
    END IF; 
END $$;

-- Optional: Update existing records to set nickname equal to name if nickname is NULL or empty
-- (Uncomment the following lines if you want to populate nicknames with existing names)

-- UPDATE user_details 
-- SET nickname = name 
-- WHERE nickname IS NULL OR nickname = '';

-- UPDATE contacts 
-- SET nickname = name 
-- WHERE nickname IS NULL OR nickname = '';

-- Verify the changes
SELECT 
    table_name, 
    column_name, 
    data_type, 
    is_nullable,
    col_description(pgc.oid, a.attnum) as column_comment
FROM information_schema.columns a
JOIN pg_class pgc ON pgc.relname = a.table_name
WHERE table_name IN ('user_details', 'contacts') 
AND column_name = 'nickname'
ORDER BY table_name, column_name; 