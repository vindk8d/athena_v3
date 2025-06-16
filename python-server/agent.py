from typing import Dict, Any, List, Optional, Literal, TypedDict, Annotated
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, AIMessage, SystemMessage
from langchain.tools import Tool
from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
import logging
from datetime import datetime, timedelta
import pytz
import json
import re
from pydantic import BaseModel, Field

from memory import MemoryManager, memory_manager
from tools import calendar_tools, set_calendar_service, set_llm_instance
from config import Config

logger = logging.getLogger(__name__)

# State Schema for the LangGraph
class AthenaState(TypedDict):
    """State schema for Athena's reasoning graph."""
    # Core message flow
    messages: Annotated[List[Any], add_messages]
    
    # User and context information
    user_id: str
    contact_id: str
    user_details: Optional[Dict[str, Any]]
    user_timezone: str
    current_datetime: str
    
    # Intent and understanding
    intent: Optional[str]
    intent_confidence: Optional[float]
    is_calendar_related: Optional[bool]
    
    # Planning and execution
    plan: Optional[List[Dict[str, Any]]]
    plan_complete: Optional[bool]
    required_info: Optional[List[str]]
    missing_info: Optional[List[str]]
    
    # Time processing
    temporal_references: Optional[List[str]]
    normalized_times: Optional[Dict[str, str]]
    time_parsing_errors: Optional[List[str]]
    
    # Clarification flow
    needs_clarification: Optional[bool]
    clarification_question: Optional[str]
    clarification_context: Optional[Dict[str, Any]]
    
    # Tool execution
    tools_to_execute: Optional[List[Dict[str, Any]]]
    tool_results: Optional[List[Dict[str, Any]]]
    execution_errors: Optional[List[str]]
    
    # Response generation
    final_response: Optional[str]
    response_metadata: Optional[Dict[str, Any]]
    
    # Graph flow control
    next_node: Optional[str]
    conversation_complete: Optional[bool]

# Enhanced system prompt for LangGraph-based agent
EXECUTIVE_ASSISTANT_SYSTEM_PROMPT = """You are Athena, a professional executive assistant AI that acts on behalf of your authenticated user to coordinate meetings and manage schedules with their colleagues.

## Core Identity and Role:
- You are the **executive assistant** of the authenticated user in the system
- When interacting with colleagues, you represent your user professionally
- You coordinate meeting scheduling on behalf of your user, not for the person you're talking to
- You have full authority to manage your user's calendar and schedule meetings
- The system serves a single user - all contacts are colleagues of this user

## Communication Style:
- **Professional but Approachable**: Maintain executive assistant professionalism
- **Clear and Efficient**: Be direct and efficient in communications
- **Representative Authority**: Speak with the authority of representing your user
- **Helpful and Solution-Oriented**: Focus on finding solutions and scheduling meetings
- **Natural and Friendly**: Avoid sounding robotic or repetitive

## Core Responsibilities:
- **Represent Your User**: Act as the professional representative of the authenticated user
- **Calendar Management**: Manage your user's calendar, check their availability, and schedule meetings on their behalf
- **Colleague Coordination**: Coordinate with colleagues who want to meet with your user
- **Professional Communication**: Maintain professional executive assistant tone and behavior
- **Meeting Facilitation**: Handle all aspects of meeting coordination for your user

## Time Handling Guidelines:
- Always work in the user's timezone (provided in context)
- Use the current date and time as the reference point for all scheduling
- When someone mentions "tomorrow", calculate it from the current date
- When someone mentions "next week", calculate it from the current date
- Default meeting duration is 30 minutes if not specified
- Calculate end_datetime = start_datetime + duration
- Use ISO format with timezone for all datetime parameters

Remember: You are ALWAYS acting on behalf of your authenticated user, coordinating with their colleagues to schedule meetings with your user. This is a single-user system - all interactions are in the context of this one user and their colleagues.
"""

class IntentClassifier:
    """Classifies user intents with detailed analysis."""
    
    @staticmethod
    async def classify_intent(llm, message: str, chat_history: List, current_datetime: datetime, user_timezone: str) -> Dict[str, Any]:
        """Classify the intent of the user's message with detailed analysis."""
        
        # Prepare conversation context
        conversation_parts = []
        if chat_history:
            for msg in chat_history[-5:]:  # Last 5 messages for context
                if hasattr(msg, 'content'):
                    conversation_parts.append(msg.content)
        conversation_parts.append(message)
        conversation_text = "\n".join(conversation_parts)
        
        # Intent classification prompt
        classification_prompt = f"""Analyze this conversation and classify the primary intent. Return ONLY valid JSON:

Conversation:
{conversation_text}

Current context:
- Date: {current_datetime.strftime('%Y-%m-%d')}
- Time: {current_datetime.strftime('%H:%M')}
- Timezone: {user_timezone}

Classify the intent and extract information:

Intent categories:
- meeting_request: Requesting to schedule a meeting/appointment
- availability_inquiry: Asking about availability or free time
- meeting_modification: Wanting to cancel, reschedule, or change existing meeting
- calendar_inquiry: Asking about calendar, events, or schedule
- timezone_question: Asking about timezone information
- greeting: Greeting or social pleasantries
- general_conversation: General conversation or unclear intent

Extract additional information:
- is_calendar_related: Boolean - does this require calendar operations?
- urgency_level: "low", "medium", or "high"
- temporal_references: List of time references mentioned (e.g., ["tomorrow", "2 PM"])
- has_specific_time: Boolean - does the query mention a specific time?
- has_duration: Boolean - is meeting duration mentioned?
- confidence: Your confidence in this classification (0.0-1.0)

Response format:
{{"intent": "meeting_request", "is_calendar_related": true, "urgency_level": "medium", "temporal_references": ["tomorrow", "2 PM"], "has_specific_time": true, "has_duration": false, "confidence": 0.9}}"""

        try:
            response = await llm.ainvoke([HumanMessage(content=classification_prompt)])
            
            # Parse LLM response
            response_text = response.content.strip()
            if not response_text.startswith('{'):
                start = response_text.find('{')
                end = response_text.rfind('}') + 1
                if start >= 0 and end > start:
                    response_text = response_text[start:end]
            
            intent_data = json.loads(response_text)
            
            logger.info(f"🧠 Intent classification: {intent_data}")
            return intent_data
            
        except Exception as e:
            logger.error(f"❌ Intent classification failed: {e}")
            # Fallback to simple classification
            return {
                "intent": "general_conversation",
                "is_calendar_related": False,
                "urgency_level": "low",
                "temporal_references": [],
                "has_specific_time": False,
                "has_duration": False,
                "confidence": 0.3
            }

class PlannerAgent:
    """Creates high-level execution plans and manages information requirements."""
    
    @staticmethod
    async def create_plan(llm, intent: str, message: str, current_datetime: datetime, user_timezone: str) -> Dict[str, Any]:
        """Create a high-level execution plan based on the intent."""
        
        planning_prompt = f"""Create a high-level execution plan for this request. Return ONLY valid JSON:

Intent: {intent}
Message: "{message}"
Current datetime: {current_datetime.strftime('%Y-%m-%d %H:%M %Z')}
User timezone: {user_timezone}

Based on the intent, create a plan with required information and steps:

For meeting_request:
- Required info: title, start_datetime, end_datetime, (optional: attendee_emails, description, location)
- Steps: ["check_availability", "create_event"]

For availability_inquiry:
- Required info: query (natural language)
- Steps: ["check_availability"]

For calendar_inquiry:
- Required info: start_datetime, end_datetime
- Steps: ["get_events"]

For meeting_modification:
- Required info: event_id, modification_type, new_details
- Steps: ["get_events", "update_event"]

Extract what information is available and what's missing:

Response format:
{{"plan": [{{"step": "check_availability", "tool": "check_availability", "required_params": ["query"], "optional_params": ["duration_minutes"]}}, {{"step": "create_event", "tool": "create_event", "required_params": ["title", "start_datetime", "end_datetime"], "optional_params": ["attendee_emails", "description", "location"]}}], "required_info": ["title", "start_datetime", "end_datetime"], "available_info": ["title"], "missing_info": ["start_datetime", "end_datetime"], "plan_complete": false, "estimated_steps": 2}}"""

        try:
            response = await llm.ainvoke([HumanMessage(content=planning_prompt)])
            
            # Parse LLM response
            response_text = response.content.strip()
            if not response_text.startswith('{'):
                start = response_text.find('{')
                end = response_text.rfind('}') + 1
                if start >= 0 and end > start:
                    response_text = response_text[start:end]
            
            plan_data = json.loads(response_text)
            
            logger.info(f"🧠 Plan created: {plan_data}")
            return plan_data
            
        except Exception as e:
            logger.error(f"❌ Plan creation failed: {e}")
            # Fallback to simple plan
            return {
                "plan": [{"step": "respond", "tool": "none", "required_params": [], "optional_params": []}],
                "required_info": [],
                "available_info": [],
                "missing_info": [],
                "plan_complete": True,
                "estimated_steps": 1
            }

class TimeNormalizer:
    """Normalizes time references to required tool formats."""
    
    @staticmethod
    async def normalize_times(llm, temporal_references: List[str], message: str, current_datetime: datetime, user_timezone: str) -> Dict[str, Any]:
        """Normalize temporal references to ISO format with timezone."""
        
        if not temporal_references:
            return {"normalized_times": {}, "parsing_errors": []}
        
        normalization_prompt = f"""Normalize these time references to ISO format with timezone. Return ONLY valid JSON:

Time references: {temporal_references}
Message: "{message}"
Current datetime: {current_datetime.strftime('%Y-%m-%d %H:%M %Z')}
User timezone: {user_timezone}

Rules:
- "tomorrow" → {(current_datetime + timedelta(days=1)).strftime('%Y-%m-%d')}
- "next week" → Start of next week Monday
- "2 PM" → Today at 14:00 or specified date at 14:00
- "Monday" → Next Monday
- Default time is 9:00 AM if no time specified
- Default duration is 30 minutes
- Output in ISO format with timezone

For each time reference, provide:
- start_datetime: ISO format with timezone
- end_datetime: ISO format with timezone (start + 30 min default)
- confidence: 0.0-1.0

Response format:
{{"normalized_times": {{"tomorrow": {{"start_datetime": "2024-01-16T09:00:00+08:00", "end_datetime": "2024-01-16T09:30:00+08:00", "confidence": 0.9}}}}, "parsing_errors": []}}"""

        try:
            response = await llm.ainvoke([HumanMessage(content=normalization_prompt)])
            
            # Parse LLM response
            response_text = response.content.strip()
            if not response_text.startswith('{'):
                start = response_text.find('{')
                end = response_text.rfind('}') + 1
                if start >= 0 and end > start:
                    response_text = response_text[start:end]
            
            normalized_data = json.loads(response_text)
            
            logger.info(f"🧠 Time normalization: {normalized_data}")
            return normalized_data
            
        except Exception as e:
            logger.error(f"❌ Time normalization failed: {e}")
            return {"normalized_times": {}, "parsing_errors": [str(e)]}

class ClarificationAgent:
    """Generates clarification questions when information is missing."""
    
    @staticmethod
    async def generate_clarification(llm, missing_info: List[str], intent: str, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a clarification question for missing information."""
        
        clarification_prompt = f"""Generate a natural clarification question to gather missing information. Return ONLY valid JSON:

Intent: {intent}
Original message: "{message}"
Missing information: {missing_info}
Context: {context}

Generate ONE specific question that asks for the most critical missing information.
Be natural, friendly, and professional as an executive assistant.

Focus on:
- If missing date/time: Ask for preferred date and time
- If missing title: Ask for meeting purpose
- If missing duration: Ask for meeting length
- If missing attendees: This is usually just the colleague asking

Examples:
- "What date and time would work best for you?"
- "What's the purpose of this meeting?"
- "How long should the meeting be?"

Response format:
{{"clarification_question": "What date and time would work best for you?", "clarification_type": "datetime", "priority": "high", "context_needed": ["start_datetime", "end_datetime"]}}"""

        try:
            response = await llm.ainvoke([HumanMessage(content=clarification_prompt)])
            
            # Parse LLM response
            response_text = response.content.strip()
            if not response_text.startswith('{'):
                start = response_text.find('{')
                end = response_text.rfind('}') + 1
                if start >= 0 and end > start:
                    response_text = response_text[start:end]
            
            clarification_data = json.loads(response_text)
            
            logger.info(f"🧠 Clarification generated: {clarification_data}")
            return clarification_data
                
        except Exception as e:
            logger.error(f"❌ Clarification generation failed: {e}")
            return {
                "clarification_question": "Could you provide more details about what you need?",
                "clarification_type": "general",
                "priority": "medium",
                "context_needed": missing_info
            }

class AthenaLangGraphAgent:
    """Main LangGraph-based Athena agent with sophisticated reasoning."""
    
    def __init__(self, openai_api_key: str, model_name: str = "gpt-3.5-turbo", temperature: float = 0.3):
        """Initialize the LangGraph agent."""
        self.llm = ChatOpenAI(
            temperature=temperature,
            model_name=model_name,
            openai_api_key=openai_api_key
        )
        
        # Set LLM instance for tools
        set_llm_instance(self.llm)
        
        # Initialize the graph
        self.graph = self._create_graph()
        
        logger.info("Athena LangGraph Agent initialized successfully")
    
    def _create_graph(self) -> StateGraph:
        """Create the LangGraph workflow."""
        # Initialize the graph
        workflow = StateGraph(AthenaState)
        
        # Add nodes
        workflow.add_node("input_interpreter", self._input_interpreter_node)
        workflow.add_node("planner", self._planner_node)
        workflow.add_node("time_normalizer", self._time_normalizer_node)
        workflow.add_node("clarification", self._clarification_node)
        workflow.add_node("execution", self._execution_node)
        workflow.add_node("response_generator", self._response_generator_node)
        
        # Define edges
        workflow.set_entry_point("input_interpreter")
        
        # From input interpreter, branch based on intent
        workflow.add_conditional_edges(
            "input_interpreter",
            self._should_use_calendar_tools,
            {
                "calendar": "planner",
                "direct_response": "response_generator"
            }
        )
        
        # From planner, branch based on next steps needed
        workflow.add_conditional_edges(
            "planner",
            self._planner_decision,
            {
                "needs_time_normalization": "time_normalizer",
                "needs_clarification": "clarification",
                "ready_for_execution": "execution",
                "direct_response": "response_generator"
            }
        )
        
        # From time normalizer to clarification
        workflow.add_edge("time_normalizer", "clarification")
        
        # From clarification to execution
        workflow.add_edge("clarification", "execution")
        
        # From execution to response generator
        workflow.add_edge("execution", "response_generator")
        
        # End the graph at response generator
        workflow.set_finish_point("response_generator")
        
        return workflow.compile()
    
    async def _input_interpreter_node(self, state: AthenaState) -> AthenaState:
        """Interpret the input and classify intent."""
        logger.info("🔍 Input Interpreter Node")
        
        # Get the latest message
        latest_message = state["messages"][-1].content if state["messages"] else ""
        
        # Get current datetime in user's timezone
        user_tz = pytz.timezone(state["user_timezone"])
        current_datetime = datetime.now(user_tz)
        
        # Classify intent
        intent_data = await IntentClassifier.classify_intent(
            self.llm, latest_message, state["messages"], current_datetime, state["user_timezone"]
        )
        
        # Update state
        state["intent"] = intent_data["intent"]
        state["intent_confidence"] = intent_data["confidence"]
        state["is_calendar_related"] = intent_data["is_calendar_related"]
        state["temporal_references"] = intent_data["temporal_references"]
        state["current_datetime"] = current_datetime.isoformat()
        
        logger.info(f"Intent classified: {intent_data['intent']} (calendar: {intent_data['is_calendar_related']})")
        
        return state
    
    async def _planner_node(self, state: AthenaState) -> AthenaState:
        """Create execution plan and assess information completeness."""
        logger.info("📋 Planner Node")
        
        # Get the latest message
        latest_message = state["messages"][-1].content if state["messages"] else ""
        current_datetime = datetime.fromisoformat(state["current_datetime"])
        
        # Create plan
        plan_data = await PlannerAgent.create_plan(
            self.llm, state["intent"], latest_message, current_datetime, state["user_timezone"]
        )
        
        # Update state
        state["plan"] = plan_data["plan"]
        state["plan_complete"] = plan_data["plan_complete"]
        state["required_info"] = plan_data["required_info"]
        state["missing_info"] = plan_data["missing_info"]
        
        # Determine next step
        if state["temporal_references"] and not state.get("normalized_times"):
            state["next_node"] = "time_normalizer"
        elif state["missing_info"]:
            state["next_node"] = "clarification"
        elif state["plan_complete"]:
            state["next_node"] = "execution"
        else:
            state["next_node"] = "response_generator"
        
        logger.info(f"Plan created: {len(state['plan'])} steps, complete: {state['plan_complete']}")
        
        return state
    
    async def _time_normalizer_node(self, state: AthenaState) -> AthenaState:
        """Normalize time references to tool-compatible formats."""
        logger.info("⏰ Time Normalizer Node")
        
        if not state["temporal_references"]:
            return state
        
        # Get the latest message
        latest_message = state["messages"][-1].content if state["messages"] else ""
        current_datetime = datetime.fromisoformat(state["current_datetime"])
        
        # Normalize times
        normalized_data = await TimeNormalizer.normalize_times(
            self.llm, state["temporal_references"], latest_message, current_datetime, state["user_timezone"]
        )
        
        # Update state
        state["normalized_times"] = normalized_data["normalized_times"]
        state["time_parsing_errors"] = normalized_data["parsing_errors"]
        
        logger.info(f"Normalized {len(state['normalized_times'])} time references")
        
        return state
    
    async def _clarification_node(self, state: AthenaState) -> AthenaState:
        """Generate clarification questions for missing information."""
        logger.info("❓ Clarification Node")
        
        if not state["missing_info"]:
            return state
        
        # Get the latest message
        latest_message = state["messages"][-1].content if state["messages"] else ""
        
        # Generate clarification
        clarification_data = await ClarificationAgent.generate_clarification(
            self.llm, state["missing_info"], state["intent"], latest_message, {}
        )
        
        # Update state
        state["needs_clarification"] = True
        state["clarification_question"] = clarification_data["clarification_question"]
        state["clarification_context"] = clarification_data
        state["final_response"] = clarification_data["clarification_question"]
        
        logger.info(f"Clarification needed: {clarification_data['clarification_question']}")
        
        return state
    
    async def _execution_node(self, state: AthenaState) -> AthenaState:
        """Execute the planned tools."""
        logger.info("⚡ Execution Node")
        
        if not state["plan"]:
            return state
        
        tool_results = []
        execution_errors = []
        
        # Execute each step in the plan
        for step in state["plan"]:
            try:
                tool_name = step["tool"]
                if tool_name == "none":
                    continue
                
                # Find the tool
                tool = next((t for t in calendar_tools if t.name == tool_name), None)
                if not tool:
                    execution_errors.append(f"Tool {tool_name} not found")
                    continue
                
                # Prepare tool input based on normalized times and available info
                tool_input = self._prepare_tool_input(step, state)
                
                # Execute the tool
                if hasattr(tool, '_arun'):
                    result = await tool._arun(**tool_input)
                else:
                    result = tool._run(**tool_input)
                
                tool_results.append({
                    "tool": tool_name,
                    "input": tool_input,
                    "output": result,
                    "success": True
                })
                
                logger.info(f"Tool {tool_name} executed successfully")
                
            except Exception as e:
                execution_errors.append(f"Tool {step['tool']} failed: {str(e)}")
                tool_results.append({
                    "tool": step["tool"],
                    "input": tool_input if 'tool_input' in locals() else {},
                    "output": str(e),
                    "success": False
                })
                logger.error(f"Tool execution error: {e}")
        
        # Update state
        state["tool_results"] = tool_results
        state["execution_errors"] = execution_errors
        
        logger.info(f"Executed {len(tool_results)} tools with {len(execution_errors)} errors")
        
        return state
    
    async def _response_generator_node(self, state: AthenaState) -> AthenaState:
        """Generate the final response based on the state."""
        try:
            # Get intent and user details
            intent = state.get("intent", "")
            user_details = state.get("user_details", {})
            user_name = self._get_user_name(user_details)
            
            # Handle direct response intents
            if intent in ["greeting", "general_conversation"]:
                greeting_responses = {
                    "greeting": f"Hello! I'm {user_name}'s executive assistant. How can I help you coordinate with {user_name}?",
                    "general_conversation": f"I'm {user_name}'s executive assistant. I can help you schedule meetings and coordinate with {user_name}. What would you like to do?"
                }
                state["final_response"] = greeting_responses.get(intent, greeting_responses["general_conversation"])
                return state
            
            # Handle calendar-related responses
            if state.get("is_calendar_related", False):
                if state.get("needs_clarification"):
                    state["final_response"] = state.get("clarification_question", "Could you please provide more details about your request?")
                elif state.get("execution_errors"):
                    error_msg = state.get("execution_errors")[0]
                    state["final_response"] = f"I encountered an error while processing your request: {error_msg}"
                else:
                    state["final_response"] = self._generate_response_from_tools(state)
            
            # Fallback response
            if not state.get("final_response"):
                state["final_response"] = f"I'm {user_name}'s executive assistant. I can help you schedule meetings and coordinate with {user_name}. What would you like to do?"
            
            return state
            
        except Exception as e:
            logger.error(f"Error in response generator: {str(e)}")
            state["final_response"] = "I apologize, but I encountered an error processing your request."
            return state
    
    def _should_use_calendar_tools(self, state: AthenaState) -> Literal["calendar", "direct_response"]:
        """Determine if we should use calendar tools based on intent."""
        # Get intent information
        intent = state.get("intent", "")
        is_calendar_related = state.get("is_calendar_related", False)
        
        # List of intents that should bypass calendar tools
        direct_response_intents = ["greeting", "general_conversation", "error"]
        
        # If intent is in direct_response_intents or not calendar related, go straight to response
        if intent in direct_response_intents or not is_calendar_related:
            logger.info(f"Direct response path chosen for intent: {intent}")
            return "direct_response"
        
        logger.info(f"Calendar path chosen for intent: {intent}")
        return "calendar"
    
    def _planner_decision(self, state: AthenaState) -> Literal["needs_time_normalization", "needs_clarification", "ready_for_execution", "direct_response"]:
        """Decide the next step from planner."""
        if state.get("temporal_references") and not state.get("normalized_times"):
            return "needs_time_normalization"
        elif state.get("missing_info"):
            return "needs_clarification"
        elif state.get("plan_complete", False):
            return "ready_for_execution"
        else:
            return "direct_response"
    
    def _prepare_tool_input(self, step: Dict[str, Any], state: AthenaState) -> Dict[str, Any]:
        """Prepare input for tool execution."""
        tool_input = {}
        
        # Get the latest message for query-based tools
        latest_message = state["messages"][-1].content if state["messages"] else ""
        
        if step["tool"] == "check_availability":
            tool_input["query"] = latest_message
            tool_input["duration_minutes"] = 30  # Default
            
        elif step["tool"] == "create_event":
            # Extract from normalized times or use defaults
            if state.get("normalized_times"):
                first_time = list(state["normalized_times"].values())[0]
                tool_input["start_datetime"] = first_time["start_datetime"]
                tool_input["end_datetime"] = first_time["end_datetime"]
            
            tool_input["title"] = "Meeting"  # Default title
            tool_input["attendee_emails"] = []  # Will be set by the system
            
        elif step["tool"] == "get_events":
            current_datetime = datetime.fromisoformat(state["current_datetime"])
            start_of_day = current_datetime.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day = current_datetime.replace(hour=23, minute=59, second=59, microsecond=999999)
            
            tool_input["start_datetime"] = start_of_day.isoformat()
            tool_input["end_datetime"] = end_of_day.isoformat()
        
        return tool_input
    
    def _generate_response_from_tools(self, state: AthenaState) -> str:
        """Generate response from tool execution results."""
        if not state.get("tool_results"):
            return "I wasn't able to complete that request."
        
        successful_results = [r for r in state["tool_results"] if r["success"]]
        
        if not successful_results:
            return "I encountered some issues while processing your request. Please try again."
        
        # Generate response based on the tools used
        responses = []
        for result in successful_results:
            responses.append(result["output"])
        
        return "\n".join(responses)
    
    def _get_user_name(self, user_details: Dict[str, Any]) -> str:
        """Get user's name from details."""
        if not user_details:
            return "your user"
        
        first_name = user_details.get('first_name', '')
        last_name = user_details.get('last_name', '')
        
        if first_name and last_name:
            return f"{first_name} {last_name}"
        elif first_name:
            return first_name
        else:
            return "your user"
    
    async def process_message(self, contact_id: str, message: str, user_id: str, user_details: Dict[str, Any] = None, access_token: str = None) -> Dict[str, Any]:
        """Process an incoming message through the LangGraph workflow."""
        try:
            logger.info("🚀 Starting LangGraph execution")
            
            # Set up calendar service if needed
            if access_token:
                try:
                    set_calendar_service(access_token)
                except Exception as e:
                    logger.error(f"Error setting up calendar service: {str(e)}")
                    # Continue execution without calendar service
            
            # Get user timezone with fallback
            user_timezone = 'UTC'
            if user_details and isinstance(user_details, dict):
                user_timezone = user_details.get('timezone', user_details.get('default_timezone', 'UTC'))
            
            # Get current time in user's timezone
            current_datetime = datetime.now(pytz.timezone(user_timezone))
            
            # Initialize state
            initial_state = AthenaState(
                messages=[HumanMessage(content=message)],
                user_id=user_id,
                contact_id=contact_id,
                user_details=user_details if isinstance(user_details, dict) else {},
                user_timezone=user_timezone,
                current_datetime=current_datetime.isoformat(),
                intent=None,
                intent_confidence=None,
                is_calendar_related=None,
                plan=None,
                plan_complete=None,
                required_info=None,
                missing_info=None,
                temporal_references=None,
                normalized_times=None,
                time_parsing_errors=None,
                needs_clarification=None,
                clarification_question=None,
                clarification_context=None,
                tools_to_execute=None,
                tool_results=None,
                execution_errors=None,
                final_response=None,
                response_metadata=None,
                next_node=None,
                conversation_complete=None
            )
            
            # Create and compile the graph
            workflow = self._create_graph()
            
            # Execute the graph
            final_state = await workflow.ainvoke(initial_state)
            
            # Debug logging
            logger.info(f"Final state type: {type(final_state)}")
            logger.info(f"Final state content: {final_state}")
            
            # Extract response with proper fallbacks
            response = "I apologize, but I encountered an error processing your request."
            tools_used = []
            intent = "error"
            
            if isinstance(final_state, dict):
                response = final_state.get("final_response", response)
                tools_used = final_state.get("tool_results", tools_used) or []
                intent = final_state.get("intent", intent)
            elif hasattr(final_state, "__dict__"):
                # Handle case where final_state is an object with attributes
                state_dict = final_state.__dict__
                response = state_dict.get("final_response", response)
                tools_used = state_dict.get("tool_results", tools_used) or []
                intent = state_dict.get("intent", intent)
            
            # Ensure tools_used is always a list
            if tools_used is None:
                tools_used = []
            
            # Debug logging
            logger.info(f"Extracted response: {response}")
            logger.info(f"Extracted tools_used: {tools_used}")
            logger.info(f"Extracted intent: {intent}")
            
            return {
                "response": response,
                "tools_used": tools_used,
                "intent": intent,
                "user_id": user_id,
                "contact_id": contact_id,
                "extracted_info": {
                    "current_datetime": current_datetime.isoformat(),
                    "user_timezone": user_timezone,
                    "langgraph_execution": True
                }
            }
            
        except Exception as e:
            logger.error(f"Error in LangGraph execution: {str(e)}")
            return {
                "response": "I apologize, but I encountered an error processing your request.",
                "tools_used": [],
                "intent": "error",
                "user_id": user_id,
                "contact_id": contact_id,
                "extracted_info": None
            }

# Agent factory function
def create_agent(openai_api_key: str = None, model_name: str = None, temperature: float = None) -> AthenaLangGraphAgent:
    """Create and return an AthenaLangGraphAgent instance."""
    
    # Use config defaults if not provided
    api_key = openai_api_key or Config.OPENAI_API_KEY
    model = model_name or Config.LLM_MODEL
    temp = temperature if temperature is not None else Config.LLM_TEMPERATURE
    
    if not api_key:
        raise ValueError("OpenAI API key is required")
    
    return AthenaLangGraphAgent(
        openai_api_key=api_key,
        model_name=model,
        temperature=temp
    )

# Global agent instance
_agent_instance: Optional[AthenaLangGraphAgent] = None

def get_agent() -> AthenaLangGraphAgent:
    """Get the global agent instance, creating it if necessary."""
    global _agent_instance
    
    if _agent_instance is None:
        _agent_instance = create_agent()
        logger.info("Global LangGraph agent instance created")
    
    return _agent_instance

def reset_agent():
    """Reset the global agent instance."""
    global _agent_instance
    _agent_instance = None
    logger.info("Global LangGraph agent instance reset")
