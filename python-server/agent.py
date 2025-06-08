from typing import Dict, Any, List, Optional
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.schema import SystemMessage, HumanMessage, AIMessage
from langchain.schema.runnable import RunnablePassthrough, RunnableLambda
from langchain.tools import Tool
import logging
from datetime import datetime, timedelta
import json

from memory import MemoryManager, memory_manager
from tools import calendar_tools, set_calendar_service
from config import Config

logger = logging.getLogger(__name__)

# Enhanced system prompt for the executive assistant
EXECUTIVE_ASSISTANT_PROMPT = """You are Athena, an advanced executive assistant AI with access to calendar management tools. Your primary role is to help users efficiently manage their schedules, coordinate meetings, and handle calendar-related tasks.

## Core Capabilities:
- **Calendar Management**: View, create, and manage calendar events
- **Availability Checking**: Check free/busy times across multiple calendars  
- **Meeting Coordination**: Schedule meetings with multiple participants
- **Intelligent Scheduling**: Suggest optimal meeting times based on availability
- **Proactive Assistance**: Anticipate needs and provide helpful suggestions

## Behavioral Guidelines:
1. **Be Professional**: Maintain a courteous, professional tone in all interactions
2. **Be Proactive**: Offer relevant suggestions and anticipate follow-up needs
3. **Gather Information**: When scheduling meetings, collect all necessary details:
   - Date and time preferences
   - Duration
   - Participants and their email addresses
   - Meeting purpose/agenda
   - Location (physical or virtual)
4. **Confirm Details**: Always confirm meeting details before creating events
5. **Handle Conflicts**: If conflicts arise, suggest alternative times
6. **Provide Context**: Give clear explanations for your actions and recommendations

## Tool Usage:
- Use `list_calendars` first to see available calendars
- Use `check_availability` before scheduling any meetings
- Use `get_events` to view existing calendar entries
- Use `create_event` only after confirming all details and availability

## Response Style:
- Be concise but thorough
- Use bullet points for clarity when listing options or details
- Include relevant emoji sparingly for visual clarity (✅, ❌, 📅, ⏰)
- Always end with a helpful next step or question when appropriate

Remember: You have access to real calendar data and can perform actual calendar operations. Always double-check availability before committing to scheduling anything."""

class ExecutiveAssistantAgent:
    """Advanced executive assistant agent using LCEL and tool execution."""
    
    def __init__(self, openai_api_key: str, model_name: str = "gpt-3.5-turbo", temperature: float = 0.7):
        """Initialize the executive assistant agent."""
        self.llm = ChatOpenAI(
            temperature=temperature,
            model_name=model_name,
            openai_api_key=openai_api_key
        )
        
        # Create the prompt template with memory placeholder
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", EXECUTIVE_ASSISTANT_PROMPT),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad")
        ])
        
        # Initialize agent and executor
        self.agent = create_openai_functions_agent(
            llm=self.llm,
            tools=calendar_tools,
            prompt=self.prompt
        )
        
        self.agent_executor = AgentExecutor(
            agent=self.agent,
            tools=calendar_tools,
            verbose=True,
            return_intermediate_steps=True,
            max_iterations=10,
            max_execution_time=30,
            handle_parsing_errors=True
        )
        
        logger.info("Executive Assistant Agent initialized successfully")
    
    async def process_message(self, contact_id: str, message: str, access_token: str = None) -> Dict[str, Any]:
        """
        Process a user message and return an intelligent response.
        
        Args:
            contact_id: Unique identifier for the contact
            message: User's message
            access_token: OAuth access token for calendar access
            
        Returns:
            Dict containing response and metadata
        """
        try:
            # Set up calendar service if access token provided
            if access_token:
                set_calendar_service(access_token)
                logger.info("Calendar service initialized for agent")
            
            # Get memory for this contact
            memory = memory_manager.get_memory(contact_id)
            
            # Load conversation history
            chat_history = await memory.get_messages()
            
            # Add current user message to memory
            await memory.add_message(HumanMessage(content=message))
            
            # Prepare inputs for the agent
            inputs = {
                "input": message,
                "chat_history": chat_history
            }
            
            # Execute the agent
            result = await self.agent_executor.ainvoke(inputs)
            
            response = result["output"]
            intermediate_steps = result.get("intermediate_steps", [])
            
            # Add AI response to memory
            await memory.add_ai_message(contact_id, response)
            
            # Extract tool usage information
            tools_used = []
            for step in intermediate_steps:
                if len(step) >= 2:
                    action, observation = step[0], step[1]
                    tools_used.append({
                        "tool": action.tool,
                        "input": action.tool_input,
                        "output": str(observation)[:200] + "..." if len(str(observation)) > 200 else str(observation)
                    })
            
            # Analyze the response for intent and extracted information
            intent = self._analyze_intent(message, tools_used)
            extracted_info = self._extract_information(message, response, tools_used)
            
            return {
                "response": response,
                "intent": intent,
                "extracted_info": extracted_info,
                "tools_used": tools_used,
                "conversation_id": contact_id
            }
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            error_response = "I apologize, but I encountered an error while processing your request. Please try again or rephrase your question."
            
            # Still add messages to memory even if there was an error
            try:
                memory = memory_manager.get_memory(contact_id)
                await memory.add_ai_message(contact_id, error_response)
            except:
                pass
            
            return {
                "response": error_response,
                "intent": "error",
                "extracted_info": {"error": str(e)},
                "tools_used": [],
                "conversation_id": contact_id
            }
    
    def _analyze_intent(self, message: str, tools_used: List[Dict]) -> str:
        """Analyze the user's intent based on message and tools used."""
        message_lower = message.lower()
        
        # Check what tools were actually used
        tool_names = [tool["tool"] for tool in tools_used]
        
        if "create_event" in tool_names:
            return "schedule_meeting"
        elif "check_availability" in tool_names:
            return "check_availability"
        elif "get_events" in tool_names:
            return "view_calendar"
        elif "list_calendars" in tool_names:
            return "explore_calendars"
        elif any(word in message_lower for word in ["schedule", "meeting", "appointment", "book"]):
            return "schedule_request"
        elif any(word in message_lower for word in ["available", "availability", "free", "busy"]):
            return "availability_inquiry"
        elif any(word in message_lower for word in ["cancel", "reschedule", "move", "change"]):
            return "modify_meeting"
        elif any(word in message_lower for word in ["calendar", "events", "meetings", "agenda"]):
            return "calendar_inquiry"
        else:
            return "general_conversation"
    
    def _extract_information(self, message: str, response: str, tools_used: List[Dict]) -> Dict[str, Any]:
        """Extract structured information from the conversation."""
        extracted = {
            "message_timestamp": datetime.now().isoformat(),
            "tools_invoked": len(tools_used),
            "response_length": len(response)
        }
        
        message_lower = message.lower()
        
        # Extract temporal references
        temporal_keywords = {
            "today": "today",
            "tomorrow": "tomorrow", 
            "yesterday": "yesterday",
            "next week": "next_week",
            "this week": "this_week",
            "monday": "monday",
            "tuesday": "tuesday",
            "wednesday": "wednesday",
            "thursday": "thursday",
            "friday": "friday",
            "saturday": "saturday",
            "sunday": "sunday"
        }
        
        for keyword, value in temporal_keywords.items():
            if keyword in message_lower:
                extracted["temporal_reference"] = value
                break
        
        # Extract duration indicators
        if any(word in message_lower for word in ["hour", "hours"]):
            extracted["duration_mentioned"] = "hours"
        elif any(word in message_lower for word in ["minute", "minutes", "min"]):
            extracted["duration_mentioned"] = "minutes"
        
        # Extract meeting-related information
        if any(word in message_lower for word in ["with", "participant", "attendee"]):
            extracted["participants_mentioned"] = True
        
        if "location" in message_lower or "where" in message_lower:
            extracted["location_mentioned"] = True
        
        # Extract information from tool outputs
        for tool in tools_used:
            if tool["tool"] == "create_event":
                extracted["event_created"] = True
                # Try to extract event details from tool input
                try:
                    tool_input = tool["input"]
                    if isinstance(tool_input, dict):
                        extracted["event_details"] = {
                            "title": tool_input.get("title"),
                            "start_time": tool_input.get("start_datetime"),
                            "end_time": tool_input.get("end_datetime")
                        }
                except:
                    pass
            
            elif tool["tool"] == "check_availability":
                extracted["availability_checked"] = True
                if "FREE" in tool["output"]:
                    extracted["time_slot_available"] = True
                elif "CONFLICTS" in tool["output"]:
                    extracted["time_slot_available"] = False
        
        return extracted

# Agent factory function
def create_agent(openai_api_key: str = None, model_name: str = None, temperature: float = None) -> ExecutiveAssistantAgent:
    """Create and return an ExecutiveAssistantAgent instance."""
    
    # Use config defaults if not provided
    api_key = openai_api_key or Config.OPENAI_API_KEY
    model = model_name or Config.LLM_MODEL
    temp = temperature if temperature is not None else Config.LLM_TEMPERATURE
    
    if not api_key:
        raise ValueError("OpenAI API key is required")
    
    return ExecutiveAssistantAgent(
        openai_api_key=api_key,
        model_name=model,
        temperature=temp
    )

# Global agent instance
_agent_instance: Optional[ExecutiveAssistantAgent] = None

def get_agent() -> ExecutiveAssistantAgent:
    """Get the global agent instance, creating it if necessary."""
    global _agent_instance
    
    if _agent_instance is None:
        _agent_instance = create_agent()
        logger.info("Global agent instance created")
    
    return _agent_instance

def reset_agent():
    """Reset the global agent instance."""
    global _agent_instance
    _agent_instance = None
    logger.info("Global agent instance reset") 