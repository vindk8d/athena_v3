-- Migration: Rename to_include_in_check to to_read_by_agent
-- This field is used by the agent to determine which calendars to read, not for frontend filtering

-- Rename the column
ALTER TABLE calendar_list RENAME COLUMN to_include_in_check TO to_read_by_agent;

-- Update the index name to reflect the new column name
DROP INDEX IF EXISTS idx_calendar_list_user_include;
CREATE INDEX IF NOT EXISTS idx_calendar_list_user_agent_read ON calendar_list(user_id, to_read_by_agent) WHERE to_read_by_agent = TRUE;

-- Update the column comment
COMMENT ON COLUMN calendar_list.to_read_by_agent IS 'Whether this calendar should be read by the agent for availability checks and operations'; 