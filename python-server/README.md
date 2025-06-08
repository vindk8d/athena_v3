# Athena Executive Assistant Server v2.0

This is the Python FastAPI server that powers Athena, an AI executive assistant that acts on behalf of a single authenticated user to coordinate meetings and manage schedules with their colleagues using LangChain with LCEL (LangChain Expression Language), agent executors, and Google Calendar integration.

## 🆕 Version 2.0 Features

- **Executive Assistant Persona**: AI that acts as the professional representative of one authenticated user
- **Single-User Focus**: Optimized to serve one executive with their colleague network
- **User-Colleague Coordination**: Coordinates with colleagues on behalf of the single authenticated user
- **LCEL Agent Architecture**: Modern LangChain agent using OpenAI Functions optimized for executive assistant tasks
- **User-Centric Calendar Management**: All calendar operations focused on the authenticated user's schedule
- **Professional Communication**: Always introduces itself as "[User's Name]'s executive assistant"
- **Enhanced Memory Management**: Database-integrated conversation memory per user-colleague pair
- **Google Calendar Tools**: Full calendar management for user calendars only
- **Intelligent Tool Selection**: Agent automatically chooses appropriate tools for executive assistant operations

## 📁 Project Structure

```
python-server/
├── main.py              # FastAPI application and executive assistant endpoints
├── agent.py             # Executive Assistant LCEL Agent with user-centric tool execution
├── memory.py            # Enhanced memory management with user-colleague pair isolation
├── tools.py             # Google Calendar API tools for user calendar management
├── config.py            # Configuration management
├── requirements.txt     # Python dependencies
├── Dockerfile          # Container configuration
├── render.yaml         # Render deployment config
└── README.md           # This file
```

## 🏗️ Architecture

### Executive Assistant System (agent.py)
- **ExecutiveAssistantAgent**: LCEL-based agent that acts on behalf of authenticated users
- **User-Centric Operations**: All calendar operations focused on the authenticated user
- **Professional Persona**: Maintains executive assistant identity in all interactions
- **Colleague Coordination**: Coordinates with colleagues who want to meet with the user
- **OpenAI Functions Agent**: Uses function calling for intelligent tool selection
- **Agent Executor**: Manages tool invocation and response generation with executive assistant context

### Memory System (memory.py)
- **User-Colleague Memory Isolation**: Separate conversation histories per user-colleague pair
- **DatabaseMemory**: Retrieves conversation history from Supabase with user context
- **EnhancedConversationMemory**: Combines buffer and database memory for executive assistant conversations
- **MemoryManager**: Manages memories across multiple users and their colleagues
- **Token Management**: Automatic memory pruning for optimal performance

### User Calendar Tools (tools.py)
- **ListCalendarsTool**: Discover authenticated user's available calendars
- **GetEventsTool**: Retrieve user's calendar events
- **CheckAvailabilityTool**: Check user's free/busy times
- **CreateEventTool**: Schedule new meetings on user's calendar with colleagues as attendees
- **CalendarService**: Google Calendar API wrapper with OAuth support for user calendars

## 🚀 Setup & Installation

### Prerequisites
- Python 3.11+
- OpenAI API Key
- Google Calendar API credentials (for user calendar access)
- Supabase database (for user authentication and memory persistence)

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
   
   # Required - for user authentication and database
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

### Core Executive Assistant Processing
- **POST** `/process-message` - Process colleague messages with full executive assistant capabilities
- **POST** `/simple-process` - Basic processing without calendar tools (legacy)

### Executive Assistant Management
- **GET** `/agent-info` - Get executive assistant configuration details
- **POST** `/reset-agent` - Reset the global executive assistant instance
- **POST** `/reset-conversation/{user_id}/{contact_id}` - Clear conversation memory for user-colleague pair

### Health & Status
- **GET** `/health` - Server health and status
- **GET** `/` - Server information and features

## 🔧 Executive Assistant Request/Response

### Enhanced Request Format
```json
{
  "telegram_message": {
    "message_id": 123,
    "chat_id": 456789,
    "user_id": 987654,
    "text": "I'd like to schedule a meeting with Sarah next week",
    "timestamp": "2024-01-01T12:00:00Z",
    "user_info": {
      "first_name": "John",
      "last_name": "Doe"
    }
  },
  "contact_id": "colleague-uuid-string",
  "user_id": "authenticated-user-uuid",
  "user_details": {
    "first_name": "Sarah",
    "last_name": "Johnson",
    "title": "CEO",
    "timezone": "America/New_York"
  },
  "conversation_history": [],
  "oauth_access_token": "user_google_oauth_token_for_calendar_access",
  "oauth_refresh_token": "optional_refresh_token"
}
```

### Enhanced Response Format
```json
{
  "response": "Hello! I'm Sarah Johnson's executive assistant. I'd be happy to help you schedule a meeting with Sarah. Let me check her availability for next week...",
  "conversation_id": "user-uuid_colleague-uuid",
  "user_id": "authenticated-user-uuid",
  "contact_id": "colleague-uuid",
  "intent": "colleague_meeting_request",
  "extracted_info": {
    "temporal_reference": "next_week",
    "user_availability_checked": true,
    "meeting_created_for_user": true,
    "executive_assistant_interaction": true,
    "event_details": {
      "title": "Meeting with John Doe",
      "start_time": "2024-01-09T14:00:00Z",
      "end_time": "2024-01-09T15:00:00Z",
      "created_for_user": "authenticated-user-uuid"
    }
  },
  "tools_used": [
    {
      "tool": "check_availability",
      "input": {"start_datetime": "2024-01-09T14:00:00Z", ...},
      "output": "✅ Sarah is FREE for this time slot"
    },
    {
      "tool": "create_event",
      "input": {"title": "Meeting with John Doe", ...},
      "output": "✅ Meeting scheduled on Sarah's calendar!"
    }
  ]
}
```

## 🛠️ Key Executive Assistant Features

### Executive Assistant Capabilities
- **User Representation**: Always acts as the executive assistant of the authenticated user
- **Professional Identity**: Introduces self as "[User's Name]'s executive assistant"
- **Authority to Schedule**: Full authority to manage user's calendar and schedule meetings
- **Colleague Coordination**: Coordinates with colleagues who want to meet with the user
- **No Colleague Authentication**: Never asks colleagues to authenticate their calendars

### Single-User Architecture
- **Focused Design**: Optimized for single-user performance and reliability
- **Colleague Management**: All contacts are colleagues of the one authenticated user
- **Calendar Privacy**: Only accesses the single authenticated user's calendar
- **Professional Boundaries**: Clear separation between user and colleague permissions

### Memory Features
- **Contact-Based Isolation**: Separate conversation histories per colleague
- **Database Integration**: Loads conversation history with single-user context
- **Cross-session Persistence**: Conversations survive server restarts
- **Token Optimization**: Automatic memory pruning per contact

### User Calendar Integration
- **OAuth Support**: Secure Google Calendar access for authenticated users only
- **User Calendar Focus**: All operations on the authenticated user's calendars
- **Availability Checking**: Free/busy time analysis for the user
- **Meeting Management**: Create meetings on user's calendar with colleagues as attendees

### Intent Detection (Executive Assistant Context)
- `colleague_meeting_request` - Colleague requests meeting with user
- `colleague_availability_inquiry` - Colleague asks about user's availability
- `meeting_scheduled_for_user` - Meeting created on user's calendar
- `checking_user_availability` - Checking user's calendar availability
- `viewing_user_calendar` - Viewing user's calendar events
- `colleague_meeting_modification` - Colleague requests changes to user's meetings
- `colleague_general_conversation` - General conversation with colleague

## 🚀 Deployment

### Local Development
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Docker
```bash
docker build -t athena-executive-assistant .
docker run -p 8000:8000 --env-file .env athena-executive-assistant
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
- Passes user ID and details for executive assistant context
- Passes user's OAuth tokens for calendar access
- Routes colleague messages to the executive assistant
- Handles executive assistant responses with proper user context
- Logs tool execution results for user calendar operations

## 🧠 Advanced Usage

### Executive Assistant Customization
```python
from agent import ExecutiveAssistantAgent

# Process colleague message for specific user
result = await agent.process_message(
    contact_id="colleague-uuid",
    message="Can I meet with Sarah tomorrow?",
    user_id="user-uuid",
    user_details={"first_name": "Sarah", "last_name": "Johnson"},
    access_token="user-oauth-token"
)
```

### User-Colleague Memory Management
```python
from memory import MemoryManager

# Get memory for specific user-colleague pair
memory_key = f"{user_id}_{contact_id}"
memory = memory_manager.get_memory(memory_key)

# Add executive assistant message
await memory.add_message(AIMessage(content="I'm Sarah's assistant..."))

# Clear memory for user-colleague pair
memory_manager.clear_memory(memory_key)
```

### User-Centric Tool Development
```python
from langchain.tools import BaseTool
from tools import CalendarToolsInput

class UserSpecificTool(BaseTool):
    name = "user_specific_tool"
    description = "Tool that operates on the authenticated user's data"
    args_schema = CalendarToolsInput
    
    def _run(self, **kwargs) -> str:
        # Tool implementation focused on user data
        return "User-specific result"
```

## 📊 Monitoring & Debugging

### Executive Assistant Logging
The server provides comprehensive logging for executive assistant operations:
- User-colleague interaction tracking
- Executive assistant decision-making process
- User calendar tool execution results
- Memory management per user-colleague pair
- Error handling with user context

### Health Checks
- `/health` endpoint for uptime monitoring
- Executive assistant status verification
- Database connectivity checks with user context

### Development Tools
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- Executive assistant info: `GET /agent-info`

## 🔧 Troubleshooting

### Common Issues

**Executive Assistant Not Identifying Properly:**
- Verify user_details are being passed correctly
- Check user authentication context
- Ensure proper user-colleague relationship setup

**User Calendar Tools Not Working:**
- Verify user's OAuth token is being passed
- Check Google Calendar API permissions for the user
- Ensure calendar access is granted for the authenticated user

**Memory Issues:**
- Verify Supabase credentials with user context
- Check user-colleague pair isolation
- Monitor memory usage patterns per user

**User Context Problems:**
- Ensure user_id is properly passed in requests
- Verify user_details are available
- Check user-colleague relationship mapping

## 📈 Performance Optimization

- **User-Based Token Management**: Automatic memory pruning per user-colleague pair
- **User Calendar Caching**: Efficient caching of user calendar data
- **Executive Assistant Context**: Fast context switching between user-colleague pairs
- **Async Processing**: Non-blocking operations with user context

## 🔄 Version History

**v2.0** - Executive Assistant with Multi-User Support
- Executive assistant persona and identity
- Multi-user support with proper isolation
- User-colleague coordination capabilities
- User-centric calendar operations
- Professional executive assistant communication
- Enhanced memory system with user-colleague pair isolation

**v1.0** - Basic LangChain Integration
- Simple conversation chains
- Basic intent detection
- In-memory conversations 