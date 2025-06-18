# LangGraph Studio Setup

This directory contains the configuration for LangGraph Studio, which provides a visual interface for debugging and testing the Athena agent.

## Environment Setup

1. **Copy the example environment file:**
   ```bash
   cp langgraph_studio.env.example langgraph_studio.env
   ```

2. **Fill in your actual API keys and credentials:**
   Edit `langgraph_studio.env` and replace the placeholder values with your actual credentials:

   - `SUPABASE_URL`: Your Supabase project URL
   - `SUPABASE_ANON_KEY`: Your Supabase anonymous key
   - `SUPABASE_SERVICE_ROLE_KEY`: Your Supabase service role key
   - `TELEGRAM_BOT_TOKEN`: Your Telegram bot token from BotFather
   - `OPENAI_API_KEY`: Your OpenAI API key
   - `GOOGLE_CLIENT_ID`: Your Google OAuth client ID
   - `GOOGLE_CLIENT_SECRET`: Your Google OAuth client secret
   - `LANGCHAIN_API_KEY`: Your LangChain API key (optional, for tracing)

## Running LangGraph Studio

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Start the studio:**
   ```bash
   python setup_studio.py
   ```

3. **Access the studio:**
   Open your browser and go to the URL shown in the terminal (usually `http://localhost:8123`)

## Security Notes

- The `langgraph_studio.env` file is ignored by git to prevent accidentally committing secrets
- Always use the `.env.example` file as a template
- Never commit actual API keys or secrets to version control
- Consider using a secrets management service for production deployments

## Troubleshooting

If you encounter issues:

1. Make sure all required environment variables are set
2. Check that your API keys are valid and have the necessary permissions
3. Ensure your Google OAuth credentials are properly configured
4. Verify that your Supabase project is accessible

For more information, see the main project README.

## 📁 Files in this Directory

- `langgraph_studio.env` - Environment variables for Studio
- `langgraph.json` - Studio configuration file
- `studio_agent.py` - Entry point for Studio
- `setup_studio.py` - Setup validation script
- `README.md` - This guide

## Prerequisites

1. **LangSmith Account**: You need a LangSmith account to use LangGraph Studio
   - Sign up at: https://smith.langchain.com
   - Get your API key from the settings page

2. **Environment Variables**: Copy from your `/app/.env.local` file

## Setup Steps

### 1. Update Environment Variables

Edit `langgraph_studio.env` and replace the placeholder values with your actual API keys:

```bash
# Required for LangGraph Studio
OPENAI_API_KEY=sk-your-actual-openai-key
LANGCHAIN_API_KEY=ls__your-actual-langsmith-key

# Optional (for calendar integration testing)
NEXT_PUBLIC_SUPABASE_URL=your-supabase-url
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-supabase-key
```

### 2. Install Dependencies

Make sure you have all required packages:

```bash
cd python-server
pip install -r requirements.txt
pip install langchain-cli
```

### 3. Run Setup Script

Run the setup validation script:

```bash
cd python-server/studio
python setup_studio.py
```

This will check:
- Environment variables are set correctly
- All dependencies are installed
- LangChain CLI is available

### 4. Start LangGraph Studio

```bash
cd python-server/studio
langchain serve --port=8123
```

### 5. Open LangGraph Studio

Navigate to: http://localhost:8123

Your agent will be available as `athena_agent` in the Studio interface.

## How to Use LangGraph Studio

### 1. **Graph Visualization**
- View your agent's graph structure with all nodes and edges
- See the flow: `input_interpreter` → `planner` → `time_normalizer` → `clarification` → `execution` → `response_generator`

### 2. **Interactive Debugging**
- Test different input messages
- Step through the execution node by node
- Inspect state at each step
- View tool calls and their results

### 3. **Example Test Cases**

Try these test messages to debug different flows:

```json
{
  "messages": [{"role": "human", "content": "Can we schedule a meeting tomorrow at 2pm?"}],
  "user_id": "test_user",
  "contact_id": "test_contact",
  "user_timezone": "America/New_York",
  "current_datetime": "2024-01-15T10:00:00-05:00"
}
```

```json
{
  "messages": [{"role": "human", "content": "What's my availability this week?"}],
  "user_id": "test_user", 
  "contact_id": "test_contact",
  "user_timezone": "America/New_York",
  "current_datetime": "2024-01-15T10:00:00-05:00"
}
```

### 4. **State Inspection**

At each step, you can inspect:
- **Intent Classification**: What intent was detected and confidence level
- **Planning**: What steps were planned for execution
- **Time Normalization**: How temporal references were parsed
- **Tool Selection**: Which calendar tools were chosen
- **Execution Results**: Tool outputs and any errors

### 5. **Debugging Tips**

- **Intent Issues**: Check the `input_interpreter` node output
- **Time Parsing**: Look at the `time_normalizer` node state
- **Tool Failures**: Inspect `execution` node for error details
- **Response Quality**: Review `response_generator` node output

## Troubleshooting

### Common Issues

1. **"Graph not found" error**
   - Ensure `langgraph.json` is correctly configured
   - Check that `studio_agent.py` exports the graph properly

2. **Environment variable errors**
   - Verify your API keys are correct
   - Make sure `langgraph_studio.env` is properly formatted

3. **Import errors**
   - Run `pip install -r ../requirements.txt` again
   - Check that all dependencies are compatible

4. **Calendar tool errors** 
   - Calendar tools require OAuth tokens which won't be available in Studio
   - These will show as expected errors during debugging

### Advanced Debugging

1. **Add Breakpoints**: Modify nodes to add logging or breakpoints
2. **Custom State**: Add debug fields to `AthenaState` for inspection
3. **Tool Mocking**: Create mock versions of calendar tools for testing

## File Structure

```
python-server/
├── agent.py              # Main agent implementation
├── tools.py              # Calendar and other tools
├── memory.py             # Memory management
├── config.py             # Configuration
├── requirements.txt      # Dependencies
└── studio/              # LangGraph Studio files
    ├── langgraph_studio.env
    ├── langgraph.json
    ├── studio_agent.py
    ├── setup_studio.py
    └── README.md
```

## Next Steps

Once you have Studio running:

1. Test your agent with various input types
2. Debug any issues in the graph execution
3. Optimize node performance and logic
4. Test edge cases and error handling

Happy debugging! 🚀 