from typing import Dict, Any, List, Optional, Literal, TypedDict, Annotated
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, AIMessage, SystemMessage, BaseMessage
from langchain.tools import tool
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain import hub
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
import logging
from datetime import datetime, timedelta
import pytz
import json
import os
import re
from pydantic import BaseModel, Field
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request
from supabase import create_client, Client

from config import Config

logger = logging.getLogger(__name__)
# Global LLM instance for availability mode detection
_llm_instance = None

# --- Helper functions copied from tools.py for tool self-containment ---
def parse_relative_time_reference(time_ref: str, user_timezone: str = "UTC", base_datetime: datetime = None) -> tuple:
    """Parse relative time references like 'tomorrow', 'next week', etc. into datetime ranges."""
    try:
        if base_datetime is None:
            base_datetime = datetime.now(pytz.timezone(user_timezone))
        if base_datetime.tzinfo is None:
            base_datetime = pytz.timezone(user_timezone).localize(base_datetime)
        time_ref_lower = time_ref.lower().strip()
        specific_time = None
        time_patterns = [
            r'(\d{1,2}):(\d{2})\s*(am|pm)?',
            r'(\d{1,2})\s*(am|pm)',
            r'(\d{1,2})\s*o\'?clock',
        ]
        for pattern in time_patterns:
            match = re.search(pattern, time_ref_lower)
            if match:
                hour = int(match.group(1))
                minute = int(match.group(2)) if len(match.groups()) > 1 and match.group(2) else 0
                ampm = match.group(3) if len(match.groups()) > 2 else None
                if ampm:
                    if ampm == 'pm' and hour != 12:
                        hour += 12
                    elif ampm == 'am' and hour == 12:
                        hour = 0
                specific_time = (hour, minute)
                break
        named_times = {
            'noon': 12, 'midnight': 0, 'morning': 9, 'afternoon': 14, 
            'evening': 18, 'night': 20, 'lunchtime': 12
        }
        if not specific_time:
            for name, hour in named_times.items():
                if name in time_ref_lower:
                    specific_time = (hour, 0)
                    break
        if time_ref_lower in ['today']:
            if specific_time:
                start = base_datetime.replace(hour=specific_time[0], minute=specific_time[1], second=0, microsecond=0)
                end = start + timedelta(minutes=30)
            else:
                start = base_datetime.replace(hour=8, minute=0, second=0, microsecond=0)
                end = base_datetime.replace(hour=18, minute=0, second=0, microsecond=0)
        elif time_ref_lower in ['tomorrow']:
            tomorrow = base_datetime + timedelta(days=1)
            if specific_time:
                start = tomorrow.replace(hour=specific_time[0], minute=specific_time[1], second=0, microsecond=0)
                end = start + timedelta(minutes=30)
            else:
                start = tomorrow.replace(hour=8, minute=0, second=0, microsecond=0)
                end = tomorrow.replace(hour=18, minute=0, second=0, microsecond=0)
        elif time_ref_lower in ['next week', 'next_week']:
            days_ahead = 7 - base_datetime.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            next_monday = base_datetime + timedelta(days=days_ahead)
            start = next_monday.replace(hour=8, minute=0, second=0, microsecond=0)
            end = (next_monday + timedelta(days=4)).replace(hour=18, minute=0, second=0, microsecond=0)
        elif time_ref_lower in ['this week', 'this_week']:
            if base_datetime.weekday() >= 5:
                days_ahead = 7 - base_datetime.weekday()
                start_day = base_datetime + timedelta(days=days_ahead)
            else:
                start_day = base_datetime
            start = start_day.replace(hour=8, minute=0, second=0, microsecond=0)
            days_to_friday = 4 - start_day.weekday()
            if days_to_friday < 0:
                days_to_friday += 7
            end_day = start_day + timedelta(days=days_to_friday)
            end = end_day.replace(hour=18, minute=0, second=0, microsecond=0)
        elif time_ref_lower in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']:
            weekdays = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
            target_weekday = weekdays.index(time_ref_lower)
            days_ahead = target_weekday - base_datetime.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            target_day = base_datetime + timedelta(days=days_ahead)
            if specific_time:
                start = target_day.replace(hour=specific_time[0], minute=specific_time[1], second=0, microsecond=0)
                end = start + timedelta(minutes=30)
            else:
                start = target_day.replace(hour=8, minute=0, second=0, microsecond=0)
                end = target_day.replace(hour=18, minute=0, second=0, microsecond=0)
        else:
            logger.warning(f"Could not parse time reference '{time_ref}', defaulting to today")
            if specific_time:
                start = base_datetime.replace(hour=specific_time[0], minute=specific_time[1], second=0, microsecond=0)
                end = start + timedelta(minutes=30)
            else:
                start = base_datetime.replace(hour=8, minute=0, second=0, microsecond=0)
                end = base_datetime.replace(hour=18, minute=0, second=0, microsecond=0)
        logger.info(f"Parsed '{time_ref}' to range: {start.isoformat()} - {end.isoformat()}")
        return start, end
    except Exception as e:
        logger.error(f"Error parsing time reference '{time_ref}': {e}")
        fallback_start = base_datetime.replace(hour=8, minute=0, second=0, microsecond=0)
        fallback_end = base_datetime.replace(hour=18, minute=0, second=0, microsecond=0)
        return fallback_start, fallback_end

def parse_specific_time_from_query(query: str, temporal_reference: str, user_timezone: str, base_datetime: datetime) -> tuple:
    """Parse specific time from query when in specific_slot_inquiry mode."""
    try:
        start_datetime, end_datetime = parse_relative_time_reference(temporal_reference, user_timezone, base_datetime)
        query_lower = query.lower()
        time_patterns = [
            r'(\d{1,2}):(\d{2})\s*(am|pm)?',
            r'(\d{1,2})\s*(am|pm)',
            r'(\d{1,2})\s*o\'?clock',
        ]
        specific_time = None
        for pattern in time_patterns:
            match = re.search(pattern, query_lower)
            if match:
                hour = int(match.group(1))
                minute = int(match.group(2)) if len(match.groups()) > 1 and match.group(2) else 0
                ampm = match.group(3) if len(match.groups()) > 2 else None
                if ampm:
                    if ampm == 'pm' and hour != 12:
                        hour += 12
                    elif ampm == 'am' and hour == 12:
                        hour = 0
                specific_time = start_datetime.replace(hour=hour, minute=minute, second=0, microsecond=0)
                break
        named_times = {
            'noon': 12, 'midnight': 0, 'morning': 9, 'afternoon': 14, 
            'evening': 18, 'night': 20, 'lunchtime': 12
        }
        if not specific_time:
            for name, hour in named_times.items():
                if name in query_lower:
                    specific_time = start_datetime.replace(hour=hour, minute=0, second=0, microsecond=0)
                    break
        if specific_time:
            end_time = specific_time + timedelta(minutes=30)
            logger.info(f"Parsed specific time from '{query}': {specific_time.isoformat()} to {end_time.isoformat()}")
            return specific_time, end_time
        else:
            logger.info(f"Could not parse specific time from '{query}', using temporal reference range")
            return start_datetime, end_datetime
    except Exception as e:
        logger.error(f"Error parsing specific time from query '{query}': {e}")
        return parse_relative_time_reference(temporal_reference, user_timezone, base_datetime)

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
        raise ValueError("Supabase URL and service role key are required")
    
    return create_client(supabase_url, supabase_key)

def get_included_calendars(user_id: str) -> List[str]:
    """Get list of calendar IDs that should be included in availability checks."""
    try:
        supabase = get_supabase_client()
        if not supabase:
            logger.error("Could not initialize Supabase client")
            return []
        
        response = supabase.table('calendar_list').select('calendar_id').eq('user_id', user_id).eq('calendar_type', 'google').eq('to_include_in_check', True).execute()
        
        if response.data:
            calendar_ids = [item['calendar_id'] for item in response.data]
            logger.info(f"Found {len(calendar_ids)} included calendars for user {user_id}")
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
        response = supabase.table('calendar_list').select('timezone').eq('user_id', user_id).eq('calendar_id', calendar_id).execute()
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
            
            if attendees:
                event_body['attendees'] = [{'email': email} for email in attendees]
            
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
    """Simplified state schema for Athena agent using proper message handling."""
    messages: Annotated[List[BaseMessage], add_messages]
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
        user_id = get_current_user_id()
        user_timezone = get_user_timezone(user_id)
        calendar_ids = get_included_calendars(user_id)
        
        if not calendar_ids:
            return "No calendars configured for availability checking. Please configure calendars in the web interface."
        
        # Get current datetime in user's timezone
        current_datetime = datetime.now(pytz.timezone(user_timezone))
        
        # Parse the query to determine time range
        start_datetime, end_datetime = parse_relative_time_reference(query, user_timezone, current_datetime)
        
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
            
    except Exception as e:
        logger.error(f"Error in check_availability_tool: {e}")
        return f"I had trouble checking availability. Please try again or provide more specific time details."

@tool
def create_event_tool(title: str, start_datetime: str, end_datetime: str, 
                     attendee_emails: List[str] = None, description: str = "", 
                     location: str = "") -> str:
    """Create a new calendar event on the user's primary calendar.
    
    This tool creates calendar events with full Google Calendar integration.
    
    Args:
        title: Meeting title (required)
        start_datetime: Start time in ISO format with timezone (required)
        end_datetime: End time in ISO format with timezone (required)
        attendee_emails: List of attendee email addresses (optional)
        description: Meeting description (optional)
        location: Meeting location (optional)
    """
    try:
        # Validate inputs
        if not title or not title.strip():
            return "❌ Meeting title is required"
        if not start_datetime or not end_datetime:
            return "❌ Start and end times are required"
        
        user_id = get_current_user_id()
        user_timezone = get_user_timezone(user_id)
        calendar_ids = get_included_calendars(user_id)
        
        if not calendar_ids:
            return "No calendars configured for creating events. Please configure calendars in the web interface."
        
        # Check if the start time is in the past
        start_dt = datetime.fromisoformat(start_datetime.replace('Z', '+00:00'))
        current_datetime = datetime.now(pytz.timezone(user_timezone))
        
        if start_dt < current_datetime:
            return f"❌ Cannot create event in the past: {start_datetime}"
        
        # Use the first configured calendar (usually primary) for creating events
        primary_calendar = calendar_ids[0]
        calendar_timezone = get_calendar_timezone(user_id, primary_calendar)
        
        service = get_calendar_service()
        
        event = service.create_event(
            primary_calendar, title, description, start_datetime, 
            end_datetime, calendar_timezone, attendee_emails or [], location
        )
        
        result = f"✅ Meeting scheduled successfully on your calendar!\n"
        result += f"Title: {event['summary']}\n"
        result += f"Time: {event['start']} to {event['end']}\n"
        result += f"Event ID: {event['id']}\n"
        if attendee_emails:
            result += f"Attendees: {', '.join(attendee_emails)}\n"
        if location:
            result += f"Location: {location}\n"
        if event.get('html_link'):
            result += f"Calendar link: {event['html_link']}\n"
        
        return result
        
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
        
    except Exception as e:
        logger.error(f"Error in get_events_tool: {e}")
        return f"I had trouble retrieving calendar events. Please try again."

@tool
def get_current_time_tool(timezone: str = "UTC") -> str:
    """Get current date and time in specified timezone.
    
    This tool provides current time information for timezone-aware operations.
    
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
    
    This tool helps convert natural language time references to proper ISO datetime format
    for use with other calendar tools.
    
    Args:
        time_reference: Natural language time reference (e.g., 'tomorrow at 10 AM', 'next Monday at 2 PM')
        timezone: Timezone to use for conversion (default: UTC)
    """
    try:
        tz = pytz.timezone(timezone)
        current_time = datetime.now(tz)
        
        # Use the existing time parsing function
        start_time, end_time = parse_relative_time_reference(time_reference, timezone, current_time)
        
        return f"'{time_reference}' converts to: {start_time.isoformat()} to {end_time.isoformat()}"
        
    except Exception as e:
        logger.error(f"Error in convert_relative_time_tool with input '{time_reference}': {e}")
        return f"I had trouble converting the time reference '{time_reference}'. Please provide a more specific date and time."

@tool
def list_calendars_tool() -> str:
    """List all calendars available to the user.
    
    This tool shows all calendars that the user has access to, including their IDs,
    names, timezones, and access levels.
    """
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
            update_body['attendees'] = [{'email': email} for email in attendee_emails]
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
    except Exception as e:
        logger.error(f"Error in delete_event_tool: {e}")
        return f"I had trouble deleting the event. Please check the event ID and try again."

@tool
def find_available_slots_tool(start_datetime: str, end_datetime: str, duration_minutes: int = 30, busy_times: List[Dict] = None) -> str:
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
        
        # Use empty list if no busy times provided
        busy_times = busy_times or []
        
        # Call the helper function
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
def parse_specific_time_tool(query: str, temporal_reference: str, timezone: str = "UTC") -> str:
    """Parse specific time from a query when you have a temporal reference.
    
    This tool helps extract specific times from natural language queries when you know the general time period.
    Useful for converting "2 PM tomorrow" into exact datetime when you know "tomorrow" refers to a specific date.
    
    Args:
        query: The query containing specific time information (e.g., "2 PM", "10:30 AM")
        temporal_reference: The general time reference (e.g., "tomorrow", "monday", "next week")
        timezone: Timezone to use for conversion (default: UTC)
    """
    try:
        tz = pytz.timezone(timezone)
        current_time = datetime.now(tz)
        
        # Call the helper function
        start_time, end_time = parse_specific_time_from_query(query, temporal_reference, timezone, current_time)
        
        return f"Parsed '{query}' with reference '{temporal_reference}' to: {start_time.isoformat()} to {end_time.isoformat()}"
        
    except Exception as e:
        logger.error(f"Error in parse_specific_time_tool with input '{query}': {e}")
        return f"I had trouble parsing the specific time from '{query}'. Please provide a more specific time reference."

# Bundle tools
tools = [check_availability_tool, create_event_tool, get_events_tool, get_current_time_tool, convert_relative_time_tool, list_calendars_tool, modify_event_tool, delete_event_tool, find_available_slots_tool, parse_specific_time_tool]

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
- check_availability_tool: Check availability using natural language queries (e.g., "tomorrow at 2 PM", "next week")
- create_event_tool: Create calendar events and meetings with full Google Calendar integration
- get_events_tool: Retrieve existing calendar events from all configured calendars
- get_current_time_tool: Get current time and timezone information
- convert_relative_time_tool: Convert relative time references (like "tomorrow at 10 AM") to proper ISO datetime format
- list_calendars_tool: List all calendars available to the user (useful for troubleshooting)
- modify_event_tool: Modify existing calendar events (title, time, attendees, description, location)
- delete_event_tool: Delete calendar events permanently
- find_available_slots_tool: Find multiple available time slots within a time range when you have busy times
- parse_specific_time_tool: Parse specific times from queries when you know the general time period

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
- Convert relative time references to proper ISO datetime format using convert_relative_time_tool if needed
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
        
        # After execution_decider or general_conversation, go to END
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
athena_elegant_graph = _create_simple_studio_graph()
# For backward compatibility
# graph = athena_elegant_graph 