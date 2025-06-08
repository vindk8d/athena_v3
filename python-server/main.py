from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
from dotenv import load_dotenv
from typing import Optional, Dict, Any, List
import logging

from config import Config
from agent import get_agent, reset_agent
from memory import memory_manager

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(title="Athena Executive Assistant LangChain Server", version="2.0.0")

# Validate configuration on startup
try:
    Config.validate()
except Exception as e:
    logger.error(f"Configuration validation failed: {e}")
    raise

# Pydantic models for request/response
class TelegramMessage(BaseModel):
    message_id: int
    chat_id: int
    user_id: int
    text: str
    timestamp: str
    user_info: Optional[Dict[str, Any]] = None

class ProcessMessageRequest(BaseModel):
    telegram_message: TelegramMessage
    contact_id: str
    conversation_history: Optional[List] = []
    # OAuth token for calendar access (optional)
    oauth_access_token: Optional[str] = None
    oauth_refresh_token: Optional[str] = None

class ProcessMessageResponse(BaseModel):
    response: str
    conversation_id: str
    intent: Optional[str] = None
    extracted_info: Optional[Dict[str, Any]] = None
    tools_used: Optional[List[Dict[str, Any]]] = []

@app.on_event("startup")
async def startup_event():
    logger.info("Starting Athena LangChain Server v2.0...")
    logger.info(f"OpenAI API Key configured: {'Yes' if Config.OPENAI_API_KEY else 'No'}")
    logger.info(f"Model: {Config.LLM_MODEL}")
    logger.info(f"Temperature: {Config.LLM_TEMPERATURE}")
    
    # Initialize the agent
    try:
        agent = get_agent()
        logger.info("Executive Assistant Agent initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize agent: {e}")
        raise

@app.get("/")
async def root():
    return {
        "message": "Athena Executive Assistant LangChain Server v2.0 is running",
        "version": "2.0.0",
        "features": [
            "LCEL Agent with Calendar Tools",
            "Enhanced Memory Management", 
            "Database Integration",
            "Google Calendar API",
            "Intent Detection & Information Extraction"
        ]
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy", 
        "service": "langchain-server",
        "version": "2.0.0",
        "agent_status": "initialized" if get_agent() else "not_initialized"
    }

@app.post("/process-message", response_model=ProcessMessageResponse)
async def process_message(request: ProcessMessageRequest):
    """
    Process a Telegram message using the executive assistant agent.
    """
    try:
        contact_id = request.contact_id
        telegram_msg = request.telegram_message
        user_message = telegram_msg.text
        
        logger.info(f"Processing message from contact {contact_id}: {user_message}")
        
        # Get the agent
        agent = get_agent()
        
        # Process the message with the agent
        result = await agent.process_message(
            contact_id=contact_id,
            message=user_message,
            access_token=request.oauth_access_token
        )
        
        logger.info(f"Agent response generated successfully")
        logger.info(f"Intent detected: {result.get('intent')}")
        logger.info(f"Tools used: {[tool['tool'] for tool in result.get('tools_used', [])]}")
        
        return ProcessMessageResponse(
            response=result["response"],
            conversation_id=result["conversation_id"],
            intent=result.get("intent"),
            extracted_info=result.get("extracted_info"),
            tools_used=result.get("tools_used", [])
        )
        
    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing message: {str(e)}")

@app.post("/reset-conversation/{contact_id}")
async def reset_conversation(contact_id: str):
    """Reset conversation memory for a specific contact."""
    try:
        memory_manager.clear_memory(contact_id)
        logger.info(f"Conversation memory cleared for contact {contact_id}")
        return {"status": "success", "message": f"Conversation memory cleared for contact {contact_id}"}
    except Exception as e:
        logger.error(f"Error resetting conversation: {e}")
        raise HTTPException(status_code=500, detail=f"Error resetting conversation: {str(e)}")

@app.post("/reset-agent")
async def reset_agent_endpoint():
    """Reset the global agent instance."""
    try:
        reset_agent()
        logger.info("Agent instance reset")
        return {"status": "success", "message": "Agent instance reset successfully"}
    except Exception as e:
        logger.error(f"Error resetting agent: {e}")
        raise HTTPException(status_code=500, detail=f"Error resetting agent: {str(e)}")

@app.get("/agent-info")
async def agent_info():
    """Get information about the current agent configuration."""
    try:
        agent = get_agent()
        return {
            "model": Config.LLM_MODEL,
            "temperature": Config.LLM_TEMPERATURE,
            "tools_available": [
                "list_calendars",
                "get_events", 
                "check_availability",
                "create_event"
            ],
            "memory_management": "enhanced_with_database",
            "agent_type": "openai_functions_agent"
        }
    except Exception as e:
        logger.error(f"Error getting agent info: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting agent info: {str(e)}")

# Legacy endpoint for backwards compatibility
@app.post("/simple-process", response_model=ProcessMessageResponse)
async def simple_process_message(request: ProcessMessageRequest):
    """
    Legacy endpoint that processes messages without calendar tools.
    Useful for testing or when calendar access is not available.
    """
    try:
        contact_id = request.contact_id
        telegram_msg = request.telegram_message
        user_message = telegram_msg.text
        
        logger.info(f"Processing simple message from contact {contact_id}: {user_message}")
        
        # Get memory for this contact
        memory = memory_manager.get_memory(contact_id)
        
        # Simple response without tools
        response = f"I received your message: '{user_message}'. This is a simple response without calendar tools."
        
        # Basic intent detection
        intent = "general_conversation"
        if any(word in user_message.lower() for word in ["schedule", "meeting", "appointment"]):
            intent = "schedule_request"
            response = "I understand you want to schedule something. Please provide your calendar access to use full scheduling features."
        
        return ProcessMessageResponse(
            response=response,
            conversation_id=contact_id,
            intent=intent,
            extracted_info={"simple_mode": True},
            tools_used=[]
        )
        
    except Exception as e:
        logger.error(f"Error in simple processing: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error in simple processing: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 