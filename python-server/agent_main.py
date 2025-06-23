from typing import Dict, Any, List, Optional, Literal, TypedDict, Annotated, Union
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, AIMessage, SystemMessage, BaseMessage
from langchain.tools import tool
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain import hub
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.base import BaseCheckpointSaver, CheckpointTuple
import logging
from datetime import datetime, timedelta, timezone, date
import pytz
import json
import os
import re
import asyncio
import uuid
from pydantic import BaseModel, Field
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request
from supabase import create_client, Client
# Removed complex serialization imports - now using simple JSON serialization
from google_auth_oauthlib.flow import Flow
import pickle
import base64

from config import Config

logger = logging.getLogger(__name__)
# Global LLM instance for availability mode detection
_llm_instance = None

# Summarization configuration
SUMMARY_THRESHOLD = 10  # Summarize when history exceeds 10 messages
MESSAGES_TO_RETAIN = 6  # Always keep the last 6 messages as-is

# ==================== CONSOLIDATED LLM-BASED TIME PARSING FUNCTIONS ====================

async def parse_time_with_llm(time_reference: str, current_timezone: str, llm_instance, duration_minutes: int = None) -> tuple:
    """Universal LLM-based time parser for any time reference.
    
    Args:
        time_reference: Natural language time like "tomorrow at 2 PM", "next monday", "10 AM"
        current_timezone: User's timezone
        llm_instance: LLM instance for parsing
        duration_minutes: Duration in minutes for events (optional). If None, returns broader time periods.
    
    Returns:
        Tuple of (start_datetime_iso, end_datetime_iso) or (None, None) if parsing fails
    """
    try:
        current_datetime = datetime.now(pytz.timezone(current_timezone))
        
        # Different behavior based on whether we want a specific duration or broader period
        if duration_minutes is not None:
            # Event scheduling mode - specific duration
            behavior_instructions = f"""
SCHEDULING MODE (Duration: {duration_minutes} minutes):
1. Convert relative references (tomorrow, next week, monday) to actual dates
2. For specific times (10 AM, 2:30 PM), use exact time
3. For time periods (morning, afternoon), use reasonable defaults:
   - morning: 9:00 AM
   - afternoon: 2:00 PM  
   - evening: 6:00 PM
4. For single time points, create start time + duration ({duration_minutes} minutes)
5. For date-only references, use 9:00 AM as default start time
6. NEVER return times in the past (if time has passed today, use tomorrow)"""
        else:
            # Availability checking mode - broader periods
            behavior_instructions = """
AVAILABILITY MODE (Broad time periods):
1. Convert relative references (tomorrow, next week, monday) to actual dates
2. For specific days, use business hours (8:00 AM - 6:00 PM)
3. For "next week", use the entire work week (Monday-Friday, 8:00 AM - 6:00 PM each day)
4. For "tomorrow", use full business day (8:00 AM - 6:00 PM)
5. For specific times like "tomorrow afternoon", use appropriate ranges (2:00 PM - 5:00 PM)
6. NEVER return times in the past"""
        
        time_parsing_prompt = f"""You are a precise time parsing expert. Convert the given time reference to exact ISO datetime strings.

Current time: {current_datetime.strftime('%Y-%m-%d %H:%M:%S %Z')}
Timezone: {current_timezone}
Time reference: "{time_reference}"

{behavior_instructions}

7. Always return times in the specified timezone with proper offset

Return ONLY a JSON object with this exact format:
{{
    "start_time": "YYYY-MM-DDTHH:MM:SS+HH:MM",
    "end_time": "YYYY-MM-DDTHH:MM:SS+HH:MM",
    "explanation": "Brief explanation of the conversion"
}}"""

        response = await llm_instance.ainvoke([HumanMessage(content=time_parsing_prompt)])
        response_text = response.content.strip()
        
        # Extract JSON from response
        json_start = response_text.find('{')
        json_end = response_text.rfind('}') + 1
        if json_start != -1 and json_end > json_start:
            json_str = response_text[json_start:json_end]
            parsed = json.loads(json_str)
            
            start_time = parsed.get('start_time')
            end_time = parsed.get('end_time')
            explanation = parsed.get('explanation', '')
            
            if start_time and end_time:
                mode = f"duration={duration_minutes}min" if duration_minutes else "availability"
                logger.info(f"LLM time parsing ({mode}): '{time_reference}' -> {start_time} to {end_time} ({explanation})")
                return start_time, end_time
        
        logger.warning(f"Could not extract valid JSON from LLM time parsing response: {response_text}")
        return None, None
        
    except Exception as e:
        logger.error(f"Error in LLM-based time parsing: {e}")
        return None, None

# ==================== TIME PARSING TOOLS ====================

@tool
async def parse_time_reference_tool(time_reference: str, duration_minutes: int = None) -> str:
    """Parse natural language time reference into ISO datetime strings using LLM.
    
    This universal tool handles both specific event scheduling and broader availability periods.
    
    Args:
        time_reference: Natural language time like "tomorrow at 2 PM", "next monday", "next week"
        duration_minutes: Duration in minutes for events (optional). 
                         If provided: creates specific time slots (e.g., 30min meeting)
                         If None: creates broader periods (e.g., business hours for availability)
    
    Returns:
        Formatted string with start and end times, or error message
    """
    try:
        # Get user context for timezone
        try:
            user_id = get_current_user_id()
            user_timezone = get_user_timezone(user_id)
        except ValueError:
            # Demo mode fallback
            user_timezone = "UTC"
        
        # Get LLM instance
        llm = get_llm_instance()
        if not llm:
            return "❌ LLM not available for time parsing"
        
        # Parse using unified LLM function
        start_time, end_time = await parse_time_with_llm(time_reference, user_timezone, llm, duration_minutes)
        
        if start_time and end_time:
            if duration_minutes:
                return f"✅ Parsed event time: {start_time} to {end_time} ({duration_minutes}min)"
            else:
                return f"✅ Parsed time period: {start_time} to {end_time}"
        else:
            return f"❌ Could not parse time reference: {time_reference}"
            
    except Exception as e:
        logger.error(f"Error in parse_time_reference_tool: {e}")
        return f"❌ Error parsing time reference: {str(e)}"

@tool
async def parse_time_period_tool(time_period: str) -> str:
    """Parse natural language time period into ISO datetime range using LLM.
    
    This tool is useful for availability checks and finding time slots.
    
    Args:
        time_period: Natural language period like "tomorrow", "next week", "monday"
    
    Returns:
        Formatted string with start and end times, or error message
    """
    try:
        # Get user context for timezone
        try:
            user_id = get_current_user_id()
            user_timezone = get_user_timezone(user_id)
        except ValueError:
            # Demo mode fallback
            user_timezone = "UTC"
        
        # Get LLM instance
        llm = get_llm_instance()
        if not llm:
            return "❌ LLM not available for time parsing"
        
        # Parse using LLM
        start_time, end_time = await parse_time_with_llm(time_period, user_timezone, llm)
        
        if start_time and end_time:
            return f"✅ Parsed period: {start_time} to {end_time}"
        else:
            return f"❌ Could not parse time period: {time_period}"
            
    except Exception as e:
        logger.error(f"Error in parse_time_period_tool: {e}")
        return f"❌ Error parsing time period: {str(e)}"

def find_available_slots(busy_times: List[Dict], start_datetime: datetime, end_datetime: datetime, slot_duration_minutes: int = 30) -> List[Dict[str, str]]:
    """Find available time slots within a time range, avoiding busy periods."""
    try:
        available_slots = []
        busy_periods = []
        for busy in busy_times:
            try:
                busy_start = datetime.fromisoformat(busy['start'].replace('Z', '+00:00'))
                busy_end = datetime.fromisoformat(busy['end'].replace('Z', '+00:00'))
                busy_periods.append((busy_start, busy_end))
            except Exception as e:
                logger.warning(f"Could not parse busy time: {busy}, error: {e}")
                continue
        busy_periods.sort(key=lambda x: x[0])
        current_time = start_datetime
        slot_duration = timedelta(minutes=slot_duration_minutes)
        while current_time + slot_duration <= end_datetime:
            slot_end = current_time + slot_duration
            is_free = True
            for busy_start, busy_end in busy_periods:
                if not (slot_end <= busy_start or current_time >= busy_end):
                    is_free = False
                    break
            if is_free:
                available_slots.append({
                    'start': current_time.isoformat(),
                    'end': slot_end.isoformat(),
                    'duration_minutes': slot_duration_minutes
                })
            current_time += timedelta(minutes=30)
        return available_slots
    except Exception as e:
        logger.error(f"Error finding available slots: {e}")
        return []

def set_llm_instance(llm):
    """Set the global LLM instance for intelligent availability mode detection."""
    global _llm_instance
    _llm_instance = llm

def get_llm_instance():
    """Get the global LLM instance."""
    return _llm_instance

# Initialize Supabase client for database operations
def get_supabase_client():
    """Get a Supabase client instance."""
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    
    if not supabase_url or not supabase_key:
        logger.error(f"Supabase configuration missing - URL: {'✓' if supabase_url else '✗'}, Key: {'✓' if supabase_key else '✗'}")
        raise ValueError("Supabase URL and service role key are required")
    
    logger.debug(f"Creating Supabase client with URL: {supabase_url[:50]}...")
    return create_client(supabase_url, supabase_key)

def get_user_calendar_query_base(user_id: str, supabase_client):
    """Get base query for user calendars with to_include_in_check filter applied."""
    return supabase_client.table('calendar_list').select('*').eq('user_id', user_id).eq('calendar_type', 'google').eq('to_include_in_check', True)

def get_included_calendars(user_id: str) -> List[str]:
    """Get list of calendar IDs that should be included in availability checks, ordered by write access."""
    try:
        supabase = get_supabase_client()
        if not supabase:
            logger.error("Could not initialize Supabase client")
            return []
        
        # Get calendars with write access priority: primary first, then owner/writer, then others
        response = supabase.table('calendar_list').select('calendar_id, access_role, is_primary').eq('user_id', user_id).eq('calendar_type', 'google').eq('to_include_in_check', True).execute()
        
        if response.data:
            # Separate calendars by access level
            primary_calendars = []
            writable_calendars = []
            readonly_calendars = []
            
            for item in response.data:
                calendar_id = item['calendar_id']
                access_role = item.get('access_role', 'reader')
                is_primary = item.get('is_primary', False)
                
                if is_primary:
                    primary_calendars.append(calendar_id)
                elif access_role in ['owner', 'writer']:
                    writable_calendars.append(calendar_id)
                else:
                    readonly_calendars.append(calendar_id)
            
            # Return in priority order: primary first, then writable, then readonly
            calendar_ids = primary_calendars + writable_calendars + readonly_calendars
            logger.info(f"Found {len(calendar_ids)} included calendars for user {user_id} (primary: {len(primary_calendars)}, writable: {len(writable_calendars)}, readonly: {len(readonly_calendars)})")
            return calendar_ids
        else:
            logger.warning(f"No included calendars found for user {user_id}")
            return []
    except Exception as e:
        logger.error(f"Error fetching included calendars: {e}")
        return []

def get_user_timezone(user_id: str) -> str:
    """Get user's default timezone from user_details."""
    try:
        supabase = get_supabase_client()
        if not supabase:
            logger.error("Could not initialize Supabase client")
            return "UTC"
        
        response = supabase.table('user_details').select('default_timezone').eq('user_id', user_id).execute()
        
        if response.data and response.data[0].get('default_timezone'):
            return response.data[0]['default_timezone']
        return "UTC"
    except Exception as e:
        logger.error(f"Error fetching user timezone: {e}")
        return "UTC"

def get_calendar_timezone(user_id: str, calendar_id: str) -> str:
    """Get calendar's timezone from calendar_list."""
    try:
        supabase = get_supabase_client()
        if not supabase:
            logger.error("Could not initialize Supabase client")
            return "UTC"
        # Only get timezone for calendars that are included in checks
        response = supabase.table('calendar_list').select('timezone').eq('user_id', user_id).eq('calendar_id', calendar_id).eq('to_include_in_check', True).execute()
        if response.data and response.data[0].get('timezone'):
            return response.data[0]['timezone']
        return "UTC"
    except Exception as e:
        logger.error(f"Error fetching calendar timezone: {e}")
        return "UTC"

# Define CalendarService class for interacting with Google Calendar API
class CalendarService:
    """Google Calendar API service wrapper."""
    
    def __init__(self, credentials: Credentials):
        """Initialize calendar service with OAuth tokens."""
        try:
            self.credentials = credentials
            self.service = build('calendar', 'v3', credentials=credentials)
            logger.info("Calendar service initialized successfully")
            
        except Exception as e:
            logger.error(f"Error initializing calendar service: {e}")
            raise
    
    def refresh_token_if_needed(self):
        """Refresh the access token if it's expired or about to expire."""
        try:
            if not self.credentials.valid:
                if self.credentials.refresh_token and self.credentials.has_expired():
                    try:
                        self.credentials.refresh(Request())
                        self.service = build('calendar', 'v3', credentials=self.credentials)
                        logger.info("Access token refreshed successfully")
                        return {
                            'access_token': self.credentials.token,
                            'refresh_token': self.credentials.refresh_token,
                            'expires_at': self.credentials.expiry.isoformat() if self.credentials.expiry else None
                        }
                    except Exception as e:
                        logger.error(f"Error refreshing token: {e}")
                        raise
            return None
        except Exception as e:
            logger.error(f"Error refreshing token: {e}")
            raise
    
    def list_calendars(self) -> List[Dict[str, Any]]:
        """List all calendars for the authenticated user."""
        try:
            calendar_list = self.service.calendarList().list().execute()
            calendars = []
            
            for calendar_item in calendar_list.get('items', []):
                calendars.append({
                    'id': calendar_item['id'],
                    'summary': calendar_item.get('summary', ''),
                    'description': calendar_item.get('description', ''),
                    'timezone': calendar_item.get('timeZone', 'UTC'),
                    'primary': calendar_item.get('primary', False),
                    'access_role': calendar_item.get('accessRole', 'reader')
                })
            
            return calendars
            
        except HttpError as e:
            logger.error(f"HTTP error listing calendars: {e}")
            raise
        except Exception as e:
            logger.error(f"Error listing calendars: {e}")
            raise
    
    def get_events(self, calendar_id: str, start_date: str, end_date: str, timezone: str = "UTC") -> List[Dict[str, Any]]:
        """Get events from a calendar within a date range."""
        try:
            start_time = f"{start_date}T00:00:00.000000Z"
            end_time = f"{end_date}T23:59:59.999999Z"
            
            events_result = self.service.events().list(
                calendarId=calendar_id,
                timeMin=start_time,
                timeMax=end_time,
                singleEvents=True,
                orderBy='startTime',
                timeZone=timezone
            ).execute()
            
            events = []
            for event in events_result.get('items', []):
                start = event.get('start', {})
                end = event.get('end', {})
                
                events.append({
                    'id': event['id'],
                    'summary': event.get('summary', 'No title'),
                    'description': event.get('description', ''),
                    'start': start.get('dateTime', start.get('date')),
                    'end': end.get('dateTime', end.get('date')),
                    'location': event.get('location', ''),
                    'attendees': [att.get('email') for att in event.get('attendees', [])],
                    'status': event.get('status', 'confirmed'),
                    'html_link': event.get('htmlLink', '')
                })
            
            return events
            
        except HttpError as e:
            logger.error(f"HTTP error getting events: {e}")
            raise
        except Exception as e:
            logger.error(f"Error getting events: {e}")
            raise
    
    def check_availability(self, start_datetime: str, end_datetime: str, calendar_ids: List[str]) -> Dict[str, Any]:
        """Check availability across multiple calendars."""
        try:
            body = {
                'timeMin': start_datetime,
                'timeMax': end_datetime,
                'items': [{'id': cal_id} for cal_id in calendar_ids]
            }
            
            freebusy_result = self.service.freebusy().query(body=body).execute()
            
            availability = {
                'time_period': {
                    'start': start_datetime,
                    'end': end_datetime
                },
                'calendars': {},
                'is_free': True,
                'conflicts': []
            }
            
            for calendar_id in calendar_ids:
                calendar_busy = freebusy_result.get('calendars', {}).get(calendar_id, {})
                busy_times = calendar_busy.get('busy', [])
                
                availability['calendars'][calendar_id] = {
                    'busy_times': busy_times,
                    'is_free': len(busy_times) == 0
                }
                
                if busy_times:
                    availability['is_free'] = False
                    availability['conflicts'].extend(busy_times)
            
            return availability
            
        except HttpError as e:
            logger.error(f"HTTP error checking availability: {e}")
            raise
        except Exception as e:
            logger.error(f"Error checking availability: {e}")
            raise
    
    def create_event(self, calendar_id: str, title: str, description: str, 
                    start_datetime: str, end_datetime: str, timezone: str = "UTC",
                    attendees: List[str] = None, location: str = "") -> Dict[str, Any]:
        """Create a new calendar event."""
        try:
            event_body = {
                'summary': title,
                'description': description,
                'start': {
                    'dateTime': start_datetime,
                    'timeZone': timezone,
                },
                'end': {
                    'dateTime': end_datetime,
                    'timeZone': timezone,
                },
                'location': location,
            }
            
            # Filter out empty/invalid email addresses
            if attendees:
                valid_emails = [email.strip() for email in attendees if email and email.strip()]
                if valid_emails:
                    event_body['attendees'] = [{'email': email} for email in valid_emails]
            
            event = self.service.events().insert(
                calendarId=calendar_id,
                body=event_body
            ).execute()
            
            return {
                'id': event['id'],
                'summary': event.get('summary'),
                'start': event.get('start', {}).get('dateTime'),
                'end': event.get('end', {}).get('dateTime'),
                'html_link': event.get('htmlLink'),
                'status': event.get('status')
            }
            
        except HttpError as e:
            logger.error(f"HTTP error creating event: {e}")
            raise
        except Exception as e:
            logger.error(f"Error creating event: {e}")
            raise

# Global calendar service instance and user context
_calendar_service: Optional[CalendarService] = None
_current_user_id: Optional[str] = None

def set_calendar_service(access_token: str, refresh_token: str = None, user_id: str = None, llm_instance=None):
    """Set up the calendar service with the provided credentials."""
    try:
        client_id = os.getenv('GOOGLE_CLIENT_ID')
        client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
        token_uri = 'https://oauth2.googleapis.com/token'
        
        if not client_id or not client_secret:
            logger.error("Google OAuth2 credentials not found in environment variables")
            raise ValueError("Google OAuth2 credentials not configured")
        
        creds = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri=token_uri,
            client_id=client_id,
            client_secret=client_secret,
            scopes=['https://www.googleapis.com/auth/calendar']
        )
        
        global _calendar_service
        _calendar_service = CalendarService(creds)
        
        if llm_instance:
            set_llm_instance(llm_instance)
        
        if user_id:
            set_current_user_id(user_id)
        
        logger.info("Calendar service initialized successfully")
        
    except Exception as e:
        logger.error(f"Error setting up calendar service: {str(e)}")
        raise

def set_current_user_id(user_id: str):
    """Set the current user ID for tool context."""
    global _current_user_id
    _current_user_id = user_id

def get_calendar_service() -> CalendarService:
    """Get the global calendar service instance."""
    if _calendar_service is None:
        raise ValueError("Calendar service not initialized. Call set_calendar_service first.")
    return _calendar_service

def get_current_user_id() -> str:
    """Get the current user ID."""
    if _current_user_id is None:
        raise ValueError("User ID not set. Call set_current_user_id first.")
    return _current_user_id

# State Schema
class SimpleState(TypedDict):
    """Enhanced state schema for Athena agent with checkpointing and summarization."""
    messages: Annotated[List[BaseMessage], add_messages]
    conversation_summary: Optional[str]  # For conversation summarization
    user_id: str
    contact_id: str
    message_intent: Optional[str]
    metadata: Optional[Dict[str, Any]]

# Tool definitions using @tool decorator with integrated calendar service
@tool
async def check_availability_tool(query: str, duration_minutes: int = 30) -> str:
    """Check calendar availability based on natural language query.
    
    This tool intelligently checks availability across all configured calendars.
    It can handle both specific time checks and time slot inquiries.
    
    Args:
        query: Natural language description of when you want to check availability
               Examples: "tomorrow at 2 PM", "next week", "is 3 PM free on Monday?"
        duration_minutes: Expected meeting duration in minutes (default 30)
    """
    try:
        # Check if we have user context (for production) or if we're in demo mode (LangGraph Studio)
        try:
            user_id = get_current_user_id()
            user_timezone = get_user_timezone(user_id)
            calendar_ids = get_included_calendars(user_id)
            
            if not calendar_ids:
                return "No calendars configured for availability checking. Please configure calendars in the web interface."
            
            # Get current datetime in user's timezone
            current_datetime = datetime.now(pytz.timezone(user_timezone))
            
            # Get LLM instance for direct time parsing
            llm = get_llm_instance()
            if not llm:
                logger.warning("LLM instance not available for time parsing")
                return "I'm having trouble understanding the time reference. Could you please provide a more specific date and time?"
            
            # Use consolidated LLM-based time parsing
            start_datetime_str, end_datetime_str = await parse_time_with_llm(query, user_timezone, llm, duration_minutes)
            
            if not start_datetime_str or not end_datetime_str:
                logger.warning("LLM time parsing failed")
                return "I'm having trouble understanding the time reference. Could you please provide a more specific date and time?"
            
            # Convert string times to datetime objects
            start_datetime = datetime.fromisoformat(start_datetime_str.replace('Z', '+00:00'))
            end_datetime = datetime.fromisoformat(end_datetime_str.replace('Z', '+00:00'))
            
            # Check if the requested time is in the past
            if start_datetime < current_datetime:
                logger.warning(f"Attempted to check availability for past time: {start_datetime}")
                return f"❌ Cannot check availability for past time. The requested time ({start_datetime.strftime('%Y-%m-%d %H:%M %Z')}) has already passed."
            
            service = get_calendar_service()
            availability = service.check_availability(start_datetime.isoformat(), end_datetime.isoformat(), calendar_ids)
            
            if availability['is_free']:
                return f"✅ Time slot {start_datetime.strftime('%Y-%m-%d %H:%M')} to {end_datetime.strftime('%H:%M %Z')} is FREE across all configured calendars"
            else:
                result = f"❌ Time slot {start_datetime.strftime('%Y-%m-%d %H:%M')} to {end_datetime.strftime('%H:%M %Z')} has CONFLICTS:\n"
                for conflict in availability['conflicts']:
                    conflict_start = datetime.fromisoformat(conflict['start'].replace('Z', '+00:00'))
                    conflict_end = datetime.fromisoformat(conflict['end'].replace('Z', '+00:00'))
                    result += f"- Busy from {conflict_start.strftime('%H:%M')} to {conflict_end.strftime('%H:%M')}\n"
                return result
                
        except ValueError as e:
            if "User ID not set" in str(e) or "Calendar service not initialized" in str(e):
                # Demo mode for LangGraph Studio
                logger.info("Running in demo mode - no user context available")
                
                # Use UTC for demo mode
                current_datetime = datetime.now(pytz.UTC)
                
                # Demo response - simulate availability check
                if "tomorrow" in query.lower() or "next" in query.lower():
                    return f"✅ Demo mode: The requested time appears to be FREE\n\nNote: This is a demo response. In production, this would check your actual Google Calendar."
                else:
                    return f"❌ Demo mode: The requested time has CONFLICTS\n\nNote: This is a demo response. In production, this would check your actual Google Calendar."
            else:
                raise
            
    except Exception as e:
        logger.error(f"Error in check_availability_tool: {e}")
        return f"I had trouble checking availability. Please try again or provide more specific time details."

@tool
async def create_event_tool(title: str, time_reference: str, duration_minutes: int = 30,
                           attendee_emails: List[str] = None, description: str = "", 
                           location: str = "") -> str:
    """Create a new calendar event on the user's primary calendar.
    
    This tool creates calendar events with full Google Calendar integration.
    
    Args:
        title: Meeting title (required)
        time_reference: Natural language time reference (e.g., "tomorrow at 2 PM", "next monday at 10 AM")
        duration_minutes: Duration in minutes (default: 30)
        attendee_emails: List of attendee email addresses (optional)
        description: Meeting description (optional)
        location: Meeting location (optional)
    """
    try:
        # Validate inputs
        if not title or not title.strip():
            return "❌ Meeting title is required"
        if not time_reference or not time_reference.strip():
            return "❌ Time reference is required"
        
        try:
            user_id = get_current_user_id()
            user_timezone = get_user_timezone(user_id)
            calendar_ids = get_included_calendars(user_id)
            
            if not calendar_ids:
                return "No calendars configured for creating events. Please configure calendars in the web interface."
            
            # Parse the time reference using LLM
            llm = get_llm_instance()
            if not llm:
                return "❌ LLM not available for time parsing"
            
            start_datetime, end_datetime = await parse_time_with_llm(time_reference, user_timezone, llm, duration_minutes)
            
            if not start_datetime or not end_datetime:
                return f"❌ Could not parse time reference: {time_reference}. Please provide a clearer time like 'tomorrow at 2 PM' or 'June 15 at 10:30 AM'"
            
            # Check if the start time is in the past
            start_dt = datetime.fromisoformat(start_datetime.replace('Z', '+00:00'))
            current_datetime = datetime.now(pytz.timezone(user_timezone))
            
            if start_dt < current_datetime:
                return f"❌ Cannot create event in the past: {start_datetime}"
            
            # Use the first configured calendar (usually primary) for creating events
            primary_calendar = calendar_ids[0]
            calendar_timezone = get_calendar_timezone(user_id, primary_calendar)
            
            service = get_calendar_service()
            
            # Filter out empty/invalid attendee emails before passing to service
            filtered_attendees = []
            if attendee_emails:
                filtered_attendees = [email.strip() for email in attendee_emails if email and email.strip()]
            
            try:
                event = service.create_event(
                    primary_calendar, title, description, start_datetime, 
                    end_datetime, calendar_timezone, filtered_attendees, location
                )
            except Exception as create_error:
                # If event creation fails on the primary calendar, try the next writable calendar
                error_msg = str(create_error)
                if "requiredAccessLevel" in error_msg or "403" in error_msg:
                    logger.warning(f"Cannot create event on calendar {primary_calendar}: {error_msg}")
                    
                    # Get supabase client for checking calendar access
                    supabase = get_supabase_client()
                    
                    # Try to find another writable calendar
                    for fallback_calendar in calendar_ids[1:]:
                        try:
                            # Check if this calendar has write access
                            calendar_info = supabase.table('calendar_list').select('access_role').eq('user_id', user_id).eq('calendar_id', fallback_calendar).eq('to_include_in_check', True).execute()
                            if calendar_info.data and calendar_info.data[0].get('access_role') in ['owner', 'writer']:
                                logger.info(f"Trying fallback calendar: {fallback_calendar}")
                                fallback_timezone = get_calendar_timezone(user_id, fallback_calendar)
                                event = service.create_event(
                                    fallback_calendar, title, description, start_datetime, 
                                    end_datetime, fallback_timezone, filtered_attendees, location
                                )
                                logger.info(f"Successfully created event on fallback calendar: {fallback_calendar}")
                                break
                        except Exception as fallback_error:
                            logger.warning(f"Fallback calendar {fallback_calendar} also failed: {fallback_error}")
                            continue
                    else:
                        # No writable calendar found
                        return f"❌ Unable to create event: No writable calendars available. Please check your calendar permissions in the web interface."
                else:
                    # Re-raise other types of errors
                    raise create_error
            
            result = f"✅ Meeting scheduled successfully on your calendar!\n"
            result += f"Title: {event['summary']}\n"
            result += f"Time: {event['start']} to {event['end']}\n"
            result += f"Event ID: {event['id']}\n"
            if filtered_attendees:
                result += f"Attendees: {', '.join(filtered_attendees)}\n"
            if location:
                result += f"Location: {location}\n"
            if event.get('html_link'):
                result += f"Calendar link: {event['html_link']}\n"
            
            return result
            
        except ValueError as e:
            if "User ID not set" in str(e) or "Calendar service not initialized" in str(e):
                # Demo mode for LangGraph Studio
                logger.info("Running in demo mode - no user context available")
                
                # Parse time reference using LLM for demo mode
                llm = get_llm_instance()
                if not llm:
                    return "❌ LLM not available for time parsing"
                
                try:
                    start_datetime, end_datetime = await parse_time_with_llm(time_reference, "UTC", llm, duration_minutes)
                    if not start_datetime or not end_datetime:
                        return f"❌ Could not parse time reference: {time_reference}. Please provide a clearer time like 'tomorrow at 2 PM' or 'June 15 at 10:30 AM'"
                except Exception as parse_error:
                    return f"❌ Error parsing time reference: {parse_error}"
                
                # Validate the datetime format
                try:
                    start_dt = datetime.fromisoformat(start_datetime.replace('Z', '+00:00'))
                    end_dt = datetime.fromisoformat(end_datetime.replace('Z', '+00:00'))
                except ValueError:
                    return "❌ Invalid datetime format. Please use ISO format (e.g., 2024-01-15T10:00:00+00:00)"
                
                # Demo response
                result = f"✅ Demo mode: Meeting would be scheduled successfully!\n"
                result += f"Title: {title}\n"
                result += f"Time: {start_datetime} to {end_datetime}\n"
                result += f"Event ID: demo_event_12345\n"
                if attendee_emails:
                    result += f"Attendees: {', '.join(attendee_emails)}\n"
                if location:
                    result += f"Location: {location}\n"
                result += f"\nNote: This is a demo response. In production, this would create the event in your actual Google Calendar."
                
                return result
            else:
                raise
        
    except Exception as e:
        logger.error(f"Error in create_event_tool: {e}")
        return f"I had trouble creating the event. Please check the details and try again."

@tool
def get_events_tool(start_datetime: str, end_datetime: str) -> str:
    """Get calendar events in a specific date range from all configured calendars.
    
    This tool retrieves events from all calendars that are configured for the user.
    
    Args:
        start_datetime: Start of date range in ISO format with timezone (required)
        end_datetime: End of date range in ISO format with timezone (required)
    """
    try:
        if not start_datetime or not end_datetime:
            return "❌ Start and end dates are required"
        
        try:
            user_id = get_current_user_id()
            calendar_ids = get_included_calendars(user_id)
            
            if not calendar_ids:
                return "No calendars configured for checking events. Please configure calendars in the web interface."
            
            service = get_calendar_service()
            all_events = []
            
            # Get events from all included calendars
            for calendar_id in calendar_ids:
                try:
                    # Convert datetime to date for the API call
                    start_date = start_datetime.split('T')[0]
                    end_date = end_datetime.split('T')[0]
                    events = service.get_events(calendar_id, start_date, end_date)
                    all_events.extend(events)
                except Exception as e:
                    logger.warning(f"Error getting events from calendar {calendar_id}: {e}")
            
            if not all_events:
                return f"No events found from {start_datetime} to {end_datetime}"
            
            # Sort events by start time
            all_events.sort(key=lambda x: x['start'])
            
            result = f"Events from {start_datetime} to {end_datetime}:\n"
            for event in all_events:
                result += f"- {event['summary']} ({event['start']} - {event['end']})\n"
                if event['location']:
                    result += f"  Location: {event['location']}\n"
                if event['attendees']:
                    result += f"  Attendees: {', '.join(event['attendees'])}\n"
            
            return result
            
        except ValueError as e:
            if "User ID not set" in str(e) or "Calendar service not initialized" in str(e):
                # Demo mode for LangGraph Studio
                logger.info("Running in demo mode - no user context available")
                
                # Demo response
                result = f"Demo mode: Events from {start_datetime} to {end_datetime}:\n"
                result += f"- Team Standup (2024-01-15T09:00:00Z - 2024-01-15T09:30:00Z)\n"
                result += f"  Location: Conference Room A\n"
                result += f"- Client Meeting (2024-01-15T14:00:00Z - 2024-01-15T15:00:00Z)\n"
                result += f"  Attendees: client@example.com\n"
                result += f"\nNote: This is a demo response. In production, this would show your actual Google Calendar events."
                
                return result
            else:
                raise
        
    except Exception as e:
        logger.error(f"Error in get_events_tool: {e}")
        return f"I had trouble retrieving calendar events. Please try again."

@tool
async def get_current_time_tool(timezone: str = None) -> str:
    """Get current date and time in user's timezone or specified timezone.
    
    This tool provides current time information for timezone-aware operations.
    If no timezone is specified, it will automatically use the user's default timezone
    from their calendar configuration.
    
    Args:
        timezone: Timezone (e.g., 'UTC', 'US/Pacific', 'Europe/London'). If None, uses user's default timezone.
    """
    try:
        # Try to get user's timezone if not specified
        if timezone is None:
            try:
                user_id = get_current_user_id()
                timezone = get_user_timezone(user_id)
                logger.info(f"Using user's default timezone: {timezone}")
            except ValueError as e:
                if "User ID not set" in str(e) or "Calendar service not initialized" in str(e):
                    # Demo mode for LangGraph Studio
                    logger.info("Running in demo mode - using UTC as default timezone")
                    timezone = "UTC"
                else:
                    logger.error(f"Error getting user timezone: {e}")
                    timezone = "UTC"
        
        tz = pytz.timezone(timezone)
        current_time = datetime.now(tz)
        return f"Current time in {timezone}: {current_time.strftime('%Y-%m-%d %H:%M:%S %Z')}"
    except Exception as e:
        logger.error(f"Error in get_current_time_tool: {e}")
        return f"I had trouble getting the current time for timezone {timezone}."

@tool
def list_calendars_tool() -> str:
    """List all calendars available to the user.
    
    This tool shows all calendars that the user has access to, including their IDs,
    names, timezones, and access levels.
    """
    try:
        try:
            service = get_calendar_service()
            calendars = service.list_calendars()
            
            if not calendars:
                return "No calendars found."
            
            # Format the response
            calendar_list = []
            for cal in calendars:
                calendar_list.append(
                    f"• {cal['summary']} ({cal['id']})\n"
                    f"  - Timezone: {cal['timezone']}\n"
                    f"  - Access: {cal['access_role']}\n"
                    f"  - Primary: {'Yes' if cal['primary'] else 'No'}"
                )
            
            return "Available calendars:\n" + "\n\n".join(calendar_list)
            
        except ValueError as e:
            if "Calendar service not initialized" in str(e):
                # Demo mode for LangGraph Studio
                logger.info("Running in demo mode - no calendar service available")
                
                result = "Demo mode: Available calendars:\n\n"
                result += "• Primary Calendar (primary@example.com)\n"
                result += "  - Timezone: UTC\n"
                result += "  - Access: owner\n"
                result += "  - Primary: Yes\n\n"
                result += "• Work Calendar (work@company.com)\n"
                result += "  - Timezone: US/Pacific\n"
                result += "  - Access: writer\n"
                result += "  - Primary: No\n\n"
                result += "Note: This is a demo response. In production, this would show your actual Google Calendar list."
                
                return result
            else:
                raise
        
    except Exception as e:
        logger.error(f"Error listing calendars: {e}")
        return f"Error listing calendars: {str(e)}"

@tool
def modify_event_tool(event_id: str, calendar_id: str = None, title: str = None, 
                     start_datetime: str = None, end_datetime: str = None,
                     attendee_emails: List[str] = None, description: str = None, 
                     location: str = None) -> str:
    """Modify an existing calendar event.
    Only provide the parameters you want to change - others will remain unchanged.
    """
    try:
        if not event_id:
            return "❌ Event ID is required for modification"
        
        try:
            user_id = get_current_user_id()
            calendar_ids = get_included_calendars(user_id)
            if not calendar_ids:
                return "No calendars configured. Please configure calendars in the web interface."
            target_calendar = calendar_id or calendar_ids[0]
            service = get_calendar_service()
            try:
                current_event = service.service.events().get(
                    calendarId=target_calendar, eventId=event_id
                ).execute()
            except HttpError as e:
                if e.resp.status == 404:
                    return f"❌ Event with ID '{event_id}' not found in calendar '{target_calendar}'"
                else:
                    raise
            update_body = {}
            if title is not None:
                update_body['summary'] = title
            if start_datetime is not None:
                update_body['start'] = {
                    'dateTime': start_datetime,
                    'timeZone': current_event.get('start', {}).get('timeZone', 'UTC')
                }
            if end_datetime is not None:
                update_body['end'] = {
                    'dateTime': end_datetime,
                    'timeZone': current_event.get('end', {}).get('timeZone', 'UTC')
                }
            if description is not None:
                update_body['description'] = description
            if location is not None:
                update_body['location'] = location
            if attendee_emails is not None:
                # Filter out empty/invalid attendee emails
                valid_emails = [email.strip() for email in attendee_emails if email and email.strip()]
                update_body['attendees'] = [{'email': email} for email in valid_emails]
            if not update_body:
                return f"Current event details:\nTitle: {current_event.get('summary', 'No title')}\nStart: {current_event.get('start', {}).get('dateTime', 'No start time')}\nEnd: {current_event.get('end', {}).get('dateTime', 'No end time')}"
            updated_event = service.service.events().update(
                calendarId=target_calendar,
                eventId=event_id,
                body=update_body
            ).execute()
            result = f"✅ Event updated successfully!\n"
            result += f"Event ID: {updated_event['id']}\n"
            result += f"Title: {updated_event.get('summary', 'No title')}\n"
            result += f"Start: {updated_event.get('start', {}).get('dateTime', 'No start time')}\n"
            result += f"End: {updated_event.get('end', {}).get('dateTime', 'No end time')}\n"
            if updated_event.get('attendees'):
                attendees = [att.get('email') for att in updated_event['attendees']]
                result += f"Attendees: {', '.join(attendees)}\n"
            if updated_event.get('location'):
                result += f"Location: {updated_event['location']}\n"
            if updated_event.get('htmlLink'):
                result += f"Calendar link: {updated_event['htmlLink']}\n"
            return result
            
        except ValueError as e:
            if "User ID not set" in str(e) or "Calendar service not initialized" in str(e):
                # Demo mode for LangGraph Studio
                logger.info("Running in demo mode - no user context available")
                
                result = f"✅ Demo mode: Event would be updated successfully!\n"
                result += f"Event ID: {event_id}\n"
                if title:
                    result += f"Title: {title}\n"
                if start_datetime:
                    result += f"Start: {start_datetime}\n"
                if end_datetime:
                    result += f"End: {end_datetime}\n"
                if attendee_emails:
                    result += f"Attendees: {', '.join(attendee_emails)}\n"
                if location:
                    result += f"Location: {location}\n"
                if description:
                    result += f"Description: {description}\n"
                result += f"\nNote: This is a demo response. In production, this would modify the event in your actual Google Calendar."
                
                return result
            else:
                raise
                
    except Exception as e:
        logger.error(f"Error in modify_event_tool: {e}")
        return f"I had trouble modifying the event. Please check the event ID and try again."

@tool
def delete_event_tool(event_id: str, calendar_id: str = None) -> str:
    """Delete a calendar event.
    This tool permanently removes an event from the calendar.
    """
    try:
        if not event_id:
            return "❌ Event ID is required for deletion"
        
        try:
            user_id = get_current_user_id()
            calendar_ids = get_included_calendars(user_id)
            if not calendar_ids:
                return "No calendars configured. Please configure calendars in the web interface."
            target_calendar = calendar_id or calendar_ids[0]
            service = get_calendar_service()
            try:
                current_event = service.service.events().get(
                    calendarId=target_calendar, eventId=event_id
                ).execute()
            except HttpError as e:
                if e.resp.status == 404:
                    return f"❌ Event with ID '{event_id}' not found in calendar '{target_calendar}'"
                else:
                    raise
            service.service.events().delete(
                calendarId=target_calendar,
                eventId=event_id
            ).execute()
            result = f"✅ Event deleted successfully!\n"
            result += f"Deleted event: {current_event.get('summary', 'No title')}\n"
            result += f"Event ID: {event_id}\n"
            return result
            
        except ValueError as e:
            if "User ID not set" in str(e) or "Calendar service not initialized" in str(e):
                # Demo mode for LangGraph Studio
                logger.info("Running in demo mode - no user context available")
                
                result = f"✅ Demo mode: Event would be deleted successfully!\n"
                result += f"Deleted event: Demo Meeting\n"
                result += f"Event ID: {event_id}\n"
                result += f"\nNote: This is a demo response. In production, this would delete the event from your actual Google Calendar."
                
                return result
            else:
                raise
                
    except Exception as e:
        logger.error(f"Error in delete_event_tool: {e}")
        return f"I had trouble deleting the event. Please check the event ID and try again."

@tool
async def find_available_slots_tool(start_datetime: str, end_datetime: str, duration_minutes: int = 30, busy_times: List[Dict] = None) -> str:
    """Find available time slots within a time range, avoiding busy periods.
    
    This tool helps find multiple available time slots when you have a list of busy times.
    Useful for finding free slots within a larger time period.
    
    Args:
        start_datetime: Start of time range in ISO format with timezone (required)
        end_datetime: End of time range in ISO format with timezone (required) 
        duration_minutes: Duration of each slot in minutes (default: 30)
        busy_times: List of busy time periods in format [{"start": "ISO_DATETIME", "end": "ISO_DATETIME"}] (optional)
    """
    try:
        # Parse datetime strings to datetime objects
        start_dt = datetime.fromisoformat(start_datetime.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(end_datetime.replace('Z', '+00:00'))
        
        # If no busy times provided, try to get them from Google Calendar
        if busy_times is None:
            try:
                user_id = get_current_user_id()
                calendar_ids = get_included_calendars(user_id)
                
                if calendar_ids:
                    service = get_calendar_service()
                    availability = service.check_availability(start_datetime, end_datetime, calendar_ids)
                    busy_times = availability.get('conflicts', [])
                    logger.info(f"Retrieved {len(busy_times)} busy periods from Google Calendar")
                else:
                    logger.warning("No calendars configured for availability checking")
                    busy_times = []
            except ValueError as e:
                if "User ID not set" in str(e) or "Calendar service not initialized" in str(e):
                    # Demo mode for LangGraph Studio
                    logger.info("Running in demo mode - using sample busy times")
                    busy_times = [
                        {"start": "2024-01-15T09:00:00Z", "end": "2024-01-15T10:00:00Z"},
                        {"start": "2024-01-15T14:00:00Z", "end": "2024-01-15T15:00:00Z"}
                    ]
                else:
                    logger.error(f"Error getting busy times from calendar: {e}")
                    busy_times = []
        
        # Use the helper function to find available slots
        available_slots = find_available_slots(busy_times, start_dt, end_dt, duration_minutes)
        
        if not available_slots:
            return f"❌ No {duration_minutes}-minute slots available from {start_datetime} to {end_datetime}"
        
        result = f"✅ Found {len(available_slots)} available {duration_minutes}-minute slots:\n"
        for i, slot in enumerate(available_slots[:10], 1):  # Limit to 10 slots for readability
            slot_start = datetime.fromisoformat(slot['start'])
            slot_end = datetime.fromisoformat(slot['end'])
            result += f"{i}. {slot_start.strftime('%Y-%m-%d %H:%M')} - {slot_end.strftime('%H:%M %Z')}\n"
        
        if len(available_slots) > 10:
            result += f"... and {len(available_slots) - 10} more slots available\n"
        
        return result
        
    except Exception as e:
        logger.error(f"Error in find_available_slots_tool: {e}")
        return f"I had trouble finding available slots. Please check the datetime format and try again."

@tool
async def get_available_slots_for_period_tool(time_period: str, duration_minutes: int = 30) -> str:
    """Get available time slots for a specific time period by checking Google Calendar.
    
    This tool automatically retrieves busy times from Google Calendar and finds available slots.
    It's a complete data retrieval function that handles the entire process.
    
    Args:
        time_period: Natural language time period (e.g., "tomorrow", "next week", "monday")
        duration_minutes: Duration of each slot in minutes (default: 30)
    """
    try:
        # Get user context
        try:
            user_id = get_current_user_id()
            user_timezone = get_user_timezone(user_id)
            calendar_ids = get_included_calendars(user_id)
            
            if not calendar_ids:
                return "No calendars configured for availability checking. Please configure calendars in the web interface."
            
            # Get current datetime in user's timezone
            current_datetime = datetime.now(pytz.timezone(user_timezone))
            
            # Get LLM instance for direct time parsing
            llm = get_llm_instance()
            if not llm:
                logger.warning("LLM instance not available for time parsing")
                return "I'm having trouble understanding the time period. Could you please provide a more specific time range?"
            
            # Use consolidated LLM-based time period parsing
            start_datetime_str, end_datetime_str = await parse_time_with_llm(time_period, user_timezone, llm)
            
            if not start_datetime_str or not end_datetime_str:
                logger.warning("LLM period parsing failed")
                return "I'm having trouble understanding the time period. Could you please provide a more specific time range?"
            
            # Convert string times to datetime objects
            start_datetime = datetime.fromisoformat(start_datetime_str.replace('Z', '+00:00'))
            end_datetime = datetime.fromisoformat(end_datetime_str.replace('Z', '+00:00'))
            
            # Check if the requested time is in the past
            if start_datetime < current_datetime:
                return f"❌ Cannot check availability for past time. The requested time ({start_datetime.strftime('%Y-%m-%d %H:%M %Z')}) has already passed."
            
            # Get busy times from Google Calendar
            service = get_calendar_service()
            availability = service.check_availability(start_datetime.isoformat(), end_datetime.isoformat(), calendar_ids)
            busy_times = availability.get('conflicts', [])
            
            logger.info(f"Retrieved {len(busy_times)} busy periods from Google Calendar for {time_period}")
            
            # Find available slots
            available_slots = find_available_slots(busy_times, start_datetime, end_datetime, duration_minutes)
            
            if not available_slots:
                return f"❌ No {duration_minutes}-minute slots available for {time_period}"
            
            result = f"✅ Available {duration_minutes}-minute slots for {time_period}:\n"
            for i, slot in enumerate(available_slots[:10], 1):  # Limit to 10 slots for readability
                slot_start = datetime.fromisoformat(slot['start'])
                slot_end = datetime.fromisoformat(slot['end'])
                result += f"{i}. {slot_start.strftime('%Y-%m-%d %H:%M')} - {slot_end.strftime('%H:%M %Z')}\n"
            
            if len(available_slots) > 10:
                result += f"... and {len(available_slots) - 10} more slots available\n"
            
            return result
        except ValueError as e:
            if "User ID not set" in str(e) or "Calendar service not initialized" in str(e):
                # Demo mode for LangGraph Studio
                logger.info("Running in demo mode - no user context available")
                
                # Use UTC for demo mode
                current_datetime = datetime.now(pytz.UTC)
                
                # Demo response with sample available slots
                result = f"✅ Demo mode: Available {duration_minutes}-minute slots for {time_period}:\n"
                result += f"1. {current_datetime.strftime('%Y-%m-%d')} 09:00 - 09:30 UTC\n"
                result += f"2. {current_datetime.strftime('%Y-%m-%d')} 10:00 - 10:30 UTC\n"
                result += f"3. {current_datetime.strftime('%Y-%m-%d')} 14:00 - 14:30 UTC\n"
                result += f"\nNote: This is a demo response. In production, this would check your actual Google Calendar."
                
                return result
            else:
                raise
        
    except Exception as e:
        logger.error(f"Error in get_available_slots_for_period_tool: {e}")
        return f"I had trouble finding available slots for {time_period}. Please try again or provide a more specific time period."



# Bundle tools - including new LLM-based time parsing tools
tools = [
    # Time parsing tools (LLM-based)
    parse_time_reference_tool, 
    # Calendar operation tools
    check_availability_tool, create_event_tool, get_events_tool, get_current_time_tool, 
    list_calendars_tool, modify_event_tool, delete_event_tool, find_available_slots_tool, 
    get_available_slots_for_period_tool
]

class SimpleSupabaseCheckpointer:
    """Simplified Supabase checkpointer that focuses only on essential conversation data.
    
    This stores only the critical data we need:
    - Messages (as simple JSON)
    - Conversation summary
    - Thread metadata
    
    Avoids complex serialization and focuses on reliability.
    """
    
    def __init__(self, debug_mode: bool = False):
        """Initialize the simple Supabase checkpointer."""
        self.supabase = None
        self.debug_mode = debug_mode
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize Supabase client."""
        try:
            self.supabase = get_supabase_client()
            logger.info("Simple Supabase checkpointer initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {e}")
            self.supabase = None
    
    def _make_json_safe(self, obj):
        """Recursively convert an object to be JSON serializable."""
        if obj is None:
            return None
        elif isinstance(obj, (str, int, float, bool)):
            return obj
        elif isinstance(obj, (datetime, date)):
            return obj.isoformat()
        elif isinstance(obj, list):
            return [self._make_json_safe(item) for item in obj]
        elif isinstance(obj, dict):
            return {str(key): self._make_json_safe(value) for key, value in obj.items()}
        elif hasattr(obj, '__dict__'):
            # For objects with __dict__, convert to dictionary
            return self._make_json_safe(obj.__dict__)
        else:
            # For any other type, convert to string
            return str(obj)
    
    def _serialize_messages(self, messages: List[BaseMessage]) -> List[dict]:
        """Convert LangChain messages to simple dictionaries."""
        if not messages:
            return []
        
        serialized = []
        for i, msg in enumerate(messages):
            try:
                # Handle different message types
                if isinstance(msg, HumanMessage):
                    msg_type = "human"
                elif isinstance(msg, AIMessage):
                    msg_type = "ai"
                elif isinstance(msg, SystemMessage):
                    msg_type = "system"
                else:
                    msg_type = "unknown"
                
                # Safely extract content
                content = ""
                if hasattr(msg, 'content'):
                    content = str(msg.content) if msg.content is not None else ""
                
                message_dict = {
                    "type": msg_type,
                    "content": content,
                    "timestamp": datetime.now().isoformat(),
                    "index": i
                }
                
                # Add any additional data if present
                if hasattr(msg, 'additional_kwargs') and msg.additional_kwargs:
                    message_dict["additional_kwargs"] = self._make_json_safe(msg.additional_kwargs)
                
                serialized.append(message_dict)
                
            except Exception as e:
                logger.warning(f"Error serializing message {i}: {e}")
                # Add a fallback message
                serialized.append({
                    "type": "unknown",
                    "content": f"[Error serializing message: {str(e)}]",
                    "timestamp": datetime.now().isoformat(),
                    "index": i
                })
        
        return serialized
    
    def _deserialize_messages(self, serialized_messages: List[dict]) -> List[BaseMessage]:
        """Convert simple dictionaries back to LangChain messages."""
        if not serialized_messages:
            return []
        
        messages = []
        for msg_data in serialized_messages:
            try:
                msg_type = msg_data.get("type", "unknown")
                content = msg_data.get("content", "")
                
                # Create the appropriate message type
                if msg_type == "human":
                    messages.append(HumanMessage(content=content))
                elif msg_type == "ai":
                    messages.append(AIMessage(content=content))
                elif msg_type == "system":
                    messages.append(SystemMessage(content=content))
                else:
                    # Default to HumanMessage for unknown types
                    messages.append(HumanMessage(content=content))
                    
            except Exception as e:
                logger.warning(f"Error deserializing message: {e}")
                # Add a fallback message
                messages.append(HumanMessage(content="[Error deserializing message]"))
        
        return messages
    
    def _extract_simple_state(self, checkpoint: dict) -> dict:
        """Extract only the essential data we need from the checkpoint."""
        if not checkpoint:
            return {}
        
        try:
            # Handle LangGraph checkpoint format
            channel_values = checkpoint.get("channel_values", {})
            
            # Extract messages - each field in SimpleState becomes its own channel
            messages = channel_values.get("messages", [])
            serialized_messages = self._serialize_messages(messages) if messages else []
            
            # Safely extract other data, ensuring everything is JSON serializable
            metadata = channel_values.get("metadata", {})
            if isinstance(metadata, dict):
                # Deep clean metadata to ensure JSON serializability
                safe_metadata = self._make_json_safe(metadata)
            else:
                safe_metadata = {}
            
            # Extract other essential data - these are separate channels in StateGraph
            simple_state = {
                "messages": serialized_messages,
                "conversation_summary": channel_values.get("conversation_summary"),
                "user_id": channel_values.get("user_id"),
                "contact_id": channel_values.get("contact_id"),
                "message_intent": channel_values.get("message_intent"),
                "metadata": safe_metadata,
                "timestamp": checkpoint.get("ts", datetime.now().isoformat()),
                "checkpoint_id": checkpoint.get("id"),
                "version": checkpoint.get("v", 1)
            }
            
            # Final validation - ensure everything is JSON serializable
            return self._make_json_safe(simple_state)
            
        except Exception as e:
            logger.error(f"Error extracting simple state: {e}")
            # Return minimal safe state
            return {
                "messages": [],
                "conversation_summary": None,
                "user_id": None,
                "contact_id": None,
                "message_intent": None,
                "metadata": {},
                "timestamp": datetime.now().isoformat(),
                "checkpoint_id": str(uuid.uuid4()),
                "version": 1
            }
    
    def _reconstruct_checkpoint(self, simple_state: dict) -> dict:
        """Reconstruct a full LangGraph-compatible checkpoint from simple state data."""
        if not simple_state:
            from collections import defaultdict
            return {
                "v": 1,
                "id": str(uuid.uuid4()),
                "ts": datetime.now().isoformat(),
                "channel_values": {},
                "channel_versions": defaultdict(int),
                "versions_seen": defaultdict(lambda: defaultdict(int)),
                "pending_sends": []
            }
        
        # Reconstruct messages
        serialized_messages = simple_state.get("messages", [])
        messages = self._deserialize_messages(serialized_messages)
        
        # Create the proper LangGraph checkpoint format
        from collections import defaultdict
        
        # For StateGraph, each field should be a separate channel
        # Map your simple state to individual channels
        channel_values = {
            "messages": messages,
            "conversation_summary": simple_state.get("conversation_summary"),
            "user_id": simple_state.get("user_id"),
            "contact_id": simple_state.get("contact_id"),
            "message_intent": simple_state.get("message_intent"),
            "metadata": simple_state.get("metadata", {})
        }
        
        # Generate versions for each channel using defaultdict(int) to match LangGraph expectations
        channel_versions = defaultdict(int)
        for channel_name, value in channel_values.items():
            if value is not None:
                channel_versions[channel_name] = 1
        
        return {
            "v": simple_state.get("version", 1),
            "id": simple_state.get("checkpoint_id", str(uuid.uuid4())),
            "ts": simple_state.get("timestamp", datetime.now().isoformat()),
            "channel_values": channel_values,
            "channel_versions": channel_versions,
            "versions_seen": defaultdict(lambda: defaultdict(int)),
            "pending_sends": []  # Critical field that was missing
        }
    
    async def aget_tuple(self, config: dict) -> Optional[CheckpointTuple]:
        """Get checkpoint tuple for a given config."""
        try:
            if not self.supabase:
                return None
            
            thread_id = config.get("configurable", {}).get("thread_id")
            if not thread_id:
                return None
            
            # Get the latest checkpoint for this thread
            response = self.supabase.table('langgraph_checkpoints').select('*').eq('thread_id', thread_id).order('created_at', desc=True).limit(1).execute()
            
            if not response.data:
                return None
            
            checkpoint_data = response.data[0]
            
            # Get the simple state data
            simple_state = checkpoint_data.get('checkpoint_data', '{}')
            if isinstance(simple_state, str):
                try:
                    simple_state = json.loads(simple_state) if simple_state.strip() else {}
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse checkpoint data JSON: {e}")
                    simple_state = {}
            
            # Reconstruct the full checkpoint
            reconstructed_checkpoint = self._reconstruct_checkpoint(simple_state)
            
            # Create proper metadata with required fields
            metadata = checkpoint_data.get('metadata', {})
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata) if metadata.strip() else {}
                except json.JSONDecodeError:
                    metadata = {}
            
            # Ensure metadata has required fields
            metadata.setdefault('step', metadata.get('step', 0))
            metadata.setdefault('source', 'loop')
            metadata.setdefault('writes', None)
            metadata.setdefault('parents', {})
            
            # Create parent config if needed
            parent_config = None
            if metadata.get('parents'):
                parent_config = {
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_id": list(metadata['parents'].values())[0] if metadata['parents'] else None
                    }
                }
            
            # Return a proper CheckpointTuple object
            return CheckpointTuple(
                config=config,
                checkpoint=reconstructed_checkpoint,
                metadata=metadata,
                parent_config=parent_config
            )
            
        except Exception as e:
            logger.error(f"Error getting checkpoint: {e}")
            return None
    
    def get_tuple(self, config: dict) -> Optional[CheckpointTuple]:
        """Sync version of get_tuple."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.aget_tuple(config))
        except Exception:
            return asyncio.run(self.aget_tuple(config))
    
    async def aget(self, config: dict) -> Optional[Any]:
        """Get checkpoint for a given config."""
        result = await self.aget_tuple(config)
        return result.checkpoint if result else None
    
    def get(self, config: dict) -> Optional[Any]:
        """Sync version of get."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.aget(config))
        except Exception:
            return asyncio.run(self.aget(config))
    
    async def aput(self, config: dict, checkpoint: dict, metadata: dict, new_versions: dict) -> dict:
        """Save checkpoint data in simplified format."""
        try:
            if not self.supabase:
                return config
            
            thread_id = config.get("configurable", {}).get("thread_id")
            if not thread_id:
                return config
            
            # Extract and simplify the checkpoint data with comprehensive error handling
            if self.debug_mode:
                logger.info(f"DEBUG: Checkpoint keys: {list(checkpoint.keys())}")
                channel_values = checkpoint.get("channel_values", {})
                logger.info(f"DEBUG: Channel values keys: {list(channel_values.keys())}")
                messages = channel_values.get("messages", [])
                logger.info(f"DEBUG: Found {len(messages)} messages to serialize")
                for i, msg in enumerate(messages[:3]):  # Log first 3 messages
                    logger.info(f"DEBUG: Message {i}: {type(msg).__name__}")
            
            simple_state = self._extract_simple_state(checkpoint)
            
            # Double-check that simple_state is JSON serializable
            try:
                json.dumps(simple_state)
                if self.debug_mode:
                    logger.info(f"DEBUG: Simple state JSON serialization successful")
            except (TypeError, ValueError) as e:
                logger.error(f"Simple state still not JSON serializable: {e}")
                if self.debug_mode:
                    logger.error(f"DEBUG: Problematic simple_state keys: {list(simple_state.keys())}")
                # Create a minimal safe state
                simple_state = {
                    "messages": [],
                    "conversation_summary": None,
                    "user_id": checkpoint.get("channel_values", {}).get("user_id"),
                    "contact_id": checkpoint.get("channel_values", {}).get("contact_id"),
                    "message_intent": None,
                    "metadata": {},
                    "timestamp": datetime.now().isoformat(),
                    "checkpoint_id": str(uuid.uuid4()),
                    "version": 1
                }
            
            # Ensure metadata is serializable and has required fields
            safe_metadata = self._make_json_safe(metadata) if metadata else {}
            
            # Ensure required metadata fields exist
            safe_metadata.setdefault('step', safe_metadata.get('step', 0))
            safe_metadata.setdefault('source', 'loop')
            safe_metadata.setdefault('writes', None)
            safe_metadata.setdefault('parents', {})
            
            # Final validation of metadata
            try:
                json.dumps(safe_metadata)
            except (TypeError, ValueError) as e:
                logger.error(f"Metadata still not JSON serializable: {e}")
                safe_metadata = {
                    'step': 0,
                    'source': 'loop',
                    'writes': None,
                    'parents': {}
                }
            
            # Create checkpoint record with simple JSON data
            try:
                checkpoint_record = {
                    'thread_id': thread_id,
                    'checkpoint_data': json.dumps(simple_state),
                    'metadata': json.dumps(safe_metadata),
                    'created_at': datetime.now().isoformat()
                }
            except (TypeError, ValueError) as e:
                logger.error(f"Final serialization failed: {e}")
                # Create minimal checkpoint record
                checkpoint_record = {
                    'thread_id': thread_id,
                    'checkpoint_data': json.dumps({
                        "messages": [],
                        "error": f"Serialization failed: {str(e)}",
                        "timestamp": datetime.now().isoformat()
                    }),
                    'metadata': json.dumps({'step': 0, 'source': 'loop', 'writes': None, 'parents': {}}),
                    'created_at': datetime.now().isoformat()
                }
            
            # Insert or update checkpoint
            # First try to update existing, then insert if not found
            existing = self.supabase.table('langgraph_checkpoints').select('id').eq('thread_id', thread_id).limit(1).execute()
            
            if existing.data:
                # Update existing
                self.supabase.table('langgraph_checkpoints').update(checkpoint_record).eq('thread_id', thread_id).execute()
                logger.debug(f"Updated checkpoint for thread {thread_id}")
            else:
                # Insert new
                self.supabase.table('langgraph_checkpoints').insert(checkpoint_record).execute()
                logger.debug(f"Created new checkpoint for thread {thread_id}")
            
            return config
            
        except Exception as e:
            logger.error(f"Error saving checkpoint: {e}")
            return config
    
    def put(self, config: dict, checkpoint: dict, metadata: dict, new_versions: dict) -> dict:
        """Sync version of put."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.aput(config, checkpoint, metadata, new_versions))
        except Exception:
            return asyncio.run(self.aput(config, checkpoint, metadata, new_versions))
    
    def get_next_version(self, current: Optional[str], channel: str) -> int:
        """Generate next version identifier as integer."""
        if current is None:
            return 1
        try:
            # If current is already an integer, increment it
            return int(current) + 1
        except (ValueError, TypeError):
            # If current is not a valid integer, start from 1
            return 1
    
    async def aput_writes(self, config: dict, writes: list, task_id: str) -> None:
        """Store intermediate writes - simplified to just log for now."""
        try:
            thread_id = config.get("configurable", {}).get("thread_id", "unknown")
            logger.debug(f"Writes logged for thread {thread_id}, task {task_id}: {len(writes)} items")
        except Exception as e:
            logger.error(f"Error logging writes: {e}")
    
    def put_writes(self, config: dict, writes: list, task_id: str) -> None:
        """Sync version of put_writes."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.aput_writes(config, writes, task_id))
        except Exception:
            return asyncio.run(self.aput_writes(config, writes, task_id))
    
    async def alist(self, config: dict, limit: int = 10, before: dict = None):
        """List checkpoints for a thread."""
        try:
            if not self.supabase:
                return
            
            thread_id = config.get("configurable", {}).get("thread_id")
            if not thread_id:
                return
            
            response = self.supabase.table('langgraph_checkpoints').select('*').eq('thread_id', thread_id).order('created_at', desc=True).limit(limit).execute()
            
            for item in response.data:
                simple_state = item.get('checkpoint_data', '{}')
                if isinstance(simple_state, str):
                    try:
                        simple_state = json.loads(simple_state) if simple_state.strip() else {}
                    except json.JSONDecodeError as e:
                        logger.warning(f"Failed to parse checkpoint data JSON in list: {e}")
                        simple_state = {}
                
                reconstructed_checkpoint = self._reconstruct_checkpoint(simple_state)
                
                # Handle metadata
                metadata = item.get('metadata', {})
                if isinstance(metadata, str):
                    try:
                        metadata = json.loads(metadata) if metadata.strip() else {}
                    except json.JSONDecodeError:
                        metadata = {}
                
                # Ensure metadata has required fields
                metadata.setdefault('step', 0)
                metadata.setdefault('source', 'loop')
                metadata.setdefault('writes', None)
                metadata.setdefault('parents', {})
                
                yield CheckpointTuple(
                    config=config,
                    checkpoint=reconstructed_checkpoint,
                    metadata=metadata,
                    parent_config=config
                )
            
        except Exception as e:
            logger.error(f"Error listing checkpoints: {e}")
            return
    
    def list(self, config: dict, limit: int = 10, before: dict = None):
        """Sync version of list."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return iter([])
            else:
                async def _get_checkpoints():
                    checkpoints = []
                    async for checkpoint in self.alist(config, limit, before):
                        checkpoints.append(checkpoint)
                    return checkpoints
                
                checkpoints = loop.run_until_complete(_get_checkpoints())
                return iter(checkpoints)
        except Exception as e:
            logger.error(f"Error in sync list method: {e}")
            return iter([])
    
    async def adelete_thread(self, thread_id: str) -> None:
        """Delete all checkpoints for a thread."""
        try:
            if not self.supabase:
                return
            
            response = self.supabase.table('langgraph_checkpoints').delete().eq('thread_id', thread_id).execute()
            logger.info(f"Deleted checkpoints for thread {thread_id}")
            
        except Exception as e:
            logger.error(f"Error deleting thread {thread_id}: {e}")
    
    def delete_thread(self, thread_id: str) -> None:
        """Sync version of delete_thread."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.adelete_thread(thread_id))
        except Exception:
            return asyncio.run(self.adelete_thread(thread_id))
    
    def _test_serialization(self, test_data):
        """Test that data can be serialized and deserialized properly."""
        try:
            # Try to serialize to JSON
            json_str = json.dumps(test_data)
            # Try to deserialize from JSON
            recovered_data = json.loads(json_str)
            return True
        except (TypeError, ValueError) as e:
            logger.error(f"Serialization test failed: {e}")
            return False
    
    def get_stats(self) -> dict:
        """Get checkpointer statistics."""
        try:
            if not self.supabase:
                return {"status": "unavailable", "total_checkpoints": 0}
            
            response = self.supabase.table('langgraph_checkpoints').select('id', count='exact').execute()
            total_count = response.count if hasattr(response, 'count') else len(response.data)
            
            # Test serialization with sample data
            test_messages = [
                HumanMessage(content="Hello"),
                AIMessage(content="Hi there!"),
                SystemMessage(content="System message")
            ]
            serialized = self._serialize_messages(test_messages)
            serialization_test = self._test_serialization(serialized)
            
            return {
                "status": "active",
                "type": "simple_supabase",
                "total_checkpoints": total_count,
                "backend": "supabase_simplified",
                "serialization_test": serialization_test
            }
            
        except Exception as e:
            logger.error(f"Error getting checkpointer stats: {e}")
            return {"status": "error", "total_checkpoints": 0}

async def create_checkpoint_saver():
    """Create a simplified Supabase checkpoint saver for state persistence."""
    try:
        # Check if we have Supabase credentials
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        
        if supabase_url and supabase_key:
            logger.info("Creating simplified Supabase checkpointer")
            
            # Try to create the simplified checkpointer with debug mode enabled temporarily
            checkpointer = SimpleSupabaseCheckpointer(debug_mode=True)
            
            if checkpointer.supabase:
                logger.info("Simplified Supabase checkpoint saver initialized successfully")
                return checkpointer
            else:
                logger.warning("Supabase client initialization failed, falling back to memory saver")
                return MemorySaver()
        else:
            logger.info("Supabase credentials not found, using memory saver for checkpointing")
            return MemorySaver()
        
    except Exception as e:
        logger.error(f"Failed to create simplified Supabase checkpoint saver: {e}")
        logger.info("Falling back to memory saver for checkpointing")
        return MemorySaver()

async def archive_conversation_to_messages_table(contact_id: str, user_id: str, messages: List[BaseMessage]):
    """Archive the complete conversation to the messages table for UI and long-term storage."""
    try:
        supabase = get_supabase_client()
        if not supabase:
            logger.warning("Supabase client not available for archiving")
            return
        
        # Clear existing messages for this contact
        supabase.table('messages').delete().eq('contact_id', contact_id).execute()
        
        # Insert all messages
        message_records = []
        for i, message in enumerate(messages):
            if isinstance(message, HumanMessage):
                sender = 'user'  # Make sure this matches the database constraint
            elif isinstance(message, AIMessage):
                sender = 'assistant'  # Changed from 'bot' to 'assistant' to match constraint
            else:
                continue  # Skip system messages for archival
            
            message_records.append({
                'contact_id': contact_id,
                'sender': sender,
                'channel': 'telegram',  # Default channel
                'content': message.content,
                'status': 'sent',
                'metadata': {
                    'message_index': i,
                    'message_type': type(message).__name__,
                    'archived_at': datetime.now().isoformat()
                },
                'created_at': datetime.now().isoformat()
            })
        
        if message_records:
            supabase.table('messages').insert(message_records).execute()
            logger.info(f"Archived {len(message_records)} messages for contact {contact_id}")
        
    except Exception as e:
        logger.error(f"Error archiving messages: {e}")

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

Your primary role is to help coordinate with the user's colleagues (found in the contacts table) to book meetings with the user. You classify messages to determine how to best assist with this coordination.

CONTEXT FOR YOUR TASK:
You will be given a summary of the early part of the conversation (if available), followed by the most recent messages.
Base your classification on the COMBINATION of the summary and the recent messages. The most recent messages are the most important for determining the user's immediate intent.

Your task is to carefully analyze user messages and classify them into one of these intents:

1. general_conversation - Greetings, casual chat, off-topic discussions

2. clarification_answer - User is providing additional details, confirming information, or answering a clarifying question that the assistant asked
   • Look for messages that are clearly responding to a previous question from the assistant
   • Common patterns: providing missing details, specifying times/dates, confirming information, giving permission to proceed
   • Examples: 
     - Providing details: "Tomorrow at 3 PM", "The client presentation", "Pacific timezone", "Meeting is catching up, about an hour, just me"
     - Confirmations: "Yes", "No", "Sure", "OK", "ok go ahead", "That works", "Yes please", "Go ahead", "Proceed"
     - Giving permission: "ok go ahead", "yes go ahead", "sure go ahead", "that's fine", "sounds good"
   • Key indicator: The message makes most sense as an answer to a previous assistant question or request for confirmation
   • IMPORTANT: If the user is providing meeting details (title, duration, attendees) in response to a previous question, this is ALWAYS clarification_answer
   • CRITICAL: If the assistant just asked "Shall I create this meeting for you?" and the user responds with any form of yes/no/confirmation, this is clarification_answer

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

CRITICAL RULES:
1. If the user's message appears to be answering a question or providing requested details (even without explicit question markers), classify as "clarification_answer"
2. If the user is providing meeting details (title, duration, attendees) in response to a previous assistant question, this is ALWAYS "clarification_answer"
3. If the assistant just asked for confirmation (e.g., "Shall I create this meeting?") and the user responds with any form of yes/no/confirmation, this is clarification_answer
4. Look at the conversation context - if the assistant just asked for meeting details or confirmation and the user is providing them, that's clarification_answer
5. Simple confirmations like "ok", "yes", "sure", "go ahead" are almost always clarification_answer when they follow an assistant question

CONTEXT ANALYSIS:
- Review the last 2-3 messages to understand the conversation flow
- If the assistant asked a question or requested confirmation, and the user is responding to that, it's clarification_answer
- If the assistant said "Shall I create this meeting?" and user says "ok go ahead", that's clarification_answer
- If the assistant asked for meeting details and user provides them, that's clarification_answer

SPECIFIC EXAMPLES:
Assistant: "Shall I create this meeting for you?"
User: "ok go ahead"
→ clarification_answer

Assistant: "Should I proceed with booking this time slot?"
User: "Yes"
→ clarification_answer

Assistant: "What's the meeting title?"
User: "Catching up"
→ clarification_answer

Assistant: "How long should the meeting be?"
User: "About an hour"
→ clarification_answer

Assistant: "Hello! How can I help you today?"
User: "Hi there"
→ general_conversation

User: "Schedule a meeting for tomorrow"
→ meeting_request

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

Your primary role is to coordinate with the user's colleagues (found in the contacts table) to book meetings with the user. You shall perform all calendar operations using the respective tools to connect and perform actions with the Google Calendar API.

DEMO MODE NOTE: When running in LangGraph Studio or other demo environments, calendar tools will provide demo responses instead of connecting to actual Google Calendar. This is normal and expected for testing purposes.

TIME PARSING CAPABILITIES:
You are capable of understanding and converting time references directly. When you see time references:
1. ALWAYS convert them to ISO format (YYYY-MM-DDTHH:MM:SS+HH:MM)
2. Use the user's timezone (provided in the conversation) or UTC if not specified
3. Handle relative references like:
   - "tomorrow at 10 AM" → Calculate exact date and time
   - "next monday" → Find the date of next Monday
   - "in 2 hours" → Add hours to current time
   - "afternoon" → Use 2 PM as default time
   - "morning" → Use 9 AM as default time
4. For duration references:
   - "about an hour" = 60 minutes
   - "half hour" = 30 minutes
   - "an hour and a half" = 90 minutes
5. For date-only references, use business hours (8 AM - 6 PM)
6. For time-only references, use today's date
7. ALWAYS validate that dates are not in the past

Example time parsing:
- "tomorrow at 10 AM" → "2024-01-16T10:00:00+00:00"
- "next monday afternoon" → "2024-01-22T14:00:00+00:00"
- "in 2 hours" → (current time + 2 hours in ISO format)

Your role is to help users manage their calendar and schedule meetings efficiently. You have access to these calendar tools:
- parse_time_reference_tool: Parse any natural language time reference (events with duration OR availability periods)
- check_availability_tool: Check availability for a specific time (provide ISO format)
- create_event_tool: Create calendar events (requires ISO format times)
- get_events_tool: Retrieve existing calendar events
- get_current_time_tool: Get current time and timezone information
- list_calendars_tool: List all calendars available to the user
- modify_event_tool: Modify existing calendar events
- delete_event_tool: Delete calendar events permanently
- find_available_slots_tool: Find multiple available time slots
- get_available_slots_for_period_tool: Get available slots by checking calendar

## Data Retrieval Tools for Availability:
- **get_available_slots_for_period_tool**: The most powerful tool for availability checking. It automatically:
  - Retrieves busy times from Google Calendar
  - Finds available slots in the specified time period
  - Returns formatted available time slots
  - Use this for queries like "What slots are available tomorrow?"

- **find_available_slots_tool**: Enhanced version that can auto-retrieve from Google Calendar
  - Can work with pre-provided busy times OR retrieve from Google Calendar automatically
  - Useful for finding slots within specific datetime ranges

## Colleague Coordination Process:
1. **Identify the Request**: When a colleague wants to meet with your user
2. **Check Availability**: Use calendar tools to check your user's availability
3. **Propose Times**: Suggest available time slots to the colleague
4. **Confirm Details**: Gather meeting title, duration, and any other details
5. **Create Meeting**: Use calendar tools to create the meeting in Google Calendar
6. **Confirm Booking**: Provide confirmation to the colleague

## Calendar Tool Usage Requirements:
- **Always use calendar tools** for any calendar-related operations
- **Never skip tool usage** when calendar operations are needed
- **Use Google Calendar API** through the provided tools for all calendar actions
- **Validate all inputs** before using tools to ensure proper formatting

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

HANDLING CONFIRMATIONS:
When users give simple confirmations (like "ok go ahead", "yes", "sure"):
- If you just asked "Shall I create this meeting?" and they say "ok go ahead", IMMEDIATELY proceed with creating the meeting
- If you asked for confirmation about any action and they confirm, proceed with that action
- Don't ask for more details if you already have sufficient information from the conversation history
- Use the information from the entire conversation to complete the task
- Acknowledge their confirmation briefly, then proceed: "Great! I'll create that meeting for you now."

EXAMPLES of handling confirmations:
Assistant: "Shall I create this meeting for you?"
User: "ok go ahead"
Assistant: "Great! I'll create that meeting for you now." [Then immediately use create_event_tool with all the details from conversation history]

A: "Should I proceed with booking this time slot?"
User: "Yes"
Assistant: "Perfect! I'll book that time slot for you." [Then immediately proceed with the action]

INTELLIGENT TIME PROCESSING:
- ALWAYS extract temporal information from conversation history (yesterday, today, tomorrow, specific dates/times)
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
1. Calculate "tomorrow at 10 AM" → exact ISO datetime
2. Calculate end time (start + 60 minutes) 
3. Extract: title="catch-up meeting", no attendees needed
4. IMMEDIATELY use create_event_tool with the ISO datetime values

User provides clarification: "Meeting is catching up, about an hour, just me" 
Assistant: Review conversation history, see "tomorrow at 10 AM" was mentioned before
1. Calculate "tomorrow at 10 AM" → exact ISO datetime
2. Extract all info: title="catching up", duration=60 mins, no attendees
3. PROCEED with create_event_tool instead of asking for confirmation

Always double-check that dates and times make sense before proceeding.
            """),
            MessagesPlaceholder(variable_name="messages"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
        
        return create_tool_calling_agent(self.llm, tools, execution_prompt)
    
    async def _create_graph(self, use_checkpointer: bool = True) -> StateGraph:
        """Create the LangGraph workflow with optional checkpointing.
        
        Args:
            use_checkpointer: If True, includes a custom checkpointer. 
                             Set to False for LangGraph Studio/API which handles persistence automatically.
        """
        # Initialize the graph
        workflow = StateGraph(SimpleState)
        
        # Add nodes
        workflow.add_node("summarizer", self._summarizer_node)
        workflow.add_node("intent_classifier", self._intent_classifier_node)
        workflow.add_node("calendar_execution", self._calendar_execution_node)
        workflow.add_node("archiver", self._archiver_node)
        
        # Set entry point to summarizer
        workflow.set_entry_point("summarizer")
        
        # Connect summarizer to intent classifier
        workflow.add_edge("summarizer", "intent_classifier")
        
        # Connect intent classifier directly to calendar execution (no routing needed)
        workflow.add_edge("intent_classifier", "calendar_execution")
        
        # Connect calendar execution to archiver before END
        workflow.add_edge("calendar_execution", "archiver")
        workflow.add_edge("archiver", END)
        
        # Create checkpointer only if requested
        if use_checkpointer:
            try:
                checkpointer = await create_checkpoint_saver()
                logger.info(f"Graph compiled with checkpointer: {type(checkpointer).__name__}")
                return workflow.compile(checkpointer=checkpointer)
            except Exception as e:
                logger.error(f"Failed to create checkpointer, compiling without: {e}")
                return workflow.compile()
        else:
            # For LangGraph Studio/API, don't use custom checkpointer
            logger.info("Graph compiled without custom checkpointer")
            return workflow.compile()
    
    # Node implementations
    async def _summarizer_node(self, state: SimpleState) -> SimpleState:
        """Trims and summarizes the conversation history for cost efficiency."""
        logger.info("📝 Summarizer Node")
        
        messages = state.get("messages", [])
        
        if len(messages) > SUMMARY_THRESHOLD:
            logger.info(f"Conversation length ({len(messages)}) exceeds threshold ({SUMMARY_THRESHOLD}). Summarizing...")
            
            # 1. Identify what to summarize and what to keep
            messages_to_summarize = messages[:-MESSAGES_TO_RETAIN]
            retained_messages = messages[-MESSAGES_TO_RETAIN:]
            
            # 2. Create the text to be summarized
            previous_summary = state.get("conversation_summary") or ""
            summary_prompt_text = "\n".join(
                [f"{type(m).__name__}: {m.content}" for m in messages_to_summarize]
            )
            
            # 3. Create the summarization prompt
            summarization_prompt = f"""You are a conversation summarizer for Athena, an executive assistant AI. Your task is to create a concise summary of the provided conversation excerpt.

Previous summary (for context):
{previous_summary}

New conversation to summarize:
{summary_prompt_text}

Please provide a new, consolidated summary that incorporates both the previous summary and the new conversation.
Preserve key information like:
- Names and contact details
- Meeting requests and scheduling details
- Calendar events and availability discussions
- Important dates, times, and deadlines
- Decisions made and actions taken
- User preferences and requirements

Focus on information that would be relevant for future interactions with this contact.

New consolidated summary:"""
            
            try:
                # 4. Invoke the LLM for summarization
                summary_response = await self.llm.ainvoke([HumanMessage(content=summarization_prompt)])
                new_summary = summary_response.content
                
                logger.info(f"Generated new summary of length {len(new_summary)}")
                
                # 5. Update the state
                state = {
                    **state,
                    "conversation_summary": new_summary,
                    "messages": retained_messages  # The message history is now trimmed
                }
                
            except Exception as e:
                logger.error(f"Error in summarization: {e}")
                # If summarization fails, just keep the recent messages
                state = {
                    **state,
                    "messages": retained_messages
                }
        
        return state
    
    async def _archiver_node(self, state: SimpleState) -> SimpleState:
        """Archive the conversation to the messages table for UI and long-term storage."""
        logger.info("🗄️ Archiver Node")
        
        try:
            messages = state.get("messages", [])
            contact_id = state.get("contact_id")
            user_id = state.get("user_id")
            
            if messages and contact_id and user_id:
                await archive_conversation_to_messages_table(contact_id, user_id, messages)
            else:
                logger.warning("Missing required data for archiving")
                
        except Exception as e:
            logger.error(f"Error in archiver node: {e}")
        
        return state

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
        
        # Prepare context with conversation summary and recent messages
        context_messages = []
        
        # Add conversation summary if available
        conversation_summary = state.get("conversation_summary")
        if conversation_summary:
            summary_message = SystemMessage(content=f"CONVERSATION SUMMARY: {conversation_summary}")
            context_messages.append(summary_message)
        
        # Add recent messages for immediate context
        recent_messages = state["messages"][-5:] if len(state["messages"]) > 1 else [HumanMessage(content=latest_message_content)]
        context_messages.extend(recent_messages)
        
        # Log context for debugging
        logger.info(f"Intent classification context ({len(context_messages)} messages, summary: {'Yes' if conversation_summary else 'No'}):")
        for i, msg in enumerate(context_messages):
            msg_type = type(msg).__name__
            content_preview = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
            logger.info(f"  {i+1}. {msg_type}: {content_preview}")
        
        agent_executor = AgentExecutor(agent=self.intent_classifier, tools=[], verbose=True)
        
        try:
            result = await agent_executor.ainvoke({"messages": context_messages})
            intent = result["output"].strip().lower()
            
            # Clean up the intent - remove markdown formatting and extra characters
            intent = intent.replace('*', '').replace('`', '').replace('"', '').replace("'", '').strip()
            
            # Validate intent
            valid_intents = [
                "general_conversation", "clarification_answer", "meeting_request", 
                "calendar_inquiry", "availability_inquiry", "meeting_modification",
                "time_question"
            ]
            
            if intent not in valid_intents:
                logger.warning(f"Intent '{intent}' not in valid intents: {valid_intents}")
                intent = "general_conversation"
            
            state["message_intent"] = intent
            logger.info(f"Intent classified: {intent}")
            
            if intent == "clarification_answer":
                logger.info("🔄 Detected clarification answer - will provide conversation context to execution decider")
            
        except Exception as e:
            logger.error(f"Intent classification error: {e}")
            state["message_intent"] = "general_conversation"
        
        return state
    
    async def _calendar_execution_node(self, state: SimpleState) -> SimpleState:
        """Execute calendar operations and handle all user interactions."""
        logger.info("📅 Calendar Execution Node")
        
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
- Time references: Convert "tomorrow", "today", "next week", specific times like "10 AM" to proper datetime
- Duration: "about an hour" = 60 minutes, "30 min" = 30 minutes
- Attendees: Extract all relevant attendee information
- Use get_current_time_tool to calculate exact dates from relative time references
- If you have sufficient information, proceed with the action instead of asking for more details.

CRITICAL: If the user is giving confirmation (like "ok go ahead", "yes", "sure") and you have sufficient information from the conversation history, PROCEED IMMEDIATELY with the action (like creating a meeting) instead of asking for more details.

CONFIRMATION HANDLING:
- If you just asked "Shall I create this meeting?" and they say "ok go ahead", create the meeting now
- If you asked for confirmation about any action and they confirm, proceed with that action
- Use get_current_time_tool to convert relative times to proper ISO format
- Extract all meeting details from the conversation history and proceed with the action

DO NOT ask for confirmation again if they've already confirmed the action.""")
            messages.insert(-1, clarification_context)  # Insert before the last user message
        elif message_intent == "general_conversation":
            logger.info("💬 Processing general conversation")
            # For general conversation, use a welcoming response but also mention calendar capabilities
            messages = state["messages"][-3:] if len(state["messages"]) > 1 else state["messages"].copy()
            general_context = SystemMessage(content="""The user is engaging in general conversation (greetings, casual chat, etc.). 

Respond warmly and professionally as Athena, the executive assistant. Always:
- Be friendly and welcoming
- Introduce your calendar management capabilities
- Ask how you can help with their scheduling needs
- Keep responses concise but helpful

If this is a greeting or introduction, briefly explain what you can do:
- Schedule meetings and appointments
- Check calendar availability
- Manage calendar events
- Find available time slots
- Handle meeting modifications

Make them feel comfortable and ready to use your calendar features.""")
            messages.insert(0, general_context)
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
            logger.error(f"Calendar execution error: {e}")
            return {
                **state,
                "messages": state["messages"] + [AIMessage(content="I'd be happy to help you with that! Could you provide a bit more detail about what you'd like me to do?")]
            }
    

    
    # Routing functions removed - now using direct flow
    
    async def process_message(self, contact_id: str, message: str, user_id: str, 
                            user_details: Dict[str, Any] = None, access_token: str = None, 
                            refresh_token: str = None) -> Dict[str, Any]:
        """Process an incoming message with LangGraph's built-in checkpointing."""
        try:
            logger.info("🚀 Starting Enhanced LangGraph execution with built-in checkpointing")
            
            # Set up calendar service if needed (only if not already set up)
            if access_token and not _calendar_service:
                try:
                    set_calendar_service(access_token, refresh_token, user_id, self.llm)
                except Exception as e:
                    logger.error(f"Error setting up calendar service: {str(e)}")
            
            # Create thread ID for checkpointing (unique per contact)
            thread_id = f"athena_{user_id}_{contact_id}"
            
            # Get the compiled graph (with or without custom checkpointer based on environment)
            graph = await self._create_graph()
            
            # Check if this is a continuing conversation by getting existing state
            try:
                existing_state = await graph.aget_state({"configurable": {"thread_id": thread_id}})
                # Check if state exists and has messages
                is_continuing_conversation = (
                    existing_state and 
                    existing_state.values and 
                    existing_state.values.get("messages")
                )
                logger.info(f"Thread {thread_id}: {'Continuing' if is_continuing_conversation else 'New'} conversation")
            except Exception as e:
                logger.warning(f"Could not retrieve existing state: {e}")
                is_continuing_conversation = False
            
            # Prepare the input state
            # For continuing conversations, LangGraph will automatically merge with existing state
            input_state = {
                "messages": [HumanMessage(content=message)],  # Only the new message
                "user_id": user_id,
                "contact_id": contact_id,
                "message_intent": None,  # Will be determined by intent classifier
                "metadata": {
                    "user_details": user_details,
                    "access_token": access_token is not None,
                    "refresh_token": refresh_token is not None,
                    "timestamp": datetime.now().isoformat(),
                    "is_continuing_conversation": is_continuing_conversation
                }
            }
            
            # Execute with built-in checkpointing
            # LangGraph automatically loads previous state and merges with input
            final_state = await graph.ainvoke(
                input_state,
                config={"configurable": {"thread_id": thread_id}}
            )
            
            # Extract response from the last AI message
            messages = final_state.get("messages", [])
            response = "I apologize, but I couldn't process your request."
            
            if messages:
                # Find the last AI message
                for msg in reversed(messages):
                    if isinstance(msg, AIMessage):
                        response = msg.content
                        break
            
            return {
                "response": response,
                "tools_used": [],  # Could be enhanced to track tool usage
                "intent": final_state.get("message_intent", "unknown"),
                "user_id": user_id,
                "contact_id": contact_id,
                "thread_id": thread_id,
                "extracted_info": {
                    "enhanced_agent": True,
                    "message_count": len(messages),
                    "checkpointing_enabled": True,
                    "has_summary": bool(final_state.get("conversation_summary")),
                    "summary_length": len(final_state.get("conversation_summary", "")),
                    "is_continuing_conversation": is_continuing_conversation
                }
            }
            
        except Exception as e:
            logger.error(f"Error in Enhanced LangGraph execution: {str(e)}")
            return {
                "response": "I apologize, but I encountered an error processing your request.",
                "tools_used": [],
                "intent": "error",
                "user_id": user_id,
                "contact_id": contact_id,
                "extracted_info": None
            }
    
    async def clear_conversation_history(self, user_id: str, contact_id: str) -> Dict[str, Any]:
        """Clear conversation history for a specific contact."""
        try:
            thread_id = f"athena_{user_id}_{contact_id}"
            graph = await self._create_graph()
            
            # Clear the checkpoint by creating a new empty state
            await graph.ainvoke(
                {
                    "messages": [],
                    "user_id": user_id,
                    "contact_id": contact_id,
                    "message_intent": None,
                    "conversation_summary": None,
                    "metadata": {"cleared_at": datetime.now().isoformat()}
                },
                config={"configurable": {"thread_id": thread_id}}
            )
            
            logger.info(f"Cleared conversation history for thread {thread_id}")
            return {
                "status": "success",
                "message": f"Conversation history cleared for contact {contact_id}",
                "thread_id": thread_id
            }
        except Exception as e:
            logger.error(f"Error clearing conversation history: {e}")
            return {
                "status": "error",
                "message": f"Failed to clear conversation history: {str(e)}"
            }

    async def get_conversation_summary(self, user_id: str, contact_id: str) -> Dict[str, Any]:
        """Get conversation summary for a specific contact."""
        try:
            thread_id = f"athena_{user_id}_{contact_id}"
            graph = await self._create_graph()
            
            # Get the current state
            state = await graph.aget_state({"configurable": {"thread_id": thread_id}})
            
            if state and state.values:
                conversation_summary = state.values.get("conversation_summary")
                messages = state.values.get("messages", [])
                return {
                    "status": "success",
                    "thread_id": thread_id,
                    "conversation_summary": conversation_summary,
                    "message_count": len(messages),
                    "has_summary": bool(conversation_summary)
                }
            else:
                return {
                    "status": "success",
                    "thread_id": thread_id,
                    "conversation_summary": None,
                    "message_count": 0,
                    "has_summary": False
                }
        except Exception as e:
            logger.error(f"Error getting conversation summary: {e}")
            return {
                "status": "error",
                "message": f"Failed to get conversation summary: {str(e)}"
            }

    async def get_conversation_state(self, user_id: str, contact_id: str) -> Dict[str, Any]:
        """Get comprehensive conversation state using LangGraph's built-in state management."""
        try:
            thread_id = f"athena_{user_id}_{contact_id}"
            graph = await self._create_graph()
            
            # Get the current state snapshot
            state_snapshot = await graph.aget_state({"configurable": {"thread_id": thread_id}})
            
            if not state_snapshot or not state_snapshot.values:
                return {
                    "status": "success",
                    "thread_id": thread_id,
                    "exists": False,
                    "conversation_summary": None,
                    "message_count": 0,
                    "last_updated": None,
                    "metadata": {}
                }
            
            # Extract state information
            values = state_snapshot.values
            messages = values.get("messages", [])
            conversation_summary = values.get("conversation_summary")
            metadata = values.get("metadata", {})
            
            # Get state history (LangGraph's built-in versioning)
            state_history = []
            try:
                # Get the last few state versions
                async for state in graph.aget_state_history(
                    {"configurable": {"thread_id": thread_id}}, 
                    limit=5
                ):
                    state_history.append({
                        "timestamp": getattr(state, 'created_at', None),
                        "next_actions": list(state.next) if state.next else [],
                        "message_count": len(state.values.get("messages", [])) if state.values else 0
                    })
            except Exception as e:
                logger.warning(f"Could not retrieve state history: {e}")
            
            return {
                "status": "success",
                "thread_id": thread_id,
                "exists": True,
                "conversation_summary": conversation_summary,
                "message_count": len(messages),
                "last_updated": getattr(state_snapshot, 'created_at', None),
                "metadata": metadata,
                "state_history": state_history,
                "next_actions": list(state_snapshot.next) if state_snapshot.next else []
            }
        except Exception as e:
            logger.error(f"Error getting conversation state: {e}")
            return {
                "status": "error",
                "message": f"Failed to get conversation state: {str(e)}"
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
async def _create_simple_studio_graph():
    """Create a compiled graph for LangGraph Studio."""
    agent = get_simple_agent()
    # Use no checkpointer for LangGraph Studio since it handles persistence automatically
    return await agent._create_graph(use_checkpointer=False)

# For LangGraph Studio compatibility - create a graph factory function
def athena_elegant_graph(config=None):
    """Graph factory function for LangGraph Studio that accepts a RunnableConfig."""
    try:
        logger.info("Creating graph for LangGraph Studio")
        
        # Create the agent
        agent = get_simple_agent()
        
        # Create without checkpointer for LangGraph Studio
        from langgraph.graph import StateGraph, END
        from langgraph.graph.message import add_messages
        
        # Create the graph
        workflow = StateGraph(SimpleState)
        
        # Add nodes - these are async methods so they should work fine with LangGraph
        workflow.add_node("summarizer", agent._summarizer_node)
        workflow.add_node("intent_classifier", agent._intent_classifier_node)
        workflow.add_node("calendar_execution", agent._calendar_execution_node)
        workflow.add_node("archiver", agent._archiver_node)
        
        # Set entry point to summarizer
        workflow.set_entry_point("summarizer")
        
        # Connect summarizer to intent classifier
        workflow.add_edge("summarizer", "intent_classifier")
        
        # Connect intent classifier directly to calendar execution (no routing needed)
        workflow.add_edge("intent_classifier", "calendar_execution")
        
        # Connect calendar execution to archiver before END
        workflow.add_edge("calendar_execution", "archiver")
        workflow.add_edge("archiver", END)
        
        # Compile without checkpointer for LangGraph Studio
        graph = workflow.compile()
        logger.info("Graph created successfully for LangGraph Studio")
        return graph
        
    except Exception as e:
        logger.error(f"Error creating graph for LangGraph Studio: {e}")
        # Create a minimal fallback graph
        workflow = StateGraph(SimpleState)
        workflow.add_node("error", lambda state: {
            **state, 
            "messages": state["messages"] + [AIMessage(content=f"Graph creation failed: {str(e)}")]
        })
        workflow.set_entry_point("error")
        workflow.add_edge("error", END)
        return workflow.compile() 