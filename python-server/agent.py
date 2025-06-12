from typing import Dict, Any, List, Optional
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain_openai import ChatOpenAI
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.schema import SystemMessage, HumanMessage, AIMessage
from langchain.schema.runnable import RunnablePassthrough, RunnableLambda
from langchain.tools import Tool
import logging
from datetime import datetime, timedelta
import pytz
import json
import re

from memory import MemoryManager, memory_manager
from tools import calendar_tools, set_calendar_service
from config import Config

logger = logging.getLogger(__name__)

# Enhanced system prompt for the single-user executive assistant with strict validation
EXECUTIVE_ASSISTANT_PROMPT = """You are Athena, a professional executive assistant AI that acts on behalf of your authenticated user to coordinate meetings and manage schedules with their colleagues.

## CRITICAL TOOL USAGE RULES - READ CAREFULLY:
⚠️  BEFORE CALLING ANY TOOL, YOU MUST VERIFY YOU HAVE ALL REQUIRED INFORMATION:

**For check_availability tool:**
- REQUIRED: start_datetime (ISO format with timezone, e.g., '2024-01-15T09:00:00+08:00')
- REQUIRED: end_datetime (ISO format with timezone, e.g., '2024-01-15T10:00:00+08:00')
- OPTIONAL: duration_minutes (defaults to 30)

**For create_event tool:**
- REQUIRED: title (meeting subject/title)
- REQUIRED: start_datetime (ISO format with timezone)
- REQUIRED: end_datetime (ISO format with timezone)
- OPTIONAL: attendee_emails (list of email addresses)
- OPTIONAL: description (meeting description)
- OPTIONAL: location (meeting location)

**For get_events tool:**
- REQUIRED: start_datetime (ISO format with timezone)
- REQUIRED: end_datetime (ISO format with timezone)

🚫 **NEVER CALL A TOOL WITHOUT ALL REQUIRED PARAMETERS**
If you don't have the required information, STOP and ask the colleague for it. Do NOT proceed with incomplete data.

## Information Gathering Process:
1. **Check what you already know** from the conversation history
2. **Identify what's missing** for the tool you want to use
3. **Ask specifically** for missing required information
4. **Only call tools** once you have ALL required parameters
5. **Calculate end_datetime** from start_datetime + duration if needed

## Current Time Context:
- The current datetime will be provided in each message
- Always use the provided datetime as the reference point for all scheduling
- Never make up or hallucinate dates - use the provided datetime
- When someone mentions "tomorrow", calculate it from the provided datetime
- When someone mentions "next week", calculate it from the provided datetime
- Always work in the user's timezone (provided in context)
- When reporting the current date/time, ALWAYS include the timezone being used

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
   - Meeting purpose/topic (for title)
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

## Timezone Handling:
- When asked about timezone, simply respond with the user's timezone from the context
- DO NOT use any tools when responding to timezone questions
- The timezone information is provided in the context message
- Example response: "I'm using [User's Timezone] for all scheduling and time calculations."

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

⚠️  CRITICAL: Never attempt to use tools without having ALL required parameters. If you're missing information like specific date, time, or duration, ask the colleague for these details first. ALWAYS verify you have complete information before making any tool calls.
"""

class MeetingInfoExtractor:
    """Helper class to extract and validate meeting information from conversations."""
    
    @staticmethod
    def extract_meeting_details(message: str, chat_history: List, current_datetime: datetime, user_timezone: str) -> Dict[str, Any]:
        """Extract meeting details from message and chat history."""
        details = {
            "title": None,
            "date": None,
            "time": None,
            "duration": None,
            "start_datetime": None,
            "end_datetime": None,
            "description": None,
            "location": None,
            "attendees": [],
            "missing_required": []
        }
        
        # Extract from current message
        message_lower = message.lower()
        
        # Extract duration
        duration_match = re.search(r'(\d+)\s*(hour|hr|minute|min)', message_lower)
        if duration_match:
            value, unit = duration_match.groups()
            if 'hour' in unit or 'hr' in unit:
                details["duration"] = int(value) * 60
            else:
                details["duration"] = int(value)
        
        # Extract temporal references
        if "tomorrow" in message_lower:
            tomorrow = current_datetime + timedelta(days=1)
            details["date"] = tomorrow.strftime('%Y-%m-%d')
        elif "today" in message_lower:
            details["date"] = current_datetime.strftime('%Y-%m-%d')
        elif "next week" in message_lower:
            next_week = current_datetime + timedelta(days=7)
            details["date"] = next_week.strftime('%Y-%m-%d')
        
        # Extract time
        time_match = re.search(r'(\d{1,2}):?(\d{0,2})\s*(am|pm|AM|PM)', message_lower)
        if time_match:
            hour, minute, period = time_match.groups()
            hour = int(hour)
            minute = int(minute) if minute else 0
            if period.lower() == 'pm' and hour != 12:
                hour += 12
            elif period.lower() == 'am' and hour == 12:
                hour = 0
            details["time"] = f"{hour:02d}:{minute:02d}"
        
        # Extract meeting purpose/title
        purpose_patterns = [
            r'(?:meeting about|discuss|talk about|regarding)\s+(.+?)(?:\.|$|\n)',
            r'(?:for|about)\s+(.+?)(?:\.|$|\n)',
            r'(?:call|meeting)\s+(.+?)(?:\.|$|\n)'
        ]
        for pattern in purpose_patterns:
            match = re.search(pattern, message_lower)
            if match:
                details["title"] = match.group(1).strip()
                break
        
        # Check chat history for missing information
        history_text = " ".join([msg.content for msg in chat_history if hasattr(msg, 'content')])
        history_lower = history_text.lower()
        
        # Extract from history if not found in current message
        if not details["duration"]:
            duration_history = re.search(r'(\d+)\s*(hour|hr|minute|min)', history_lower)
            if duration_history:
                value, unit = duration_history.groups()
                if 'hour' in unit or 'hr' in unit:
                    details["duration"] = int(value) * 60
                else:
                    details["duration"] = int(value)
        
        if not details["title"]:
            for pattern in purpose_patterns:
                match = re.search(pattern, history_lower)
                if match:
                    details["title"] = match.group(1).strip()
                    break
        
        # Set defaults
        if not details["duration"]:
            details["duration"] = 30  # Default to 30 minutes
        
        if not details["title"]:
            details["title"] = "Meeting"  # Default title
        
        # Calculate start and end datetime if we have date and time
        if details["date"] and details["time"]:
            try:
                user_tz = pytz.timezone(user_timezone)
                start_dt = user_tz.localize(datetime.strptime(f"{details['date']} {details['time']}", '%Y-%m-%d %H:%M'))
                details["start_datetime"] = start_dt.isoformat()
                
                end_dt = start_dt + timedelta(minutes=details["duration"])
                details["end_datetime"] = end_dt.isoformat()
            except Exception as e:
                logger.error(f"Error calculating datetime: {e}")
        
        # Identify missing required information
        required_fields = ["date", "time"]
        for field in required_fields:
            if not details[field]:
                details["missing_required"].append(field)
        
        return details
    
    @staticmethod
    def _is_valid_iso_datetime(datetime_str: str) -> bool:
        """Check if string is a valid ISO datetime with timezone."""
        try:
            if not datetime_str:
                return False
            # Try to parse as ISO datetime
            datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
            return True
        except (ValueError, TypeError):
            return False

class ToolInputValidator:
    """Helper class to validate tool inputs before execution."""
    
    @staticmethod
    def validate_check_availability(start_datetime: str, end_datetime: str) -> Dict[str, Any]:
        """Validate inputs for check_availability tool."""
        errors = []
        
        if not start_datetime:
            errors.append("start_datetime is required")
        elif not MeetingInfoExtractor._is_valid_iso_datetime(start_datetime):
            errors.append("start_datetime must be in ISO format with timezone")
            
        if not end_datetime:
            errors.append("end_datetime is required")
        elif not MeetingInfoExtractor._is_valid_iso_datetime(end_datetime):
            errors.append("end_datetime must be in ISO format with timezone")
            
        return {"is_valid": len(errors) == 0, "errors": errors}
    
    @staticmethod
    def validate_create_event(title: str, start_datetime: str, end_datetime: str) -> Dict[str, Any]:
        """Validate inputs for create_event tool."""
        errors = []
        
        if not title or not title.strip():
            errors.append("title is required")
            
        if not start_datetime:
            errors.append("start_datetime is required")
        elif not MeetingInfoExtractor._is_valid_iso_datetime(start_datetime):
            errors.append("start_datetime must be in ISO format with timezone")
            
        if not end_datetime:
            errors.append("end_datetime is required")
        elif not MeetingInfoExtractor._is_valid_iso_datetime(end_datetime):
            errors.append("end_datetime must be in ISO format with timezone")
            
        return {"is_valid": len(errors) == 0, "errors": errors}
    
    @staticmethod
    def validate_get_events(start_datetime: str, end_datetime: str) -> Dict[str, Any]:
        """Validate inputs for get_events tool."""
        errors = []
        
        if not start_datetime:
            errors.append("start_datetime is required")
        elif not MeetingInfoExtractor._is_valid_iso_datetime(start_datetime):
            errors.append("start_datetime must be in ISO format with timezone")
            
        if not end_datetime:
            errors.append("end_datetime is required")
        elif not MeetingInfoExtractor._is_valid_iso_datetime(end_datetime):
            errors.append("end_datetime must be in ISO format with timezone")
            
        return {"is_valid": len(errors) == 0, "errors": errors}

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
    
    def _analyze_conversation_context(self, chat_history: List, message: str) -> Dict[str, Any]:
        """Analyze conversation context to understand what information is already available."""
        context = {
            "has_meeting_request": False,
            "has_date_preference": False,
            "has_time_preference": False,
            "has_duration": False,
            "has_title": False,
            "conversation_stage": "initial",
            "mentioned_keywords": []
        }
        
        # Combine all messages for analysis
        all_text = message.lower()
        if chat_history:
            history_text = " ".join([msg.content.lower() for msg in chat_history if hasattr(msg, 'content')])
            all_text = history_text + " " + all_text
        
        # Analyze content
        meeting_keywords = ["meeting", "schedule", "appointment", "book", "calendar", "availability"]
        time_keywords = ["tomorrow", "today", "next week", "monday", "tuesday", "wednesday", "thursday", "friday", "am", "pm"]
        duration_keywords = ["hour", "hours", "minute", "minutes", "min", "hr"]
        
        context["mentioned_keywords"] = [keyword for keyword in meeting_keywords + time_keywords + duration_keywords if keyword in all_text]
        context["has_meeting_request"] = any(keyword in all_text for keyword in meeting_keywords)
        context["has_time_preference"] = any(keyword in all_text for keyword in time_keywords)
        context["has_duration"] = any(keyword in all_text for keyword in duration_keywords)
        
        # Determine conversation stage
        if not context["has_meeting_request"]:
            context["conversation_stage"] = "initial"
        elif context["has_meeting_request"] and not context["has_time_preference"]:
            context["conversation_stage"] = "gathering_time"
        elif context["has_time_preference"] and not context["has_duration"]:
            context["conversation_stage"] = "gathering_duration"
        else:
            context["conversation_stage"] = "ready_to_schedule"
        
        return context
    
    def _should_block_tool_execution(self, tool_name: str, tool_input: Dict[str, Any], conversation_context: Dict[str, Any]) -> Dict[str, Any]:
        """Determine if tool execution should be blocked due to missing required information."""
        blocking_result = {"should_block": False, "reason": "", "missing_info": []}
        
        # First check if this is a timezone-related question
        if any(word in conversation_context.get("mentioned_keywords", []) for word in ["timezone", "time zone", "tz"]):
            blocking_result.update({
                "should_block": True,
                "reason": "This is a timezone-related question. No tools should be used.",
                "missing_info": []
            })
            return blocking_result
        
        # Then proceed with normal tool validation
        if tool_name == "check_availability":
            validation = ToolInputValidator.validate_check_availability(
                tool_input.get("start_datetime", ""),
                tool_input.get("end_datetime", "")
            )
            if not validation["is_valid"]:
                blocking_result.update({
                    "should_block": True,
                    "reason": f"Missing required parameters for check_availability: {', '.join(validation['errors'])}",
                    "missing_info": validation["errors"]
                })
        
        elif tool_name == "create_event":
            validation = ToolInputValidator.validate_create_event(
                tool_input.get("title", ""),
                tool_input.get("start_datetime", ""),
                tool_input.get("end_datetime", "")
            )
            if not validation["is_valid"]:
                blocking_result.update({
                    "should_block": True,
                    "reason": f"Missing required parameters for create_event: {', '.join(validation['errors'])}",
                    "missing_info": validation["errors"]
                })
        
        elif tool_name == "get_events":
            validation = ToolInputValidator.validate_get_events(
                tool_input.get("start_datetime", ""),
                tool_input.get("end_datetime", "")
            )
            if not validation["is_valid"]:
                blocking_result.update({
                    "should_block": True,
                    "reason": f"Missing required parameters for get_events: {', '.join(validation['errors'])}",
                    "missing_info": validation["errors"]
                })
        
        return blocking_result
    
    async def _gather_missing_inputs(self, tool_name: str, missing_info: List[str], chat_history: List) -> Dict[str, Any]:
        """Gather missing inputs through conversation."""
        gathering_prompt = f"""You are gathering missing information for the {tool_name} tool.
        Missing required parameters: {', '.join(missing_info)}
        
        Ask ONE question at a time to gather the missing information.
        Be specific about what information you need and in what format.
        Do not ask for all missing information at once.
        
        Current chat history:
        {chat_history}
        
        Ask for the first missing parameter:"""
        
        response = await self.llm.ainvoke(gathering_prompt)
        return {"question": response.content, "missing_info": missing_info}
    
    async def _handle_tool_execution_error(self, error: Exception, tool_name: str, tool_input: Dict[str, Any], 
                                         chat_history: List, conversation_context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tool execution errors by gathering missing information."""
        error_str = str(error)
        missing_info = []
        
        # Extract missing parameters from error message
        if "missing" in error_str.lower() and "required" in error_str.lower():
            # Parse error message to extract missing parameters
            missing_params = re.findall(r"missing.*?required.*?arguments?:?\s*([^:]+)", error_str, re.IGNORECASE)
            if missing_params:
                missing_info = [param.strip() for param in missing_params[0].split(',')]
        
        if missing_info:
            # Gather missing inputs through conversation
            gathering_result = await self._gather_missing_inputs(tool_name, missing_info, chat_history)
            
            # Add the gathering question to chat history
            chat_history.append(HumanMessage(content=gathering_result["question"]))
            
            return {
                "status": "gathering_inputs",
                "question": gathering_result["question"],
                "missing_info": missing_info,
                "tool_name": tool_name,
                "original_input": tool_input
            }
        
        return {
            "status": "error",
            "error": str(error),
            "tool_name": tool_name
        }
    
    async def process_message(self, contact_id: str, message: str, user_id: str, user_details: Dict[str, Any] = None, access_token: str = None) -> Dict[str, Any]:
        """Process a message with enhanced error handling and input gathering."""
        try:
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
                user_timezone = user_details.get('default_timezone', 'UTC')
            
            # Get current datetime in user's timezone
            user_tz = pytz.timezone(user_timezone)
            current_datetime = datetime.now(user_tz)
            
            # Analyze conversation context
            conversation_context = self._analyze_conversation_context(chat_history, message)
            logger.info(f"Conversation context: {conversation_context}")
            
            # Extract meeting details from message and history
            meeting_details = MeetingInfoExtractor.extract_meeting_details(
                message, chat_history, current_datetime, user_timezone
            )
            logger.info(f"Extracted meeting details: {meeting_details}")
            
            # Enhanced context message with validation prompts
            contextualized_message = f"""Acting as the executive assistant for {user_name}, respond to this colleague message: "{message}"

Current Time Context:
- Current datetime: {current_datetime.strftime('%Y-%m-%d %H:%M:%S %Z')}
- User's timezone: {user_timezone}

User Details:
- User ID: {user_id}
- Name: {user_name}
- Timezone: {user_timezone}
- Calendar: Pre-configured calendars are available for availability checking

Conversation Analysis:
- Stage: {conversation_context['conversation_stage']}
- Has meeting request: {conversation_context['has_meeting_request']}
- Has time preference: {conversation_context['has_time_preference']}
- Has duration: {conversation_context['has_duration']}
- Keywords mentioned: {', '.join(conversation_context['mentioned_keywords'])}

Extracted Meeting Information:
- Title: {meeting_details.get('title', 'Not specified')}
- Date: {meeting_details.get('date', 'Not specified')}
- Time: {meeting_details.get('time', 'Not specified')}
- Duration: {meeting_details.get('duration', 'Not specified')} minutes
- Start datetime: {meeting_details.get('start_datetime', 'Not calculated')}
- End datetime: {meeting_details.get('end_datetime', 'Not calculated')}
- Missing required info: {', '.join(meeting_details.get('missing_required', []))}

CRITICAL VALIDATION RULES:
⚠️  Before calling ANY tool, verify you have ALL required parameters:
- check_availability: MUST have start_datetime AND end_datetime
- create_event: MUST have title AND start_datetime AND end_datetime  
- get_events: MUST have start_datetime AND end_datetime

🚫 If ANY required parameter is missing, DO NOT call the tool. Instead, ask the colleague for the missing information.

Important Guidelines:
- You are {user_name}'s executive assistant
- This colleague wants to interact with {user_name}, not with you directly
- All meeting scheduling should be for meetings WITH {user_name}
- Before using any tools, ensure you have all required information (date, time, duration)
- Calculate end_datetime from start_datetime + duration
- Use {user_timezone} timezone for all datetime calculations
- The calendar list is pre-configured - no need to list calendars manually
- Always use the current datetime ({current_datetime.strftime('%Y-%m-%d %H:%M:%S %Z')}) as reference for relative time expressions"""
            
            # Add current colleague message to memory
            await memory.add_message(HumanMessage(content=message))
            
            # Log detailed input for debugging
            logger.info(f"=== AGENT EXECUTION START ===")
            logger.info(f"Contact ID: {contact_id}")
            logger.info(f"User ID: {user_id}")
            logger.info(f"Original Message: {message}")
            logger.info(f"Contextualized Message Length: {len(contextualized_message)} chars")
            logger.info(f"Chat History Length: {len(chat_history)} messages")
            
            # Prepare inputs for the agent with executive assistant context
            inputs = {
                "input": contextualized_message,
                "chat_history": chat_history
            }
            
            # Execute the agent with enhanced monitoring
            logger.info("=== STARTING AGENT EXECUTION ===")
            result = await self.agent_executor.ainvoke(inputs)
            logger.info("=== AGENT EXECUTION COMPLETED ===")
            
            response = result["output"]
            intermediate_steps = result.get("intermediate_steps", [])
            
            # Enhanced logging of tool chain execution
            logger.info(f"=== TOOL EXECUTION CHAIN ===")
            logger.info(f"Number of intermediate steps: {len(intermediate_steps)}")
            
            tools_used = []
            for i, step in enumerate(intermediate_steps):
                if len(step) >= 2:
                    action, observation = step[0], step[1]
                    tool_info = {
                        "step": i + 1,
                        "tool": action.tool,
                        "input": action.tool_input,
                        "output": str(observation)[:200] + "..." if len(str(observation)) > 200 else str(observation)
                    }
                    tools_used.append(tool_info)
                    
                    # Detailed tool execution logging
                    logger.info(f"STEP {i + 1}: Tool '{action.tool}' called")
                    logger.info(f"  Input: {action.tool_input}")
                    logger.info(f"  Output: {str(observation)[:500]}{'...' if len(str(observation)) > 500 else ''}")
                    
                    # Check if this tool call should have been blocked
                    blocking_check = self._should_block_tool_execution(action.tool, action.tool_input, conversation_context)
                    if blocking_check["should_block"]:
                        logger.warning(f"  ⚠️  TOOL CALL SHOULD HAVE BEEN BLOCKED: {blocking_check['reason']}")
                        logger.warning(f"  Missing information: {blocking_check['missing_info']}")
                        
                        # Handle missing inputs through conversation
                        error_handling = await self._handle_tool_execution_error(
                            Exception(blocking_check["reason"]),
                            action.tool,
                            action.tool_input,
                            chat_history,
                            conversation_context
                        )
                        
                        if error_handling["status"] == "gathering_inputs":
                            # Add the gathering question to memory
                            await memory.add_message(AIMessage(content=error_handling["question"]))
                            
                            # Return the gathering question to continue the conversation
                            return {
                                "response": error_handling["question"],
                                "intent": "gathering_inputs",
                                "extracted_info": {
                                    "missing_info": error_handling["missing_info"],
                                    "tool_name": error_handling["tool_name"],
                                    "original_input": error_handling["original_input"]
                                },
                                "tools_used": tools_used,
                                "conversation_id": contact_id,
                                "user_id": user_id,
                                "contact_id": contact_id
                            }
            
            # Add AI response to memory
            await memory.add_message(AIMessage(content=response))
            
            # Analyze the response for intent and extracted information
            intent = self._analyze_intent(message, tools_used)
            extracted_info = self._extract_information(message, response, tools_used, user_id)
            
            # Add current datetime and validation info to extracted info
            extracted_info.update({
                "current_datetime": current_datetime.isoformat(),
                "user_timezone": user_timezone,
                "conversation_context": conversation_context,
                "meeting_details_extracted": meeting_details,
                "tool_validation_performed": True
            })
            
            logger.info(f"=== AGENT EXECUTION END ===")
            logger.info(f"Response length: {len(response)} chars")
            logger.info(f"Tools used: {[tool['tool'] for tool in tools_used]}")
            logger.info(f"Intent analyzed: {intent}")
            
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
            logger.error(f"=== AGENT EXECUTION ERROR ===")
            logger.error(f"Error processing message from contact {contact_id} for user {user_id}: {e}")
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error details: {str(e)}")
            
            # Get user name for error response
            user_name = "your user"
            if user_details:
                first_name = user_details.get('first_name', '')
                last_name = user_details.get('last_name', '')
                if first_name and last_name:
                    user_name = f"{first_name} {last_name}"
                elif first_name:
                    user_name = first_name
            
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
                "extracted_info": {
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "user_id": user_id,
                    "single_user_system": True,
                    "validation_enhanced": True
                },
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