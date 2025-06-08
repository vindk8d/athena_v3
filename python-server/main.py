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
app = FastAPI(title="Athena Executive Assistant Server", version="2.0.0")

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
    user_id: str  # The authenticated user's ID (from auth.users.id)
    user_details: Optional[Dict[str, Any]] = None  # User details from user_details table
    conversation_history: Optional[List] = []
    # OAuth token for the user's calendar access (optional)
    oauth_access_token: Optional[str] = None
    oauth_refresh_token: Optional[str] = None

class ProcessMessageResponse(BaseModel):
    response: str
    conversation_id: str
    user_id: str
    contact_id: str
    intent: Optional[str] = None
    extracted_info: Optional[Dict[str, Any]] = None
    tools_used: Optional[List[Dict[str, Any]]] = []

@app.on_event("startup")
async def startup_event():
    logger.info("Starting Athena Executive Assistant Server v2.0...")
    logger.info(f"OpenAI API Key configured: {'Yes' if Config.OPENAI_API_KEY else 'No'}")
    logger.info(f"Model: {Config.LLM_MODEL}")
    logger.info(f"Temperature: {Config.LLM_TEMPERATURE}")
    logger.info("Agent Mode: Single-User Executive Assistant (serves one user and their colleagues)")
    
    # Initialize the executive assistant agent
    try:
        agent = get_agent()
        logger.info("Single-User Executive Assistant Agent initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize executive assistant agent: {e}")
        raise

@app.get("/")
async def root():
    return {
        "message": "Athena Executive Assistant Server v2.0 is running",
        "version": "2.0.0",
        "agent_type": "Single-User Executive Assistant",
        "description": "AI assistant that acts on behalf of one authenticated user to coordinate with their colleagues",
        "features": [
            "Executive Assistant Persona",
            "Single-User Focus",
            "Colleague Coordination", 
            "Professional Meeting Scheduling",
            "User Calendar Management",
            "Google Calendar API Integration",
            "Enhanced Memory Management per Contact",
            "Simplified Single-User Architecture"
        ]
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy", 
        "service": "executive-assistant-server",
        "version": "2.0.0",
        "agent_type": "executive_assistant",
        "agent_status": "initialized" if get_agent() else "not_initialized"
    }

@app.post("/process-message", response_model=ProcessMessageResponse)
async def process_message(request: ProcessMessageRequest):
    """
    Process a colleague's Telegram message using the executive assistant agent.
    """
    try:
        contact_id = request.contact_id
        user_id = request.user_id
        user_details = request.user_details
        telegram_msg = request.telegram_message
        colleague_message = telegram_msg.text
        
        logger.info(f"Processing message from colleague {contact_id} for user {user_id}: {colleague_message}")
        
        # Get the agent
        agent = get_agent()
        
        # Process the message with the executive assistant agent
        result = await agent.process_message(
            contact_id=contact_id,
            message=colleague_message,
            user_id=user_id,
            user_details=user_details,
            access_token=request.oauth_access_token
        )
        
        logger.info(f"Executive assistant response generated successfully")
        logger.info(f"Intent detected: {result.get('intent')}")
        logger.info(f"Tools used: {[tool['tool'] for tool in result.get('tools_used', [])]}")
        
        return ProcessMessageResponse(
            response=result["response"],
            conversation_id=result["conversation_id"],
            user_id=result["user_id"],
            contact_id=result["contact_id"],
            intent=result.get("intent"),
            extracted_info=result.get("extracted_info"),
            tools_used=result.get("tools_used", [])
        )
        
    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing message: {str(e)}")

@app.post("/reset-conversation/{contact_id}")
async def reset_conversation(contact_id: str):
    """Reset conversation memory for a specific contact (single-user system)."""
    try:
        memory_key = f"user_{contact_id}"
        memory_manager.clear_memory(memory_key)
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
    """Get information about the single-user executive assistant agent configuration."""
    try:
        agent = get_agent()
        return {
            "model": Config.LLM_MODEL,
            "temperature": Config.LLM_TEMPERATURE,
            "agent_type": "single_user_executive_assistant",
            "persona": "Professional executive assistant acting on behalf of one authenticated user",
            "system_type": "single_user",
            "tools_available": [
                "list_calendars",
                "get_events", 
                "check_availability",
                "create_event"
            ],
            "capabilities": [
                "Single user calendar management",
                "Colleague coordination",
                "Professional meeting scheduling",
                "Executive representation",
                "Simplified architecture"
            ],
            "memory_management": "per_contact_isolation",
            "multi_user_support": False,
            "description": "Serves one user and coordinates with their colleagues"
        }
    except Exception as e:
        logger.error(f"Error getting agent info: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting agent info: {str(e)}")

# Legacy endpoint for backwards compatibility
@app.post("/simple-process", response_model=ProcessMessageResponse)
async def simple_process_message(request: ProcessMessageRequest):
    """
    Legacy endpoint that processes colleague messages without calendar tools.
    Useful for testing or when calendar access is not available.
    """
    try:
        contact_id = request.contact_id
        user_id = request.user_id
        user_details = request.user_details
        telegram_msg = request.telegram_message
        colleague_message = telegram_msg.text
        
        logger.info(f"Processing simple message from colleague {contact_id} for user {user_id}: {colleague_message}")
        
        # Get memory for this contact (single-user system)
        memory_key = f"user_{contact_id}"
        memory = memory_manager.get_memory(memory_key)
        
        # Create user name for response
        user_name = "your user"
        if user_details:
            first_name = user_details.get('first_name', '')
            last_name = user_details.get('last_name', '')
            if first_name and last_name:
                user_name = f"{first_name} {last_name}"
            elif first_name:
                user_name = first_name
        
        # Simple executive assistant response without tools
        response = f"Hello! I'm {user_name}'s executive assistant. I received your message: '{colleague_message}'. I'm currently running in simple mode without calendar access."
        
        # Basic intent detection
        intent = "colleague_general_conversation"
        if any(word in colleague_message.lower() for word in ["schedule", "meeting", "appointment"]):
            intent = "colleague_meeting_request"
            response = f"I understand you want to schedule a meeting with {user_name}. I'll need calendar access to check {user_name}'s availability and coordinate the meeting."
        
        return ProcessMessageResponse(
            response=response,
            conversation_id=memory_key,
            user_id=user_id,
            contact_id=contact_id,
            intent=intent,
            extracted_info={"simple_mode": True, "executive_assistant_mode": True},
            tools_used=[]
        )
        
    except Exception as e:
        logger.error(f"Error in simple processing: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error in simple processing: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 