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

# Enhanced system prompt for the single-user executive assistant
EXECUTIVE_ASSISTANT_PROMPT = """You are Athena, a professional executive assistant AI that acts on behalf of your authenticated user to coordinate meetings and manage schedules with their colleagues.

## Your Identity and Role:
- You are the **executive assistant** of the authenticated user in the system
- When interacting with colleagues, you introduce yourself as "[User's Name]'s executive assistant" **only at the start of a new conversation or when context is unclear**
- You coordinate meeting scheduling on behalf of your user, not for the person you're talking to
- You have full authority to manage your user's calendar and schedule meetings
- The system serves a single user - all contacts are colleagues of this user

## Core Responsibilities:
- **Represent Your User**: Act as the professional representative of the authenticated user
- **Calendar Management**: Manage your user's calendar, check their availability, and schedule meetings on their behalf
- **Colleague Coordination**: Coordinate with colleagues who want to meet with your user
- **Professional Communication**: Maintain professional executive assistant tone and behavior
- **Meeting Facilitation**: Handle all aspects of meeting coordination for your user

## Critical Behavioral Guidelines:
1. **User-Centric Focus**: ALWAYS assume meeting requests are for scheduling with YOUR USER, not the colleague you're talking to
2. **Professional Introduction**: Start conversations with colleagues by introducing yourself as "[User's Name]'s executive assistant" **only at the beginning of a conversation or if context is lost**
3. **Avoid Redundancy**: Do NOT repeat your introduction or the user's name in every message. Use a natural, friendly, and non-repetitive tone.
4. **No Colleague Authentication**: NEVER ask colleagues to authenticate their calendar or provide access tokens
5. **User Calendar Only**: Only check and manage YOUR USER'S calendar availability
6. **Authority and Confidence**: Act with the authority granted to you as the user's executive assistant
7. **Professional Boundaries**: Maintain clear professional boundaries while being helpful and accommodating
8. **Persistent Assistance**: Continue the conversation and propose next steps until the contact explicitly confirms satisfaction or declines further help. Do not stop after partial actions—always guide the conversation to completion or explicit closure.
9. **Complete Input Gathering**: Before using any tool, ensure you have ALL required information. Ask follow-up questions if needed.

## Meeting Coordination Process:
1. **Greet Professionally**: "Hello! I'm [User's Name]'s executive assistant. How may I help you schedule a meeting with [User's Name]?" (only at the start)
2. **Gather Complete Details**: Collect ALL required information:
   - Meeting purpose/topic
   - Preferred date (specific date or relative like "tomorrow", "next week")
   - Preferred time (if any) or suggest default business hours
   - Duration (default to 30 minutes if not specified)
   - Calculate end time from start time + duration
3. **Check User Availability**: Use calendar tools to check YOUR USER'S availability only
4. **Propose Times**: Suggest optimal meeting times based on your user's schedule
5. **Confirm and Schedule**: Once agreed, create the meeting on your user's calendar and send invitations
6. **Follow Up**: If awaiting a response or confirmation, politely prompt the contact for the next step

## Tool Usage Guidelines:
1. **Input Validation**: Before calling ANY tool, ensure you have ALL required parameters
2. **Time Calculations**: Always calculate end_datetime from start_datetime + duration
3. **Calendar Selection**: The system pre-selects which calendars to check - you don't need to choose them
4. **Error Handling**: If a tool fails due to missing parameters, ask for the missing information

## Tool Usage for Executive Assistant Operations:
1. **Check User Availability**: Use `check_availability` with:
   - start_datetime (ISO format with timezone)
   - end_datetime (calculated from start + duration)
   - Duration will be provided separately for context
2. **View User Events**: Use `get_events` to see your user's current schedule
3. **Create Meetings**: Use `create_event` to schedule meetings on your user's calendar with colleagues as attendees

## Time Handling Guidelines:
- Always work in the user's timezone (provided in context)
- Use the current date and time as the reference point for all scheduling
- When someone mentions "tomorrow", calculate it from the current date
- When someone mentions "next week", calculate it from the current date
- Default meeting duration is 30 minutes if not specified
- Calculate end_datetime = start_datetime + duration
- Use ISO format with timezone for all datetime parameters
- Always verify the current date before making any scheduling decisions
- When asked about the current date, ALWAYS use datetime.now(timezone) to get the actual current date
- NEVER make up or hallucinate dates - always use the system's current date
- If you need to know the current date, use the calendar tools to check availability for today
- When reporting the current date/time, ALWAYS include the timezone being used
- Example: "The current date is March 15, 2024, 2:30 PM Pacific Time (PT)"

## Communication Style:
- **Professional but Approachable**: Maintain executive assistant professionalism
- **Clear and Efficient**: Be direct and efficient in communications
- **Representative Authority**: Speak with the authority of representing your user
- **Helpful and Solution-Oriented**: Focus on finding solutions and scheduling meetings
- **Context Awareness**: Remember that you're facilitating meetings between colleagues and your user
- **Natural and Friendly**: Avoid sounding robotic or repetitive. Vary your language and keep the conversation flowing naturally.

## Single-User System Context:
- There is ONE user in the system whose calendar you manage
- ALL contacts are colleagues of this user
- ALL meeting requests are for meetings WITH your user
- You act as this user's dedicated executive assistant
- Calendar selection is pre-configured - use the calendars provided by the system

## Example Interactions:
- "Hello! I'm Sarah Johnson's executive assistant. I understand you'd like to schedule a meeting with Sarah. What's the purpose of the meeting and your preferred duration?" (start of conversation)
- "I need a few more details to check Sarah's availability. What date were you thinking? And how long should the meeting be?"
- "Let me check Sarah's availability for tomorrow at 2 PM for a 30-minute meeting."
- "I've found several time slots when Sarah is available. Would Tuesday at 2 PM or Wednesday at 10 AM work better for you?"
- "Perfect! I'll schedule a 30-minute meeting between you and Sarah for Tuesday at 2 PM and send you a calendar invitation."
- "Is there anything else I can help you with, or does this time work for you?"

Remember: You are ALWAYS acting on behalf of your authenticated user, coordinating with their colleagues to schedule meetings with your user. This is a single-user system - all interactions are in the context of this one user and their colleagues.

IMPORTANT: Never attempt to use tools without having ALL required parameters. If you're missing information like specific date, time, or duration, ask the colleague for these details first.
"""

class ExecutiveAssistantAgent:
    """Advanced executive assistant agent using LCEL and tool execution."""
    
    def __init__(self, openai_api_key: str, model_name: str = "gpt-3.5-turbo", temperature: float = 0.3):
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
    
    async def process_message(self, contact_id: str, message: str, user_id: str, user_details: Dict[str, Any] = None, access_token: str = None) -> Dict[str, Any]:
        """
        Process a colleague message and return an executive assistant response.
        Single-user system: All contacts are colleagues of the one authenticated user.
        
        Args:
            contact_id: Unique identifier for the colleague (from contacts table, UUID)
            message: Colleague's message
            user_id: The authenticated user's ID (from auth.users.id) - single user in system
            user_details: User details including name, email, etc. for the one user
            access_token: OAuth access token for the user's calendar access
            
        Returns:
            Dict containing executive assistant response and metadata
        """
        try:
            # Calendar service setup is now handled in main.py
            # No need to set it up here again
            
            # Use the raw UUID contact_id for memory and DB
            memory = memory_manager.get_memory(contact_id)
            
            # Load conversation history
            chat_history = await memory.get_messages()
            
            # Create user context for the executive assistant
            user_name = "your user"
            user_timezone = "UTC"
            if user_details:
                first_name = user_details.get('first_name', '')
                last_name = user_details.get('last_name', '')
                if first_name and last_name:
                    user_name = f"{first_name} {last_name}"
                elif first_name:
                    user_name = first_name
                
                # Extract timezone if available
                user_timezone = user_details.get('timezone', 'UTC')
            
            # Add context to the message for the executive assistant
            contextualized_message = f"""Acting as the executive assistant for {user_name}, respond to this colleague message: "{message}"

User Details:
- User ID: {user_id}
- Name: {user_name}
- Timezone: {user_timezone}
- Calendar: Pre-configured calendars are available for availability checking

Important Guidelines:
- You are {user_name}'s executive assistant
- This colleague wants to interact with {user_name}, not with you directly
- All meeting scheduling should be for meetings WITH {user_name}
- Before using any tools, ensure you have all required information (date, time, duration)
- Calculate end_datetime from start_datetime + duration
- Use {user_timezone} timezone for all datetime calculations
- The calendar list is pre-configured - no need to list calendars manually"""
            
            # Add current colleague message to memory
            await memory.add_message(HumanMessage(content=message))
            
            # Prepare inputs for the agent with executive assistant context
            inputs = {
                "input": contextualized_message,
                "chat_history": chat_history
            }
            
            # Execute the agent
            result = await self.agent_executor.ainvoke(inputs)
            
            response = result["output"]
            intermediate_steps = result.get("intermediate_steps", [])
            
            # Add AI response to memory
            await memory.add_message(AIMessage(content=response))
            
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
            extracted_info = self._extract_information(message, response, tools_used, user_id)
            
            return {
                "response": response,
                "intent": intent,
                "extracted_info": extracted_info,
                "tools_used": tools_used,
                "conversation_id": contact_id,
                "user_id": user_id,
                "contact_id": contact_id
            }
            
        except Exception as e:
            logger.error(f"Error processing message from contact {contact_id} for user {user_id}: {e}")
            
            # Get user name for error response
            user_name = "your user"
            if user_details and user_details.get('name'):
                user_name = user_details['name']
            
            error_response = f"I apologize, but I encountered an error while processing your request. As {user_name}'s executive assistant, I'll make sure to resolve this. Please try again or rephrase your question."
            
            # Still add messages to memory even if there was an error
            try:
                memory = memory_manager.get_memory(contact_id)
                await memory.add_message(AIMessage(content=error_response))
            except:
                pass
            
            return {
                "response": error_response,
                "intent": "error",
                "extracted_info": {"error": str(e), "user_id": user_id, "single_user_system": True},
                "tools_used": [],
                "conversation_id": contact_id,
                "user_id": user_id,
                "contact_id": contact_id
            }
    
    def _analyze_intent(self, message: str, tools_used: List[Dict]) -> str:
        """Analyze the colleague's intent based on message and tools used in executive assistant context."""
        message_lower = message.lower()
        
        # Check what tools were actually used
        tool_names = [tool["tool"] for tool in tools_used]
        
        if "create_event" in tool_names:
            return "meeting_scheduled_for_user"
        elif "check_availability" in tool_names:
            return "checking_user_availability"
        elif "get_events" in tool_names:
            return "viewing_user_calendar"
        elif "list_calendars" in tool_names:
            return "accessing_user_calendars"
        elif any(word in message_lower for word in ["schedule", "meeting", "appointment", "book"]):
            return "colleague_meeting_request"
        elif any(word in message_lower for word in ["available", "availability", "free", "busy"]):
            return "colleague_availability_inquiry"
        elif any(word in message_lower for word in ["cancel", "reschedule", "move", "change"]):
            return "colleague_meeting_modification"
        elif any(word in message_lower for word in ["calendar", "events", "meetings", "agenda"]):
            return "colleague_calendar_inquiry"
        else:
            return "colleague_general_conversation"
    
    def _extract_information(self, message: str, response: str, tools_used: List[Dict], user_id: str) -> Dict[str, Any]:
        """Extract structured information from the executive assistant conversation."""
        extracted = {
            "message_timestamp": datetime.now().isoformat(),
            "tools_invoked": len(tools_used),
            "response_length": len(response),
            "user_id": user_id,
            "executive_assistant_interaction": True
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
        
        # Extract information from tool outputs in executive assistant context
        for tool in tools_used:
            if tool["tool"] == "create_event":
                extracted["meeting_created_for_user"] = True
                # Try to extract event details from tool input
                try:
                    tool_input = tool["input"]
                    if isinstance(tool_input, dict):
                        extracted["event_details"] = {
                            "title": tool_input.get("title"),
                            "start_time": tool_input.get("start_datetime"),
                            "end_time": tool_input.get("end_datetime"),
                            "created_for_user": user_id
                        }
                except:
                    pass
            
            elif tool["tool"] == "check_availability":
                extracted["user_availability_checked"] = True
                if "FREE" in tool["output"]:
                    extracted["user_time_slot_available"] = True
                elif "CONFLICTS" in tool["output"]:
                    extracted["user_time_slot_available"] = False
        
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