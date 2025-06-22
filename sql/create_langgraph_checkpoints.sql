-- Create table for LangGraph checkpoints using Supabase REST API
-- This replaces the need for direct PostgreSQL connection

CREATE TABLE IF NOT EXISTS langgraph_checkpoints (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    thread_id TEXT NOT NULL,
    checkpoint_data JSONB NOT NULL,
    metadata JSONB DEFAULT '{}',
    parent_config JSONB DEFAULT '{}',
    pending_writes JSONB DEFAULT '[]',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_langgraph_checkpoints_thread_id 
ON langgraph_checkpoints(thread_id);

CREATE INDEX IF NOT EXISTS idx_langgraph_checkpoints_created_at 
ON langgraph_checkpoints(created_at DESC);

-- Add RLS policies for security
ALTER TABLE langgraph_checkpoints ENABLE ROW LEVEL SECURITY;

-- Policy: Users can only access their own checkpoints
-- Note: This assumes user_id is stored in the thread_id or metadata
CREATE POLICY "Users can access their own checkpoints" ON langgraph_checkpoints
    FOR ALL USING (
        -- Allow access if the thread_id contains the user's ID
        -- Thread ID format: athena_{user_id}_{contact_id}
        thread_id LIKE 'athena_' || auth.uid() || '_%'
        OR
        -- Or if using service role key (for server-side operations)
        auth.role() = 'service_role'
    );

-- Grant necessary permissions
GRANT ALL ON langgraph_checkpoints TO authenticated;
GRANT ALL ON langgraph_checkpoints TO service_role;

-- Optional: Add cleanup policy to remove old checkpoints
-- Keep only the last 10 checkpoints per thread
CREATE OR REPLACE FUNCTION cleanup_old_checkpoints()
RETURNS void AS $$
BEGIN
    WITH ranked_checkpoints AS (
        SELECT id, 
               ROW_NUMBER() OVER (PARTITION BY thread_id ORDER BY created_at DESC) as rn
        FROM langgraph_checkpoints
    )
    DELETE FROM langgraph_checkpoints 
    WHERE id IN (
        SELECT id FROM ranked_checkpoints WHERE rn > 10
    );
END;
$$ LANGUAGE plpgsql;

-- Optional: Create a scheduled job to run cleanup (if pg_cron is available)
-- SELECT cron.schedule('cleanup-checkpoints', '0 2 * * *', 'SELECT cleanup_old_checkpoints();'); 