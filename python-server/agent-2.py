from typing import Dict, Any, List, Optional, Literal, TypedDict, Annotated
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, AIMessage, SystemMessage, BaseMessage
from langchain.tools import tool
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain import hub
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
# ToolExecutor not needed for this simplified agent
# MemorySaver not needed for LangGraph API
import logging
from datetime import datetime, timedelta
import pytz
import json

from tools import calendar_tools, set_calendar_service, set_llm_instance
from config import Config

logger = logging.getLogger(__name__)

# Improved State Schema using LangChain message types
class SimpleState(TypedDict):
    """Simplified state schema for Athena agent using proper message handling."""
    messages: Annotated[List[BaseMessage], add_messages]
    user_id: str
    contact_id: str
    message_intent: Optional[str]
    metadata: Optional[Dict[str, Any]]

# Tool definitions using @tool decorator
@tool
async def check_availability_tool(query: str, duration_minutes: int = 30) -> str:
    """Check calendar availability based on natural language query.
    
    Args:
        query: Natural language description of when you want to check availability
        duration_minutes: Expected meeting duration in minutes (default 30)
    """
    try:
        # Use the existing check_availability tool from calendar_tools with async execution
        availability_tool = next(t for t in calendar_tools if t.name == "check_availability")
        result = await availability_tool._arun(query=query, duration_minutes=duration_minutes)
        return result
    except Exception as e:
        logger.error(f"Error in check_availability_tool: {e}")
        return f"I had trouble checking availability. Please try again or provide more specific time details."

@tool
def create_event_tool(title: str, start_datetime: str, end_datetime: str, 
                     attendee_emails: List[str] = None, description: str = "", 
                     location: str = "") -> str:
    """Create a new calendar event.
    
    Args:
        title: Meeting title
        start_datetime: Start time in ISO format with timezone
        end_datetime: End time in ISO format with timezone
        attendee_emails: List of attendee email addresses
        description: Meeting description
        location: Meeting location
    """
    try:
        create_tool = next(t for t in calendar_tools if t.name == "create_event")
        result = create_tool._run(
            title=title,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            attendee_emails=attendee_emails or [],
            description=description,
            location=location
        )
        return result
    except Exception as e:
        logger.error(f"Error in create_event_tool: {e}")
        return f"I had trouble creating the event. Please check the details and try again."

@tool
def get_events_tool(start_datetime: str, end_datetime: str) -> str:
    """Get calendar events in a specific date range.
    
    Args:
        start_datetime: Start of date range in ISO format with timezone
        end_datetime: End of date range in ISO format with timezone
    """
    try:
        events_tool = next(t for t in calendar_tools if t.name == "get_events")
        result = events_tool._run(start_datetime=start_datetime, end_datetime=end_datetime)
        return result
    except Exception as e:
        logger.error(f"Error in get_events_tool: {e}")
        return f"I had trouble retrieving calendar events. Please try again."

@tool
def get_current_time_tool(timezone: str = "UTC") -> str:
    """Get current date and time in specified timezone.
    
    Args:
        timezone: Timezone (e.g., 'UTC', 'US/Pacific', 'Europe/London')
    """
    try:
        tz = pytz.timezone(timezone)
        current_time = datetime.now(tz)
        return f"Current time in {timezone}: {current_time.strftime('%Y-%m-%d %H:%M:%S %Z')}"
    except Exception as e:
        logger.error(f"Error in get_current_time_tool: {e}")
        return f"I had trouble getting the current time for timezone {timezone}."

@tool
def convert_relative_time_tool(time_reference: str, timezone: str = "UTC") -> str:
    """Convert relative time references like 'tomorrow at 10 AM' to ISO datetime format.
    
    Args:
        time_reference: Natural language time reference (e.g., 'tomorrow at 10 AM', 'next Monday at 2 PM')
        timezone: Timezone to use for conversion (default: UTC)
    """
    try:
        tz = pytz.timezone(timezone)
        current_time = datetime.now(tz)
        
        # Parse common relative time patterns
        time_ref_lower = time_reference.lower().strip()
        
        # Extract time if present
        time_match = None
        import re
        
        # Try pattern for time with AM/PM (e.g., "10 AM", "2 PM")
        am_pm_pattern = r'(\d{1,2})\s*(am|pm)'
        match = re.search(am_pm_pattern, time_ref_lower)
        if match:
            hour = int(match.group(1))
            minute = 0  # No minutes specified
            ampm = match.group(2)
            
            if ampm == 'pm' and hour != 12:
                hour += 12
            elif ampm == 'am' and hour == 12:
                hour = 0
            
            time_match = (hour, minute)
        else:
            # Try pattern for time with minutes (e.g., "10:30 AM", "14:30")
            time_with_minutes_pattern = r'(\d{1,2}):(\d{2})\s*(am|pm)?'
            match = re.search(time_with_minutes_pattern, time_ref_lower)
            if match:
                hour = int(match.group(1))
                minute = int(match.group(2))
                ampm = match.group(3) if match.group(3) else None
                
                if ampm:
                    if ampm == 'pm' and hour != 12:
                        hour += 12
                    elif ampm == 'am' and hour == 12:
                        hour = 0
                
                time_match = (hour, minute)
        
        # Default to 9 AM if no time specified
        if not time_match:
            time_match = (9, 0)
            logger.info(f"No time found in '{time_reference}', defaulting to 9:00 AM")
        
        logger.info(f"Extracted time: {time_match[0]:02d}:{time_match[1]:02d}")
        
        # Determine the date
        target_date = None
        if 'tomorrow' in time_ref_lower:
            target_date = current_time + timedelta(days=1)
            logger.info("Detected 'tomorrow' - adding 1 day")
        elif 'today' in time_ref_lower:
            target_date = current_time
            logger.info("Detected 'today' - using current date")
        elif 'yesterday' in time_ref_lower:
            target_date = current_time - timedelta(days=1)
            logger.info("Detected 'yesterday' - subtracting 1 day")
        else:
            # Default to today if no date specified
            target_date = current_time
            logger.info("No date reference found, defaulting to today")
        
        # Create the datetime
        result_datetime = target_date.replace(
            hour=time_match[0], 
            minute=time_match[1], 
            second=0, 
            microsecond=0
        )
        
        # Convert to ISO format
        iso_datetime = result_datetime.isoformat()
        
        logger.info(f"Successfully converted '{time_reference}' to {iso_datetime}")
        return f"'{time_reference}' converts to: {iso_datetime}"
        
    except Exception as e:
        logger.error(f"Error in convert_relative_time_tool with input '{time_reference}': {e}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        return f"I had trouble converting the time reference '{time_reference}'. Please provide a more specific date and time."

# Bundle tools
tools = [check_availability_tool, create_event_tool, get_events_tool, get_current_time_tool, convert_relative_time_tool]

class SimpleAthenaAgent:
    """Simplified Athena agent with cleaner architecture."""
    
    def __init__(self, openai_api_key: str, model_name: str = "gpt-3.5-turbo", temperature: float = 0.3):
        """Initialize the simplified agent."""
        self.llm = ChatOpenAI(
            temperature=temperature,
            model_name=model_name,
            openai_api_key=openai_api_key
        )
        
        # Set LLM instance for tools
        set_llm_instance(self.llm)
        
        # Create agents
        self.intent_classifier = self._create_intent_classifier()
        self.execution_decider = self._create_execution_decider()
        
        # Create the graph
        self.graph = self._create_graph()
        
        logger.info("Simple Athena agent initialized successfully")
    
    def _create_intent_classifier(self):
        """Create intent classifier agent."""
        intent_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an intent classifier for Athena, a professional executive assistant AI. 

Your task is to carefully analyze user messages and classify them into one of these intents:

1. general_conversation - Greetings, casual chat, off-topic discussions

2. clarification_answer - User is providing additional details or answering a clarifying question that the assistant asked
   • Look for messages that are clearly responding to a previous question from the assistant
   • Common patterns: providing missing details, specifying times/dates, confirming information
   • Examples: "Tomorrow at 3 PM", "Yes, that works", "The client presentation", "Pacific timezone"
   • Key indicator: The message makes most sense as an answer to a previous assistant question

3. meeting_request - User wants to schedule, book, or create a new meeting or appointment
   • Initial requests to schedule something new
   • Examples: "Schedule a meeting", "Can we meet tomorrow?", "Book time with John"

4. calendar_inquiry - User wants to see, review, or check existing calendar events
   • Examples: "What's on my calendar?", "Show me tomorrow's schedule"

5. availability_inquiry - User wants to check free time, availability, or open slots
   • Examples: "When am I free?", "What slots are available?", "Check my availability"

6. meeting_modification - User wants to change, cancel, reschedule, or modify existing meetings
   • Examples: "Cancel my 2 PM meeting", "Move the call to Thursday"

7. time_question - User asks about current time, timezone information, or date/time clarification
   • Examples: "What time is it?", "What timezone are you using?"

CRITICAL: If the user's message appears to be answering a question or providing requested details (even without explicit question markers), classify as "clarification_answer".

Always classify based on the user's primary intent, even if the message contains multiple elements.
Respond with ONLY the intent name (e.g., "meeting_request").
            """),
            MessagesPlaceholder(variable_name="messages"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
        
        return create_tool_calling_agent(self.llm, [], intent_prompt)
    
    def _create_execution_decider(self):
        """Create execution decider agent with all tools."""
        execution_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are Athena, a professional and intelligent executive assistant AI.

Your role is to help users manage their calendar and schedule meetings efficiently. You have access to powerful calendar tools:
- Check availability using natural language queries
- Create calendar events and meetings
- Retrieve existing calendar events
- Get current time and timezone information
- Convert relative time references (like "tomorrow at 10 AM") to proper ISO datetime format

IMPORTANT GUIDELINES:
1. **Be Conversational & Natural**: Always communicate in a warm, professional, and human-like manner
2. **Gather Information Thoughtfully**: When details are missing, ask clarifying questions naturally rather than listing requirements
3. **Handle Challenges Gracefully**: If something doesn't work as expected, provide helpful alternatives without mentioning technical issues
4. **Validate Inputs Carefully**: Before using tools, ensure you have all necessary information in the correct format
5. **Be Proactive**: Anticipate user needs and offer helpful suggestions

HANDLING CLARIFICATION ANSWERS:
When users provide additional information (clarification_answer intent), treat it as continuing the previous conversation:
- Review the conversation history to understand what information was requested
- Combine the new details with previous context to complete the task
- If you now have enough information, proceed with the appropriate action (create meeting, check availability, etc.)
- If still missing critical details, ask for the remaining information naturally
- Always acknowledge the information they provided: "Great! So that's [summary of info]..."

INTELLIGENT TIME PROCESSING:
- ALWAYS extract temporal information from conversation history (yesterday, today, tomorrow, specific dates/times)
- Convert relative time references to proper ISO datetime format using get_current_time_tool if needed
- When you see "tomorrow at 10 AM", calculate the actual date and convert to ISO format
- "About an hour" = 60 minutes duration
- "Just me" = no attendees needed

When scheduling meetings, I need:
- Meeting title/purpose
- Date and time (be specific about timezone if unclear)  
- Duration or end time
- Any attendees (optional)

CRITICAL: If you have sufficient information from conversation history, PROCEED with creating the meeting instead of asking for confirmation. Don't ask users to repeat information they already provided.

EXAMPLES of intelligent processing:
User: "Schedule a meeting tomorrow at 10 AM for catching up, about an hour, just me"
Assistant: 
1. Use convert_relative_time_tool("tomorrow at 10 AM") to get ISO start time
2. Calculate end time (start + 60 minutes) 
3. Extract: title="catch-up meeting", no attendees needed
4. IMMEDIATELY use create_event_tool with the ISO datetime values

User provides clarification: "Meeting is catching up, about an hour, just me" 
Assistant: Review conversation history, see "tomorrow at 10 AM" was mentioned before
1. Use convert_relative_time_tool("tomorrow at 10 AM") 
2. Extract all info: title="catching up", duration=60 mins, no attendees
3. PROCEED with create_event_tool instead of asking for confirmation

Always double-check that dates and times make sense before proceeding.
            """),
            MessagesPlaceholder(variable_name="messages"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
        
        return create_tool_calling_agent(self.llm, tools, execution_prompt)
    
    def _create_graph(self) -> StateGraph:
        """Create the LangGraph workflow."""
        # Initialize the graph
        workflow = StateGraph(SimpleState)
        
        # Add nodes
        workflow.add_node("intent_classifier", self._intent_classifier_node)
        workflow.add_node("execution_decider", self._execution_decider_node)
        workflow.add_node("meeting_request", self._meeting_request_node)
        workflow.add_node("calendar_inquiry", self._calendar_inquiry_node)
        workflow.add_node("availability_inquiry", self._availability_inquiry_node)
        workflow.add_node("meeting_modification", self._meeting_modification_node)
        workflow.add_node("time_question", self._time_question_node)
        workflow.add_node("general_conversation", self._general_conversation_node)
        
        # Set entry point
        workflow.set_entry_point("intent_classifier")
        
        # Add routing from intent classifier
        workflow.add_conditional_edges(
            "intent_classifier",
            self._route_by_intent,
            {
                "general_conversation": "general_conversation",
                "clarification_answer": "execution_decider",
                "meeting_request": "execution_decider",
                "calendar_inquiry": "execution_decider", 
                "availability_inquiry": "execution_decider",
                "meeting_modification": "execution_decider",
                "time_question": "execution_decider"
            }
        )
        
        # Route from execution_decider to specific nodes
        workflow.add_conditional_edges(
            "execution_decider",
            self._route_from_execution_decider,
            {
                "meeting_request": "meeting_request",
                "calendar_inquiry": "calendar_inquiry",
                "availability_inquiry": "availability_inquiry", 
                "meeting_modification": "meeting_modification",
                "time_question": "time_question",
                "end": END
            }
        )
        
        # All specific nodes route back to execution_decider
        for node in ["meeting_request", "calendar_inquiry", "availability_inquiry", 
                    "meeting_modification", "time_question"]:
            workflow.add_edge(node, "execution_decider")
        
        # Add edge from execution_decider to END
        workflow.add_edge("general_conversation", END)
        workflow.add_edge("execution_decider", END)
        
        return workflow.compile()
    
    # Node implementations
    async def _intent_classifier_node(self, state: SimpleState) -> SimpleState:
        """Classify the intent of the user's message."""
        logger.info("🔍 Intent Classifier Node")
        
        # Get latest message content
        latest_message_content = ""
        if state["messages"]:
            latest_message = state["messages"][-1]
            if isinstance(latest_message, HumanMessage):
                latest_message_content = latest_message.content
            elif hasattr(latest_message, 'content'):
                latest_message_content = latest_message.content
        
        # Use the intent classifier agent with recent context for better classification
        # Include last few messages for context (max 3 messages)
        context_messages = state["messages"][-3:] if len(state["messages"]) > 1 else [HumanMessage(content=latest_message_content)]
        agent_executor = AgentExecutor(agent=self.intent_classifier, tools=[], verbose=True)
        
        try:
            result = await agent_executor.ainvoke({"messages": context_messages})
            intent = result["output"].strip().lower()
            
            # Validate intent
            valid_intents = [
                "general_conversation", "clarification_answer", "meeting_request", 
                "calendar_inquiry", "availability_inquiry", "meeting_modification",
                "time_question"
            ]
            
            if intent not in valid_intents:
                intent = "general_conversation"
            
            state["message_intent"] = intent
            logger.info(f"Intent classified: {intent}")
            
            if intent == "clarification_answer":
                logger.info("🔄 Detected clarification answer - will provide conversation context to execution decider")
            
        except Exception as e:
            logger.error(f"Intent classification error: {e}")
            state["message_intent"] = "general_conversation"
        
        return state
    
    async def _execution_decider_node(self, state: SimpleState) -> SimpleState:
        """Decide how to execute based on the message."""
        logger.info("⚡ Execution Decider Node")
        
        # Get message intent to determine how to handle this
        message_intent = state.get("message_intent", "")
        
        # For clarification answers, include conversation context
        if message_intent == "clarification_answer":
            logger.info("🔄 Processing clarification answer - including conversation context")
            # Use the full conversation history for context
            messages = state["messages"].copy()
            # Add a system message to help the agent understand this is a clarification
            clarification_context = SystemMessage(content="""The user is providing additional information in response to a previous question you asked. 

IMPORTANT: Review the ENTIRE conversation history to extract ALL relevant information:
- Meeting details (title, purpose, type)
- Time references (tomorrow, today, specific times like "10 AM")
- Duration ("about an hour" = 60 minutes, "30 minutes", etc.)
- Attendees ("just me" = no attendees, specific names/emails)

If you now have sufficient information, PROCEED with the action (like creating a meeting) instead of asking for more details. Use get_current_time_tool to convert relative times to proper ISO format.""")
            messages.insert(-1, clarification_context)  # Insert before the last user message
        else:
            # For other intents, use conversation context for better information extraction
            # Include recent conversation history (max 5 messages) for context
            messages = state["messages"][-5:] if len(state["messages"]) > 1 else state["messages"].copy()
            
            # Add context for information extraction
            if message_intent in ["meeting_request", "calendar_inquiry", "availability_inquiry"]:
                extraction_context = SystemMessage(content="""Extract ALL relevant information from the conversation history:
- Time references: Convert "tomorrow", "today", "next week", specific times like "10 AM" to proper datetime
- Duration: "about an hour" = 60 minutes, "30 min" = 30 minutes
- Meeting details: titles, purposes, attendee information
- Use get_current_time_tool to calculate exact dates from relative time references
- If you have sufficient information, proceed with the action instead of asking redundant questions.""")
                messages.insert(0, extraction_context)
        
        # Use the execution decider agent with tools
        agent_executor = AgentExecutor(agent=self.execution_decider, tools=tools, verbose=True)
        
        try:
            result = await agent_executor.ainvoke({"messages": messages})
            response = result["output"]
            # Use proper message type instead of string appending
            return {
                **state,
                "messages": state["messages"] + [AIMessage(content=response)]
            }
            
        except Exception as e:
            logger.error(f"Execution decider error: {e}")
            return {
                **state,
                "messages": state["messages"] + [AIMessage(content="I'd be happy to help you with that! Could you provide a bit more detail about what you'd like me to do?")]
            }
    
    async def _meeting_request_node(self, state: SimpleState) -> SimpleState:
        """Handle meeting request intent."""
        logger.info("📅 Meeting Request Node")
        
        # Get latest message content
        latest_message_content = ""
        if state["messages"]:
            latest_message = state["messages"][-1]
            if isinstance(latest_message, HumanMessage):
                latest_message_content = latest_message.content
            elif hasattr(latest_message, 'content'):
                latest_message_content = latest_message.content
        
        # Create a specific prompt for meeting requests
        meeting_prompt = f"""
        The user wants to schedule a meeting. Their message: "{latest_message_content}"
        
        As their executive assistant, help them by:
        1. Understanding what kind of meeting they want to schedule
        2. Identifying what information you have and what might be missing
        3. If you have all the essential details (title, date/time, duration), proceed to create the event
        4. If key information is missing, ask for it in a natural, helpful way
        
        Essential information needed:
        - Meeting title/purpose
        - Date and time (with timezone clarity)
        - Duration or end time
        - Attendees (if any)
        
        Be warm and conversational. Instead of saying "I need X, Y, Z", ask naturally like:
        "That sounds great! What day and time would work best for this meeting?"
        
        Always validate that the proposed time makes sense and isn't in the past.
        """
        
        messages = [HumanMessage(content=meeting_prompt)]
        agent_executor = AgentExecutor(agent=self.execution_decider, tools=tools, verbose=True)
        
        try:
            result = await agent_executor.ainvoke({"messages": messages})
            response = result["output"]
            return {
                **state,
                "messages": state["messages"] + [AIMessage(content=response)]
            }
            
        except Exception as e:
            logger.error(f"Meeting request error: {e}")
            return {
                **state,
                "messages": state["messages"] + [AIMessage(content="I'd be happy to help you schedule that meeting! To get started, could you let me know what day and time would work best, and what the meeting is for?")]
            }
    
    async def _calendar_inquiry_node(self, state: SimpleState) -> SimpleState:
        """Handle calendar inquiry intent."""
        logger.info("📋 Calendar Inquiry Node")
        
        # Get latest message content
        latest_message_content = ""
        if state["messages"]:
            latest_message = state["messages"][-1]
            if isinstance(latest_message, HumanMessage):
                latest_message_content = latest_message.content
            elif hasattr(latest_message, 'content'):
                latest_message_content = latest_message.content
        
        # Create a specific prompt for calendar inquiries
        calendar_prompt = f"""
        The user wants to know about their calendar events. Their message: "{latest_message_content}"
        
        As their executive assistant, help them by:
        1. Understanding what time period or specific events they're asking about
        2. If the timeframe is clear, use get_events_tool to retrieve their calendar
        3. Present the information in a clear, organized way
        4. If the time period isn't specific enough, ask naturally for clarification
        
        Be conversational and helpful. For example:
        "I'd be happy to check your calendar! Which day or time period would you like me to look at?"
        
        When presenting calendar information, organize it in a user-friendly format with dates, times, and event titles.
        """
        
        messages = [HumanMessage(content=calendar_prompt)]
        agent_executor = AgentExecutor(agent=self.execution_decider, tools=tools, verbose=True)
        
        try:
            result = await agent_executor.ainvoke({"messages": messages})
            response = result["output"]
            return {
                **state,
                "messages": state["messages"] + [AIMessage(content=response)]
            }
            
        except Exception as e:
            logger.error(f"Calendar inquiry error: {e}")
            return {
                **state,
                "messages": state["messages"] + [AIMessage(content="I'd be happy to check your calendar for you! Which day or time period would you like me to look at?")]
            }
    
    async def _availability_inquiry_node(self, state: SimpleState) -> SimpleState:
        """Handle availability inquiry intent."""
        logger.info("🕐 Availability Inquiry Node")
        
        # Get latest message content
        latest_message_content = ""
        if state["messages"]:
            latest_message = state["messages"][-1]
            if isinstance(latest_message, HumanMessage):
                latest_message_content = latest_message.content
            elif hasattr(latest_message, 'content'):
                latest_message_content = latest_message.content
        
        # Create a specific prompt for availability inquiries
        availability_prompt = f"""
        The user wants to know about their availability or free time. Their message: "{latest_message_content}"
        
        As their executive assistant, help them by:
        1. Understanding what time period they want to check for availability
        2. If the timeframe is clear, use check_availability_tool to find their free time
        3. Present available time slots in an organized, easy-to-read format
        4. If the time period isn't specific enough, ask naturally for more details
        
        Be helpful and conversational. For example:
        "I'd be happy to check your availability! When are you looking to schedule something?"
        
        When showing availability, present it clearly with specific time slots and durations.
        If there are no available slots, suggest alternative times or days.
        """
        
        messages = [HumanMessage(content=availability_prompt)]
        agent_executor = AgentExecutor(agent=self.execution_decider, tools=tools, verbose=True)
        
        try:
            result = await agent_executor.ainvoke({"messages": messages})
            response = result["output"]
            return {
                **state,
                "messages": state["messages"] + [AIMessage(content=response)]
            }
            
        except Exception as e:
            logger.error(f"Availability inquiry error: {e}")
            return {
                **state,
                "messages": state["messages"] + [AIMessage(content="I'd be happy to check your availability! When are you looking to schedule something?")]
            }
    
    async def _meeting_modification_node(self, state: SimpleState) -> SimpleState:
        """Handle meeting modification intent."""
        logger.info("✏️ Meeting Modification Node")
        
        response = "I'd be happy to help you modify that meeting! While I'm setting up the ability to make changes directly, I can definitely help coordinate the update for you. Could you tell me which meeting you'd like to change and what you'd like to adjust - the time, attendees, or something else?"
        
        return {
            **state,
            "messages": state["messages"] + [AIMessage(content=response)]
        }
    
    async def _time_question_node(self, state: SimpleState) -> SimpleState:
        """Handle time question intent."""
        logger.info("🕒 Time Question Node")
        
        # Get latest message content
        latest_message_content = ""
        if state["messages"]:
            latest_message = state["messages"][-1]
            if isinstance(latest_message, HumanMessage):
                latest_message_content = latest_message.content
            elif hasattr(latest_message, 'content'):
                latest_message_content = latest_message.content
        
        # Create a specific prompt for time questions
        time_prompt = f"""
        The user has a time or timezone question. Their message: "{latest_message_content}"
        
        As their executive assistant, help them by:
        1. If they want to know the current time, use get_current_time_tool
        2. If they need timezone information or clarification, provide helpful details
        3. Be conversational and provide context they might find useful
        
        Be helpful and informative. Provide the time information they need in a clear, friendly way.
        """
        
        messages = [HumanMessage(content=time_prompt)]
        agent_executor = AgentExecutor(agent=self.execution_decider, tools=tools, verbose=True)
        
        try:
            result = await agent_executor.ainvoke({"messages": messages})
            response = result["output"]
            return {
                **state,
                "messages": state["messages"] + [AIMessage(content=response)]
            }
            
        except Exception as e:
            logger.error(f"Time question error: {e}")
            return {
                **state,
                "messages": state["messages"] + [AIMessage(content="I'd be happy to help with time-related questions! What would you like to know?")]
            }
    

    
    async def _general_conversation_node(self, state: SimpleState) -> SimpleState:
        """Handle general conversation intent."""
        logger.info("💬 General Conversation Node")
        
        response = "Hello! I'm Athena, your executive assistant. I'm here to help you manage your calendar, schedule meetings, check availability, and keep your day organized. What can I help you with today?"
        
        return {
            **state,
            "messages": state["messages"] + [AIMessage(content=response)]
        }
    
    # Routing functions
    def _route_by_intent(self, state: SimpleState) -> str:
        """Route based on classified intent."""
        intent = state.get("message_intent", "general_conversation")
        logger.info(f"Routing by intent: {intent}")
        return intent
    
    def _route_from_execution_decider(self, state: SimpleState) -> str:
        """Route from execution decider based on context."""
        # For now, just end after execution decider
        # In a more complex implementation, you could analyze the response
        # and route to specific nodes for additional processing
        return "end"
    
    async def process_message(self, contact_id: str, message: str, user_id: str, 
                            user_details: Dict[str, Any] = None, access_token: str = None) -> Dict[str, Any]:
        """Process an incoming message through the simplified workflow."""
        try:
            logger.info("🚀 Starting Simple LangGraph execution")
            
            # Set up calendar service if needed
            if access_token:
                try:
                    set_calendar_service(access_token)
                except Exception as e:
                    logger.error(f"Error setting up calendar service: {str(e)}")
            
            # Initialize simple state with proper message types
            initial_state = SimpleState(
                messages=[HumanMessage(content=message)],
                user_id=user_id,
                contact_id=contact_id,
                message_intent=None,
                metadata={
                    "user_details": user_details,
                    "access_token": access_token is not None,
                    "timestamp": datetime.now().isoformat()
                }
            )
            
            # Execute the graph
            final_state = await self.graph.ainvoke(initial_state)
            
            # Extract response from the last AI message
            messages = final_state.get("messages", [])
            response = "I apologize, but I couldn't process your request."
            
            if messages:
                # Find the last AI message
                for message in reversed(messages):
                    if isinstance(message, AIMessage):
                        response = message.content
                        break
            
            return {
                "response": response,
                "tools_used": [],  # Could be enhanced to track tool usage
                "intent": final_state.get("message_intent", "unknown"),
                "user_id": user_id,
                "contact_id": contact_id,
                "extracted_info": {
                    "simplified_agent": True,
                    "message_count": len(messages)
                }
            }
            
        except Exception as e:
            logger.error(f"Error in Simple LangGraph execution: {str(e)}")
            return {
                "response": "I apologize, but I encountered an error processing your request.",
                "tools_used": [],
                "intent": "error",
                "user_id": user_id,
                "contact_id": contact_id,
                "extracted_info": None
            }

# Agent factory functions
def create_simple_agent(openai_api_key: str = None, model_name: str = None, temperature: float = None) -> SimpleAthenaAgent:
    """Create and return a SimpleAthenaAgent instance."""
    
    # Use config defaults if not provided
    api_key = openai_api_key or Config.OPENAI_API_KEY
    model = model_name or Config.LLM_MODEL
    temp = temperature if temperature is not None else Config.LLM_TEMPERATURE
    
    if not api_key:
        raise ValueError("OpenAI API key is required")
    
    return SimpleAthenaAgent(
        openai_api_key=api_key,
        model_name=model,
        temperature=temp
    )

# Global agent instance
_simple_agent_instance: Optional[SimpleAthenaAgent] = None

def get_simple_agent() -> SimpleAthenaAgent:
    """Get the global simple agent instance, creating it if necessary."""
    global _simple_agent_instance
    
    if _simple_agent_instance is None:
        _simple_agent_instance = create_simple_agent()
        logger.info("Global Simple LangGraph agent instance created")
    
    return _simple_agent_instance

def reset_simple_agent():
    """Reset the global simple agent instance."""
    global _simple_agent_instance
    _simple_agent_instance = None
    logger.info("Global Simple LangGraph agent instance reset")

# Export graph for LangGraph Studio
def _create_simple_studio_graph():
    """Create a compiled graph for LangGraph Studio."""
    agent = get_simple_agent()
    return agent._create_graph()

# Export the compiled graph for LangGraph Studio
graph = _create_simple_studio_graph() 