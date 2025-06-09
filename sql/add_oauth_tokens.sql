-- Add OAuth token fields to user_details table
ALTER TABLE user_details
ADD COLUMN IF NOT EXISTS oauth_access_token TEXT,
ADD COLUMN IF NOT EXISTS oauth_refresh_token TEXT,
ADD COLUMN IF NOT EXISTS oauth_token_expires_at TIMESTAMPTZ;

-- Create an index on user_id for faster OAuth token lookups
CREATE INDEX IF NOT EXISTS idx_user_details_oauth_tokens ON user_details(user_id) WHERE oauth_access_token IS NOT NULL;

-- Add comment for documentation
COMMENT ON COLUMN user_details.oauth_access_token IS 'Google OAuth 2.0 access token for Calendar API access';
COMMENT ON COLUMN user_details.oauth_refresh_token IS 'Google OAuth 2.0 refresh token for token renewal';
COMMENT ON COLUMN user_details.oauth_token_expires_at IS 'Timestamp when the access token expires'; 