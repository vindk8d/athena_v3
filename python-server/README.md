# Athena Executive Assistant LangChain Server v2.0

This is the Python FastAPI server that handles advanced natural language processing for the Athena Executive Assistant chatbot using LangChain with LCEL (LangChain Expression Language), agent executors, and Google Calendar integration.

## 🆕 Version 2.0 Features

- **LCEL Agent Architecture**: Modern LangChain agent using OpenAI Functions
- **Enhanced Memory Management**: Database-integrated conversation memory
- **Google Calendar Tools**: Full calendar management capabilities
- **Intelligent Tool Selection**: Agent automatically chooses appropriate tools
- **Advanced Intent Detection**: Context-aware intent analysis
- **Structured Information Extraction**: Rich metadata extraction from conversations

## 📁 Project Structure

```
python-server/
├── main.py              # FastAPI application and endpoints
├── agent.py             # LCEL Agent with tool execution
├── memory.py            # Enhanced memory management with database
├── tools.py             # Google Calendar API tools
├── config.py            # Configuration management
├── requirements.txt     # Python dependencies
├── Dockerfile          # Container configuration
├── render.yaml         # Render deployment config
└── README.md           # This file
```

## 🏗️ Architecture

### Agent System (agent.py)
- **ExecutiveAssistantAgent**: LCEL-based agent with tool execution
- **OpenAI Functions Agent**: Uses function calling for tool selection
- **Agent Executor**: Manages tool invocation and response generation
- **Error Handling**: Graceful fallbacks and error recovery

### Memory System (memory.py)
- **DatabaseMemory**: Retrieves conversation history from Supabase
- **EnhancedConversationMemory**: Combines buffer and database memory
- **MemoryManager**: Manages memories across multiple contacts
- **Token Management**: Automatic memory pruning for optimal performance

### Calendar Tools (tools.py)
- **ListCalendarsTool**: Discover available calendars
- **GetEventsTool**: Retrieve calendar events
- **CheckAvailabilityTool**: Check free/busy times
- **CreateEventTool**: Schedule new meetings
- **CalendarService**: Google Calendar API wrapper with OAuth support

## 🚀 Setup & Installation

### Prerequisites
- Python 3.11+
- OpenAI API Key
- Google Calendar API credentials (for calendar features)
- Supabase database (for memory persistence)

### Installation

1. **Clone and navigate:**
   ```bash
   cd python-server
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Environment configuration:**
   Create a `.env` file:
   ```env
   # Required
   OPENAI_API_KEY=your_openai_api_key_here
   
   # Optional - for database memory
   NEXT_PUBLIC_SUPABASE_URL=your_supabase_url
   NEXT_PUBLIC_SUPABASE_ANON_KEY=your_supabase_anon_key
   
   # Optional - customize model settings
   LLM_MODEL=gpt-3.5-turbo
   LLM_TEMPERATURE=0.7
   PORT=8000
   ```

4. **Run the server:**
   ```bash
   python main.py
   ```
   
   Or with uvicorn:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```

## 📡 API Endpoints

### Core Processing
- **POST** `/process-message` - Process messages with full agent capabilities
- **POST** `/simple-process` - Basic processing without calendar tools (legacy)

### Agent Management
- **GET** `/agent-info` - Get agent configuration details
- **POST** `/reset-agent` - Reset the global agent instance
- **POST** `/reset-conversation/{contact_id}` - Clear conversation memory

### Health & Status
- **GET** `/health` - Server health and status
- **GET** `/` - Server information and features

## 🔧 Agent Request/Response

### Enhanced Request Format
```json
{
  "telegram_message": {
    "message_id": 123,
    "chat_id": 456789,
    "user_id": 987654,
    "text": "Schedule a meeting with john@example.com for tomorrow at 2pm",
    "timestamp": "2024-01-01T12:00:00Z",
    "user_info": {
      "first_name": "John",
      "last_name": "Doe"
    }
  },
  "contact_id": "uuid-string",
  "conversation_history": [],
  "oauth_access_token": "google_oauth_token_for_calendar_access",
  "oauth_refresh_token": "optional_refresh_token"
}
```

### Enhanced Response Format
```json
{
  "response": "I'll help you schedule that meeting. Let me check your availability for tomorrow at 2pm...",
  "conversation_id": "uuid-string",
  "intent": "schedule_meeting",
  "extracted_info": {
    "temporal_reference": "tomorrow",
    "participants_mentioned": true,
    "availability_checked": true,
    "event_created": true,
    "event_details": {
      "title": "Meeting with John",
      "start_time": "2024-01-02T14:00:00Z",
      "end_time": "2024-01-02T15:00:00Z"
    }
  },
  "tools_used": [
    {
      "tool": "check_availability",
      "input": {"start_datetime": "2024-01-02T14:00:00Z", ...},
      "output": "✅ Time slot is FREE"
    },
    {
      "tool": "create_event",
      "input": {"title": "Meeting with John", ...},
      "output": "✅ Event created successfully!"
    }
  ]
}
```

## 🛠️ Key Features

### Agent Capabilities
- **Multi-turn Conversations**: Maintains context across interactions
- **Tool Selection**: Automatically chooses appropriate calendar tools
- **Error Recovery**: Graceful handling of tool failures
- **Professional Communication**: Executive assistant personality

### Memory Features
- **Database Integration**: Loads last 5 messages from Supabase
- **Buffer Management**: Efficient in-memory conversation tracking
- **Token Optimization**: Automatic memory pruning
- **Cross-session Persistence**: Conversations survive server restarts

### Calendar Integration
- **OAuth Support**: Secure Google Calendar access
- **Multi-calendar Support**: Access multiple user calendars
- **Availability Checking**: Free/busy time analysis
- **Event Management**: Create, read, and manage calendar events

### Intent Detection
- `schedule_meeting` - Meeting scheduling requests
- `check_availability` - Availability inquiries  
- `view_calendar` - Calendar viewing requests
- `explore_calendars` - Calendar discovery
- `modify_meeting` - Meeting changes/cancellations
- `general_conversation` - General chat

## 🚀 Deployment

### Local Development
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Docker
```bash
docker build -t athena-langchain-v2 .
docker run -p 8000:8000 --env-file .env athena-langchain-v2
```

### Render Deployment
1. Connect your repository to Render
2. Set environment variables in Render dashboard:
   - `OPENAI_API_KEY`
   - `NEXT_PUBLIC_SUPABASE_URL`
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY`
3. Deploy using the included `render.yaml`

## 🔗 Integration

### Next.js Integration
Update your main app's `.env.local`:
```env
PYTHON_SERVER_URL=https://your-render-app.onrender.com
```

The Telegram webhook handler automatically:
- Passes OAuth tokens for calendar access
- Handles agent responses with tool usage
- Logs tool execution results
- Provides fallback responses

## 🧠 Advanced Usage

### Custom Tool Development
```python
from langchain.tools import BaseTool
from tools import CalendarToolsInput

class CustomTool(BaseTool):
    name = "custom_tool"
    description = "Description of what this tool does"
    args_schema = CalendarToolsInput
    
    def _run(self, **kwargs) -> str:
        # Tool implementation
        return "Tool result"

# Add to calendar_tools list
```

### Memory Customization
```python
from memory import MemoryManager

# Get memory for specific contact
memory = memory_manager.get_memory("contact_id")

# Add custom message
await memory.add_message(SystemMessage(content="Custom instruction"))

# Clear memory
memory_manager.clear_memory("contact_id")
```

### Agent Configuration
```python
from agent import create_agent

# Create custom agent
agent = create_agent(
    model_name="gpt-4",
    temperature=0.3
)
```

## 📊 Monitoring & Debugging

### Logging
The server provides comprehensive logging:
- Agent decision-making process
- Tool execution results
- Memory management operations
- Error handling and recovery

### Health Checks
- `/health` endpoint for uptime monitoring
- Agent status verification
- Database connectivity checks

### Development Tools
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- Agent info: `GET /agent-info`

## 🔧 Troubleshooting

### Common Issues

**Calendar Tools Not Working:**
- Verify OAuth token is being passed
- Check Google Calendar API permissions
- Ensure calendar access is granted

**Memory Issues:**
- Verify Supabase credentials
- Check database connectivity
- Monitor memory usage patterns

**Agent Timeouts:**
- Adjust `max_execution_time` in agent executor
- Optimize tool response times
- Consider upgrading to GPT-4 for complex tasks

## 📈 Performance Optimization

- **Token Management**: Automatic memory pruning
- **Tool Caching**: Efficient calendar data caching
- **Error Handling**: Fast fallback responses
- **Async Processing**: Non-blocking operations

## 🔄 Version History

**v2.0** - LCEL Agent with Calendar Tools
- LCEL agent architecture
- Google Calendar integration
- Enhanced memory system
- Advanced tool execution

**v1.0** - Basic LangChain Integration
- Simple conversation chains
- Basic intent detection
- In-memory conversations 