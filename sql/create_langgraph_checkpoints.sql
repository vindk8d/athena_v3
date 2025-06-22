-- Create the langgraph_checkpoints table for LangGraph state persistence
-- This table stores the conversation state for each thread (contact conversation)

CREATE TABLE IF NOT EXISTS langgraph_checkpoints (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    parent_checkpoint_id TEXT,
    type TEXT,
    checkpoint JSONB NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_langgraph_checkpoints_thread_id 
ON langgraph_checkpoints(thread_id);

CREATE INDEX IF NOT EXISTS idx_langgraph_checkpoints_created_at 
ON langgraph_checkpoints(created_at);

CREATE INDEX IF NOT EXISTS idx_langgraph_checkpoints_parent 
ON langgraph_checkpoints(parent_checkpoint_id);

-- Create a function to automatically update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_langgraph_checkpoints_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create trigger to automatically update updated_at
DROP TRIGGER IF EXISTS trigger_update_langgraph_checkpoints_updated_at ON langgraph_checkpoints;
CREATE TRIGGER trigger_update_langgraph_checkpoints_updated_at
    BEFORE UPDATE ON langgraph_checkpoints
    FOR EACH ROW
    EXECUTE FUNCTION update_langgraph_checkpoints_updated_at();

-- Add helpful comments
COMMENT ON TABLE langgraph_checkpoints IS 'Stores LangGraph conversation state checkpoints for persistent memory across sessions';
COMMENT ON COLUMN langgraph_checkpoints.thread_id IS 'Unique identifier for each conversation thread (format: athena_{user_id}_{contact_id})';
COMMENT ON COLUMN langgraph_checkpoints.checkpoint IS 'Complete conversation state including messages, summary, and metadata';
COMMENT ON COLUMN langgraph_checkpoints.metadata IS 'Additional metadata about the checkpoint'; 