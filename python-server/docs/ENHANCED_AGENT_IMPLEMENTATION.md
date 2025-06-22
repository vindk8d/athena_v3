# Enhanced Athena Agent Implementation

This document describes the enhanced implementation of the Athena agent in `agent_main.py` with three major improvements:

1. **LangGraph Checkpointing with PostgreSQL/Supabase**
2. **Periodic Archiving to Messages Table**
3. **Conversation Summarization and Trimming**

## Architecture Overview

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   New Message   │───▶│   Summarizer     │───▶│ Intent Classifier│
└─────────────────┘    │   Node           │    └─────────────────┘
                       └──────────────────┘             │
                                                        ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Archiver      │◀───│  Execution       │◀───│    Routing      │
│   Node          │    │  Decider         │    │    Logic        │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │
         ▼
┌─────────────────┐
│      END        │
└─────────────────┘
```

## 1. LangGraph Checkpointing

### Overview
The agent now uses LangGraph's built-in checkpointing system with PostgreSQL as the backend storage. This provides automatic state persistence across conversation sessions.

### Key Features
- **Thread-based Persistence**: Each contact conversation gets a unique thread ID (`athena_{user_id}_{contact_id}`)
- **Automatic State Management**: LangGraph handles loading/saving conversation state automatically
- **Supabase Integration**: Uses Supabase PostgreSQL as the checkpoint store
- **Fallback Support**: Falls back to in-memory storage if PostgreSQL is unavailable

### Implementation Details

#### Checkpoint Saver Creation
```python
async def create_checkpoint_saver():
    """Create a PostgreSQL checkpoint saver for state persistence using Supabase."""
    # Constructs connection string from Supabase environment variables
    # Creates AsyncPostgresSaver with proper configuration
    # Falls back to MemorySaver if PostgreSQL unavailable
```

#### Thread ID Format
```
athena_{user_id}_{contact_id}
```
This ensures each user-contact conversation pair has isolated state.

#### Database Schema
The `langgraph_checkpoints` table stores:
- `thread_id`: Unique conversation identifier
- `checkpoint`: Complete conversation state (JSONB)
- `metadata`: Additional checkpoint metadata
- Timestamps and indexing for performance

## 2. Conversation Summarization and Trimming

### Overview
To manage costs and context window limits, the agent implements intelligent conversation summarization that preserves important context while reducing token usage.

### Configuration
```python
SUMMARY_THRESHOLD = 10  # Summarize when history exceeds 10 messages
MESSAGES_TO_RETAIN = 6  # Always keep the last 6 messages as-is
```

### Summarization Process

#### Trigger Conditions
- Summarization activates when message count > `SUMMARY_THRESHOLD`
- Recent messages (last `MESSAGES_TO_RETAIN`) are always preserved
- Older messages are summarized and removed from active context

#### Summarization Node (`_summarizer_node`)
1. **Message Segmentation**: Splits messages into "to-summarize" and "to-retain"
2. **Context Building**: Combines previous summary with new messages to summarize
3. **LLM Summarization**: Uses the main LLM to create consolidated summary
4. **State Update**: Updates conversation state with new summary and trimmed messages

#### Summary Content
The summarization preserves:
- Names and contact details
- Meeting requests and scheduling details
- Calendar events and availability discussions
- Important dates, times, and deadlines
- Decisions made and actions taken
- User preferences and requirements

### Integration with Intent Classification
The intent classifier receives both the conversation summary and recent messages, allowing it to:
- Understand long-term conversation context
- Make informed decisions based on recent interactions
- Maintain continuity across summarized conversations

## 3. Periodic Archiving to Messages Table

### Overview
While checkpoints store the "hot" conversational state, the messages table serves as "cold" storage for UI display and long-term archival.

### Archiving Process

#### Archiver Node (`_archiver_node`)
- Executes after every conversation turn
- Archives complete conversation to the `messages` table
- Provides data for frontend chat UI
- Enables conversation history search and analytics

#### Archiving Strategy
1. **Clear and Insert**: Removes existing messages for the contact, then inserts complete conversation
2. **Message Transformation**: Converts LangChain messages to database format
3. **Metadata Enrichment**: Adds indexing, timestamps, and conversation metadata

### Benefits
- **UI Optimization**: Messages table is perfectly structured for chat interfaces
- **Decoupled Architecture**: Frontend reads from messages table, agent uses checkpoints
- **Performance**: Enables pagination, search, and efficient queries
- **Data Integrity**: Complete conversation history always available

## 4. Enhanced State Schema

### SimpleState Updates
```python
class SimpleState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    conversation_summary: Optional[str]  # NEW: For summarization
    user_id: str
    contact_id: str
    message_intent: Optional[str]
    metadata: Optional[Dict[str, Any]]
```

### State Flow
1. **Load**: Previous state loaded from checkpoint
2. **Summarize**: Messages summarized if threshold exceeded
3. **Process**: Intent classification and execution with full context
4. **Archive**: Complete conversation archived to messages table
5. **Save**: Updated state automatically saved to checkpoint

## 5. API Enhancements

### Process Message
```python
async def process_message(self, contact_id: str, message: str, user_id: str, ...):
    # Creates thread_id for checkpointing
    # Loads previous state automatically
    # Processes message through enhanced graph
    # Returns response with checkpoint metadata
```

### Memory Management
```python
async def clear_conversation_history(self, user_id: str, contact_id: str):
    # Clears checkpoint state for specific contact
    
async def get_conversation_summary(self, user_id: str, contact_id: str):
    # Retrieves current conversation summary and metadata
```

## 6. Environment Configuration

### Required Environment Variables
```bash
# Supabase Configuration
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key

# OpenAI Configuration
OPENAI_API_KEY=your-openai-api-key
```

### Database Setup
1. Run the checkpoint table creation script:
   ```sql
   -- Execute sql/create_langgraph_checkpoints.sql in your Supabase database
   ```

2. Ensure the existing `messages` table is available for archiving

## 7. Performance Considerations

### Cost Optimization
- **Summarization**: Reduces token usage for long conversations
- **Selective Context**: Only recent messages sent to LLM for processing
- **Efficient Storage**: Checkpoints store compressed conversation state

### Scalability
- **Thread Isolation**: Each conversation is independently managed
- **Async Operations**: All database operations are asynchronous
- **Indexed Queries**: Proper database indexing for fast retrieval

### Error Handling
- **Graceful Degradation**: Falls back to memory storage if PostgreSQL unavailable
- **Summarization Fallback**: Continues with message trimming if summarization fails
- **Archive Resilience**: Agent continues working even if archiving fails

## 8. Migration from Previous Implementation

### Backward Compatibility
- Maintains same API interface as previous `agent_main.py`
- Returns additional metadata about checkpointing and summarization
- Existing integrations continue to work without changes

### Migration Steps
1. Install new dependencies: `langgraph-checkpoint-postgres`, `psycopg[binary]`
2. Create checkpoint table using provided SQL script
3. Set up Supabase environment variables
4. Deploy enhanced agent implementation
5. Monitor logs for successful checkpoint creation

## 9. Monitoring and Debugging

### Logging
The enhanced agent provides detailed logging for:
- Checkpoint creation and loading
- Summarization triggers and results
- Archiving operations
- Error conditions and fallbacks

### Metrics
Available in response metadata:
- `checkpointing_enabled`: Whether checkpointing is active
- `has_summary`: Whether conversation has been summarized
- `summary_length`: Length of current summary
- `message_count`: Number of messages in current state
- `thread_id`: Unique conversation identifier

### Troubleshooting
Common issues and solutions:
- **PostgreSQL Connection**: Check Supabase credentials and network connectivity
- **Summarization Errors**: Monitor LLM API limits and token usage
- **Archive Failures**: Verify Supabase permissions and table schema

## 10. Future Enhancements

### Potential Improvements
- **Semantic Search**: Enable search across conversation summaries
- **Analytics Dashboard**: Conversation metrics and usage patterns
- **Multi-tenant Isolation**: Enhanced security for enterprise deployments
- **Custom Summarization**: User-configurable summarization strategies
- **Export Functionality**: Conversation export for data portability

This enhanced implementation provides a robust, scalable, and cost-effective solution for managing conversational AI state while maintaining excellent user experience and system performance. 