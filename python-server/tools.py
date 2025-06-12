# Import necessary modules and types
from typing import List, Dict, Any, Optional, Tuple  # Import types for type hinting
from langchain.tools import BaseTool  # Import BaseTool for creating custom tools
from pydantic import BaseModel, Field  # Import for creating data models and fields
from datetime import datetime, timedelta, timezone  # Import for date and time operations
import json  # Import for JSON operations (not used in this snippet)
import logging  # Import for logging functionality
from google.oauth2.credentials import Credentials  # Import for handling OAuth credentials
from googleapiclient.discovery import build  # Import for building Google API client
from googleapiclient.errors import HttpError  # Import for handling Google API errors
import pytz  # Import for timezone operations
import os  # Import for environment variables
from google.auth.transport.requests import Request  # Import for refreshing access tokens
from supabase import create_client, Client  # Import for database operations
from langchain.schema import HumanMessage  # Import for LLM interaction

# Set up logging
logger = logging.getLogger(__name__)  # Create a logger instance for this module

# Global LLM instance for availability mode detection (will be set by agent)
_llm_instance = None

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
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")  # Use service role key for backend operations
    
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

def parse_relative_time_reference(time_ref: str, user_timezone: str = "UTC", base_datetime: datetime = None) -> Tuple[datetime, datetime]:
    """Parse relative time references like 'tomorrow', 'next week', etc. into datetime ranges."""
    try:
        if base_datetime is None:
            base_datetime = datetime.now(pytz.timezone(user_timezone))
        
        # Ensure base_datetime has timezone info
        if base_datetime.tzinfo is None:
            base_datetime = pytz.timezone(user_timezone).localize(base_datetime)
        
        time_ref_lower = time_ref.lower().strip()
        
        if time_ref_lower in ['today']:
            start = base_datetime.replace(hour=8, minute=0, second=0, microsecond=0)  # 8 AM
            end = base_datetime.replace(hour=18, minute=0, second=0, microsecond=0)   # 6 PM
            
        elif time_ref_lower in ['tomorrow']:
            tomorrow = base_datetime + timedelta(days=1)
            start = tomorrow.replace(hour=8, minute=0, second=0, microsecond=0)
            end = tomorrow.replace(hour=18, minute=0, second=0, microsecond=0)
            
        elif time_ref_lower in ['next week', 'next_week']:
            # Find next Monday
            days_ahead = 7 - base_datetime.weekday()  # Monday is 0
            if days_ahead <= 0:  # Already next week
                days_ahead += 7
            next_monday = base_datetime + timedelta(days=days_ahead)
            start = next_monday.replace(hour=8, minute=0, second=0, microsecond=0)
            end = (next_monday + timedelta(days=4)).replace(hour=18, minute=0, second=0, microsecond=0)  # Friday 6 PM
            
        elif time_ref_lower in ['this week', 'this_week']:
            # Start from next business day if it's weekend, otherwise today
            if base_datetime.weekday() >= 5:  # Weekend
                days_ahead = 7 - base_datetime.weekday()
                start_day = base_datetime + timedelta(days=days_ahead)
            else:
                start_day = base_datetime
            
            start = start_day.replace(hour=8, minute=0, second=0, microsecond=0)
            # End of this work week (Friday)
            days_to_friday = 4 - start_day.weekday()
            if days_to_friday < 0:
                days_to_friday += 7
            end_day = start_day + timedelta(days=days_to_friday)
            end = end_day.replace(hour=18, minute=0, second=0, microsecond=0)
            
        elif time_ref_lower in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']:
            weekdays = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
            target_weekday = weekdays.index(time_ref_lower)
            days_ahead = target_weekday - base_datetime.weekday()
            if days_ahead <= 0:  # Target day already happened this week
                days_ahead += 7
            target_day = base_datetime + timedelta(days=days_ahead)
            start = target_day.replace(hour=8, minute=0, second=0, microsecond=0)
            end = target_day.replace(hour=18, minute=0, second=0, microsecond=0)
            
        else:
            # Default to today if we can't parse the reference
            logger.warning(f"Could not parse time reference '{time_ref}', defaulting to today")
            start = base_datetime.replace(hour=8, minute=0, second=0, microsecond=0)
            end = base_datetime.replace(hour=18, minute=0, second=0, microsecond=0)
        
        logger.info(f"Parsed '{time_ref}' to range: {start.isoformat()} - {end.isoformat()}")
        return start, end
        
    except Exception as e:
        logger.error(f"Error parsing time reference '{time_ref}': {e}")
        # Fallback to today
        fallback_start = base_datetime.replace(hour=8, minute=0, second=0, microsecond=0)
        fallback_end = base_datetime.replace(hour=18, minute=0, second=0, microsecond=0)
        return fallback_start, fallback_end

async def determine_availability_mode(query: str, llm_instance=None) -> Dict[str, Any]:
    """Use LLM to determine if this is a timespan inquiry or specific slot inquiry."""
    try:
        if llm_instance is None:
            llm_instance = get_llm_instance()
        
        if llm_instance is None:
            logger.warning("No LLM instance available, using fallback mode detection")
            return _determine_availability_mode_fallback(query)
        
        mode_prompt = f"""Analyze this availability inquiry and determine the mode. Return ONLY valid JSON:

Query: "{query}"

Determine the inquiry type:
- "timespan_inquiry": User wants to see available slots within a time period (e.g., "tomorrow", "next week", "what's free today")
- "specific_slot_inquiry": User wants to check if a specific time slot is available (e.g., "2 PM tomorrow", "Monday at 10 AM")

Also extract:
- temporal_reference: The time reference mentioned (e.g., "tomorrow", "next week", "monday", "2 PM tomorrow")
- has_specific_time: boolean - does the query mention a specific time?
- suggested_duration: meeting duration in minutes if mentioned or implied (default: 30)

Response format:
{{"mode": "timespan_inquiry", "temporal_reference": "tomorrow", "has_specific_time": false, "suggested_duration": 30, "confidence": 0.9}}"""

        response = await llm_instance.ainvoke([HumanMessage(content=mode_prompt)])
        
        # Parse LLM response
        response_text = response.content.strip()
        if not response_text.startswith('{'):
            start = response_text.find('{')
            end = response_text.rfind('}') + 1
            if start >= 0 and end > start:
                response_text = response_text[start:end]
        
        mode_analysis = json.loads(response_text)
        
        # Validate the mode
        valid_modes = ["timespan_inquiry", "specific_slot_inquiry"]
        if mode_analysis.get("mode") not in valid_modes:
            logger.warning(f"Invalid mode from LLM: {mode_analysis.get('mode')}, using fallback")
            return _determine_availability_mode_fallback(query)
        
        logger.info(f"🧠 LLM availability mode analysis: {mode_analysis}")
        return mode_analysis
        
    except Exception as e:
        logger.error(f"❌ LLM availability mode detection failed: {e}")
        return _determine_availability_mode_fallback(query)

def _determine_availability_mode_fallback(query: str) -> Dict[str, Any]:
    """Fallback keyword-based mode detection."""
    query_lower = query.lower()
    
    # Check for specific time indicators
    specific_time_indicators = [
        'at ', ' am', ' pm', ':', 'o\'clock', 'noon', 'midnight',
        'morning', 'afternoon', 'evening', 'night'
    ]
    
    has_specific_time = any(indicator in query_lower for indicator in specific_time_indicators)
    
    # Extract temporal reference
    temporal_keywords = {
        'today': 'today', 'tomorrow': 'tomorrow', 'yesterday': 'yesterday',
        'next week': 'next_week', 'this week': 'this_week',
        'monday': 'monday', 'tuesday': 'tuesday', 'wednesday': 'wednesday',
        'thursday': 'thursday', 'friday': 'friday', 'saturday': 'saturday', 'sunday': 'sunday'
    }
    
    temporal_reference = None
    for keyword, value in temporal_keywords.items():
        if keyword in query_lower:
            temporal_reference = value
            break
    
    # Determine mode based on analysis
    if has_specific_time and temporal_reference:
        mode = "specific_slot_inquiry"
    elif temporal_reference:
        mode = "timespan_inquiry"
    else:
        mode = "timespan_inquiry"  # Default to timespan for safety
    
    return {
        "mode": mode,
        "temporal_reference": temporal_reference or "today",
        "has_specific_time": has_specific_time,
        "suggested_duration": 30,
        "confidence": 0.6
    }

def parse_specific_time_from_query(query: str, temporal_reference: str, user_timezone: str, base_datetime: datetime) -> Tuple[datetime, datetime]:
    """Parse specific time from query when in specific_slot_inquiry mode."""
    try:
        # Start with the temporal reference range
        start_datetime, end_datetime = parse_relative_time_reference(temporal_reference, user_timezone, base_datetime)
        
        query_lower = query.lower()
        
        # Try to extract specific time patterns
        import re
        
        # Pattern for "2 PM", "14:00", "2:30 PM", etc.
        time_patterns = [
            r'(\d{1,2}):(\d{2})\s*(am|pm)?',  # 2:30 PM, 14:30
            r'(\d{1,2})\s*(am|pm)',           # 2 PM, 2AM
            r'(\d{1,2})\s*o\'?clock',         # 2 o'clock
        ]
        
        specific_time = None
        for pattern in time_patterns:
            match = re.search(pattern, query_lower)
            if match:
                hour = int(match.group(1))
                minute = int(match.group(2)) if len(match.groups()) > 1 and match.group(2) else 0
                ampm = match.group(3) if len(match.groups()) > 2 else None
                
                # Convert to 24-hour format
                if ampm:
                    if ampm == 'pm' and hour != 12:
                        hour += 12
                    elif ampm == 'am' and hour == 12:
                        hour = 0
                
                # Create the specific datetime
                specific_time = start_datetime.replace(hour=hour, minute=minute, second=0, microsecond=0)
                break
        
        # Check for named times
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
            # Default 30-minute duration for specific time slots
            end_time = specific_time + timedelta(minutes=30)
            logger.info(f"Parsed specific time from '{query}': {specific_time.isoformat()} to {end_time.isoformat()}")
            return specific_time, end_time
        else:
            # Fallback to the temporal reference range
            logger.info(f"Could not parse specific time from '{query}', using temporal reference range")
            return start_datetime, end_datetime
            
    except Exception as e:
        logger.error(f"Error parsing specific time from query '{query}': {e}")
        # Fallback to temporal reference
        return parse_relative_time_reference(temporal_reference, user_timezone, base_datetime)

def find_available_slots(busy_times: List[Dict], start_datetime: datetime, end_datetime: datetime, slot_duration_minutes: int = 30) -> List[Dict[str, str]]:
    """Find available time slots within a time range, avoiding busy periods."""
    try:
        available_slots = []
        
        # Convert busy times to datetime objects for comparison
        busy_periods = []
        for busy in busy_times:
            try:
                busy_start = datetime.fromisoformat(busy['start'].replace('Z', '+00:00'))
                busy_end = datetime.fromisoformat(busy['end'].replace('Z', '+00:00'))
                busy_periods.append((busy_start, busy_end))
            except Exception as e:
                logger.warning(f"Could not parse busy time: {busy}, error: {e}")
                continue
        
        # Sort busy periods by start time
        busy_periods.sort(key=lambda x: x[0])
        
        # Generate time slots every 30 minutes within business hours
        current_time = start_datetime
        slot_duration = timedelta(minutes=slot_duration_minutes)
        
        while current_time + slot_duration <= end_datetime:
            slot_end = current_time + slot_duration
            
            # Check if this slot conflicts with any busy period
            is_free = True
            for busy_start, busy_end in busy_periods:
                # Check if there's any overlap
                if not (slot_end <= busy_start or current_time >= busy_end):
                    is_free = False
                    break
            
            if is_free:
                available_slots.append({
                    'start': current_time.isoformat(),
                    'end': slot_end.isoformat(),
                    'duration_minutes': slot_duration_minutes
                })
            
            # Move to next slot (30-minute intervals)
            current_time += timedelta(minutes=30)
        
        return available_slots
        
    except Exception as e:
        logger.error(f"Error finding available slots: {e}")
        return []

# Define base input model for calendar tools
class CalendarToolsInput(BaseModel):
    """Base input model for calendar tools."""
    pass  # This is an empty base class for other input models to inherit from

# Enhanced input model for checking availability with mode support
class CheckAvailabilityInput(BaseModel):
    """Input model for checking calendar availability with enhanced mode support."""
    query: str = Field(description="Natural language availability query (e.g., 'what slots are available tomorrow?', 'is 2 PM free on Monday?')")
    duration_minutes: Optional[int] = Field(default=30, description="Preferred meeting duration in minutes for slot finding")
    
    class Config:
        json_schema_extra = {
            "example": {
                "query": "what slots are available tomorrow?",
                "duration_minutes": 30
            }
        }

# Define input model for getting events
class GetEventsInput(BaseModel):
    """Input model for getting calendar events."""
    start_datetime: str = Field(description="Start datetime in ISO format with timezone")
    end_datetime: str = Field(description="End datetime in ISO format with timezone")
    
    class Config:
        json_schema_extra = {
            "example": {
                "start_datetime": "2024-01-15T00:00:00+08:00",
                "end_datetime": "2024-01-15T23:59:59+08:00"
            }
        }

# Define input model for creating events
class CreateEventInput(BaseModel):
    """Input model for creating calendar events."""
    title: str = Field(description="Event title/subject")
    start_datetime: str = Field(description="Start datetime in ISO format with timezone")
    end_datetime: str = Field(description="End datetime in ISO format with timezone")
    attendee_emails: Optional[List[str]] = Field(default=[], description="List of attendee email addresses")
    description: Optional[str] = Field(default="", description="Event description")
    location: Optional[str] = Field(default="", description="Event location")
    
    class Config:
        json_schema_extra = {
            "example": {
                "title": "Team Meeting",
                "start_datetime": "2024-01-15T09:00:00+08:00",
                "end_datetime": "2024-01-15T10:00:00+08:00",
                "attendee_emails": ["colleague@example.com"],
                "description": "Weekly team sync",
                "location": "Conference Room A"
            }
        }

# Define CalendarService class for interacting with Google Calendar API
class CalendarService:
    """Google Calendar API service wrapper."""
    
    def __init__(self, access_token: str, refresh_token: str = None):
        """Initialize calendar service with OAuth tokens."""
        try:
            # Create credentials object using the provided tokens
            self.credentials = Credentials(
                token=access_token,
                refresh_token=refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=os.getenv('GOOGLE_CLIENT_ID'),  # Add client credentials for refresh
                client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
            )
            
            # Build the calendar service using the credentials
            self.service = build('calendar', 'v3', credentials=self.credentials)
            logger.info("Calendar service initialized successfully")  # Log successful initialization
            
        except Exception as e:
            logger.error(f"Error initializing calendar service: {e}")  # Log any errors during initialization
            raise  # Re-raise the exception
    
    def refresh_token_if_needed(self):
        """Refresh the access token if it's expired or about to expire."""
        try:
            if self.credentials.expired and self.credentials.refresh_token:
                logger.info("Access token expired, refreshing...")
                self.credentials.refresh(Request())
                logger.info("Access token refreshed successfully")
                return {
                    'access_token': self.credentials.token,
                    'refresh_token': self.credentials.refresh_token,
                    'expires_at': self.credentials.expiry.isoformat() if self.credentials.expiry else None
                }
            return None
        except Exception as e:
            logger.error(f"Error refreshing token: {e}")
            raise
    
    def list_calendars(self) -> List[Dict[str, Any]]:
        """List all calendars for the authenticated user."""
        try:
            # Fetch the list of calendars from the Google Calendar API
            calendar_list = self.service.calendarList().list().execute()
            calendars = []
            
            # Process each calendar item and extract relevant information
            for calendar_item in calendar_list.get('items', []):
                calendars.append({
                    'id': calendar_item['id'],
                    'summary': calendar_item.get('summary', ''),
                    'description': calendar_item.get('description', ''),
                    'timezone': calendar_item.get('timeZone', 'UTC'),
                    'primary': calendar_item.get('primary', False),
                    'access_role': calendar_item.get('accessRole', 'reader')
                })
            
            return calendars  # Return the list of processed calendars
            
        except HttpError as e:
            logger.error(f"HTTP error listing calendars: {e}")  # Log HTTP errors
            raise
        except Exception as e:
            logger.error(f"Error listing calendars: {e}")  # Log general errors
            raise
    
    def get_events(self, calendar_id: str, start_date: str, end_date: str, timezone: str = "UTC") -> List[Dict[str, Any]]:
        """Get events from a calendar within a date range."""
        try:
            # Convert dates to RFC3339 format with timezone
            start_time = f"{start_date}T00:00:00.000000Z"
            end_time = f"{end_date}T23:59:59.999999Z"
            
            # Fetch events from the Google Calendar API
            events_result = self.service.events().list(
                calendarId=calendar_id,
                timeMin=start_time,
                timeMax=end_time,
                singleEvents=True,
                orderBy='startTime',
                timeZone=timezone
            ).execute()
            
            events = []
            # Process each event and extract relevant information
            for event in events_result.get('items', []):
                # Parse start and end times
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
            
            return events  # Return the list of processed events
            
        except HttpError as e:
            logger.error(f"HTTP error getting events: {e}")  # Log HTTP errors
            raise
        except Exception as e:
            logger.error(f"Error getting events: {e}")  # Log general errors
            raise
    
    def check_availability(self, start_datetime: str, end_datetime: str, calendar_ids: List[str]) -> Dict[str, Any]:
        """Check availability across multiple calendars."""
        try:
            # Prepare the request body for the freebusy query
            body = {
                'timeMin': start_datetime,
                'timeMax': end_datetime,
                'items': [{'id': cal_id} for cal_id in calendar_ids]
            }
            
            # Execute the freebusy query
            freebusy_result = self.service.freebusy().query(body=body).execute()
            
            # Initialize the availability dictionary
            availability = {
                'time_period': {
                    'start': start_datetime,
                    'end': end_datetime
                },
                'calendars': {},
                'is_free': True,
                'conflicts': []
            }
            
            # Process the freebusy result for each calendar
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
            
            return availability  # Return the processed availability information
            
        except HttpError as e:
            logger.error(f"HTTP error checking availability: {e}")  # Log HTTP errors
            raise
        except Exception as e:
            logger.error(f"Error checking availability: {e}")  # Log general errors
            raise
    
    def create_event(self, calendar_id: str, title: str, description: str, 
                    start_datetime: str, end_datetime: str, timezone: str = "UTC",
                    attendees: List[str] = None, location: str = "") -> Dict[str, Any]:
        """Create a new calendar event."""
        try:
            # Prepare the event body
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
            
            # Add attendees if provided
            if attendees:
                event_body['attendees'] = [{'email': email} for email in attendees]
            
            # Insert the event into the calendar
            event = self.service.events().insert(
                calendarId=calendar_id,
                body=event_body
            ).execute()
            
            # Return relevant information about the created event
            return {
                'id': event['id'],
                'summary': event.get('summary'),
                'start': event.get('start', {}).get('dateTime'),
                'end': event.get('end', {}).get('dateTime'),
                'html_link': event.get('htmlLink'),
                'status': event.get('status')
            }
            
        except HttpError as e:
            logger.error(f"HTTP error creating event: {e}")  # Log HTTP errors
            raise
        except Exception as e:
            logger.error(f"Error creating event: {e}")  # Log general errors
            raise

# Global calendar service instance and user context (will be set when processing requests)
_calendar_service: Optional[CalendarService] = None
_current_user_id: Optional[str] = None

def set_calendar_service(access_token: str, refresh_token: str = None, user_id: str = None, llm_instance=None):
    """Set the global calendar service instance and LLM instance for tools."""
    global _calendar_service
    _calendar_service = CalendarService(access_token, refresh_token)
    
    # Set LLM instance for availability mode detection if provided
    if llm_instance:
        set_llm_instance(llm_instance)
        logger.info("LLM instance set for intelligent availability mode detection")
    
    # Get the primary calendar's timezone and update user_details
    try:
        calendars = _calendar_service.list_calendars()
        primary_calendar = next((cal for cal in calendars if cal.get('primary', False)), None)
        
        if primary_calendar and primary_calendar.get('timezone'):
            # Update user_details with the primary calendar's timezone
            from supabase import create_client
            import os
            
            supabase = create_client(
                os.getenv('SUPABASE_URL'),
                os.getenv('SUPABASE_SERVICE_ROLE_KEY')  # Use service role key for backend operations
            )
            
            # Use provided user_id or get from global context
            current_user_id = user_id or get_current_user_id()
            if current_user_id:
                supabase.table('user_details').update({
                    'default_timezone': primary_calendar['timezone'],
                    'updated_at': datetime.utcnow().isoformat()
                }).eq('user_id', current_user_id).execute()
                logger.info(f"Updated user's default timezone to {primary_calendar['timezone']}")
            else:
                logger.warning("Could not update timezone: No user ID available")
    except Exception as e:
        logger.error(f"Error updating user's default timezone: {e}")

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

# LangChain Tools

class ListCalendarsTool(BaseTool):
    """Tool to list all calendars for the authenticated user."""
    
    name = "list_calendars"
    description = "List all calendars for the user. Use this to see available calendars before checking events or availability. No arguments needed."
    args_schema = CalendarToolsInput
    
    def _run(self, *args, **kwargs) -> str:
        """List all calendars for the authenticated user."""
        try:
            calendar_service = get_calendar_service()
            calendars = calendar_service.list_calendars()
            
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

class GetEventsTool(BaseTool):
    """Tool to get events from user's calendars for a date range."""
    
    name = "get_events"
    description = """Get events from the user's calendars for a date range. 
    REQUIRED PARAMETERS: start_datetime and end_datetime in ISO format with timezone.
    NEVER call this tool without both parameters properly formatted."""
    args_schema = GetEventsInput
    
    def _run(self, start_datetime: str, end_datetime: str) -> str:
        """Execute the tool with enhanced validation."""
        try:
            # Validate required inputs
            start_datetime = validate_datetime_input(start_datetime, "start_datetime")
            end_datetime = validate_datetime_input(end_datetime, "end_datetime")
            
            logger.info(f"GetEventsTool called with start_datetime={start_datetime}, end_datetime={end_datetime}")
            
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
            logger.error(f"Validation error in GetEventsTool: {e}")
            return f"❌ Validation Error: {str(e)}. Please provide valid start_datetime and end_datetime in ISO format with timezone."
        except Exception as e:
            logger.error(f"Error getting events: {e}")
            return f"Error getting events: {str(e)}"

def calculate_end_datetime(start_datetime: str, duration_minutes: int) -> str:
    """Calculate end datetime from start datetime and duration in minutes."""
    try:
        # Ensure the input datetime has timezone info
        if 'Z' in start_datetime:
            start_datetime = start_datetime.replace('Z', '+00:00')
        
        # Parse the start datetime
        start_dt = datetime.fromisoformat(start_datetime)
        
        # Calculate end datetime
        end_dt = start_dt + timedelta(minutes=duration_minutes)
        
        # Format back to ISO format with timezone
        return end_dt.isoformat()
    except Exception as e:
        logger.error(f"Error calculating end datetime: {e}")
        raise

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

class CheckAvailabilityTool(BaseTool):
    """Tool to intelligently check availability across user's configured calendars with two modes: timespan inquiry and specific slot checking."""
    
    name = "check_availability"
    description = """Intelligently check availability across the user's configured calendars. 
    This tool automatically detects if you're asking for:
    1. Available time slots within a period (e.g., "what slots are free tomorrow?", "show me availability next week")
    2. Whether a specific time is available (e.g., "is 2 PM tomorrow free?", "check Monday at 10 AM")
    
    REQUIRED PARAMETER: query - Natural language availability question
    OPTIONAL PARAMETER: duration_minutes - Meeting duration for slot suggestions (default: 30)
    
    Examples:
    - "What slots are available tomorrow?" 
    - "Is he free next week?"
    - "Check if 2 PM on Monday is available"
    - "Show me free time this afternoon"
    """
    args_schema = CheckAvailabilityInput
    
    async def _arun(self, query: str, duration_minutes: int = 30) -> str:
        """Execute the tool with enhanced async validation and LLM mode detection."""
        try:
            # Validate required inputs
            query = validate_required_string(query, "query")
            
            logger.info(f"CheckAvailabilityTool called with query='{query}', duration_minutes={duration_minutes}")
            
            user_id = get_current_user_id()
            user_timezone = get_user_timezone(user_id)
            calendar_ids = get_included_calendars(user_id)
            
            if not calendar_ids:
                return "No calendars configured for availability checking. Please configure calendars in the web interface."
            
            # Get current datetime in user's timezone
            current_datetime = datetime.now(pytz.timezone(user_timezone))
            logger.info(f"Current datetime ({user_timezone}): {current_datetime.isoformat()}")
            
            # Use LLM to determine availability mode
            mode_analysis = await determine_availability_mode(query, get_llm_instance())
            logger.info(f"Mode analysis result: {mode_analysis}")
            
            # Parse the temporal reference to get datetime range
            temporal_ref = mode_analysis.get('temporal_reference', 'today')
            start_datetime, end_datetime = parse_relative_time_reference(temporal_ref, user_timezone, current_datetime)
            
            # Check if the requested time is in the past
            if start_datetime < current_datetime:
                logger.warning(f"Attempted to check availability for past time: {start_datetime}")
                return f"❌ Cannot check availability for past time. The requested time ({start_datetime.strftime('%Y-%m-%d %H:%M %Z')}) has already passed."
            
            service = get_calendar_service()
            
            if mode_analysis['mode'] == 'timespan_inquiry':
                # Handle timespan inquiry - find available slots
                logger.info(f"Processing timespan inquiry for {temporal_ref}")
                
                # Get busy times for the entire period
                availability = service.check_availability(start_datetime.isoformat(), end_datetime.isoformat(), calendar_ids)
                
                # Find available slots within the timespan
                all_busy_times = availability.get('conflicts', [])
                available_slots = find_available_slots(all_busy_times, start_datetime, end_datetime, duration_minutes)
                
                if not available_slots:
                    result = f"❌ No {duration_minutes}-minute slots available {temporal_ref} ({start_datetime.strftime('%Y-%m-%d %H:%M')} to {end_datetime.strftime('%H:%M %Z')})\n"
                    if all_busy_times:
                        result += "Busy periods:\n"
                        for busy in all_busy_times:
                            busy_start = datetime.fromisoformat(busy['start'].replace('Z', '+00:00'))
                            busy_end = datetime.fromisoformat(busy['end'].replace('Z', '+00:00'))
                            result += f"- {busy_start.strftime('%H:%M')} to {busy_end.strftime('%H:%M')}\n"
                    return result
                else:
                    result = f"✅ Found {len(available_slots)} available {duration_minutes}-minute slots {temporal_ref}:\n"
                    for i, slot in enumerate(available_slots[:8], 1):  # Limit to 8 slots for readability
                        slot_start = datetime.fromisoformat(slot['start'])
                        slot_end = datetime.fromisoformat(slot['end'])
                        result += f"{i}. {slot_start.strftime('%H:%M')} - {slot_end.strftime('%H:%M')}\n"
                    
                    if len(available_slots) > 8:
                        result += f"... and {len(available_slots) - 8} more slots available\n"
                    
                    return result
                    
            elif mode_analysis['mode'] == 'specific_slot_inquiry':
                # Handle specific slot inquiry - check if specific time is free
                logger.info(f"Processing specific slot inquiry for {temporal_ref}")
                
                # Parse the specific time from the query
                slot_start, slot_end = parse_specific_time_from_query(query, temporal_ref, user_timezone, current_datetime)
                
                availability = service.check_availability(slot_start.isoformat(), slot_end.isoformat(), calendar_ids)
                
                if availability['is_free']:
                    return f"✅ Time slot {slot_start.strftime('%Y-%m-%d %H:%M')} to {slot_end.strftime('%H:%M %Z')} is FREE across all configured calendars"
                else:
                    result = f"❌ Time slot {slot_start.strftime('%Y-%m-%d %H:%M')} to {slot_end.strftime('%H:%M %Z')} has CONFLICTS:\n"
                    for conflict in availability['conflicts']:
                        conflict_start = datetime.fromisoformat(conflict['start'].replace('Z', '+00:00'))
                        conflict_end = datetime.fromisoformat(conflict['end'].replace('Z', '+00:00'))
                        result += f"- Busy from {conflict_start.strftime('%H:%M')} to {conflict_end.strftime('%H:%M')}\n"
                    return result
            
        except ValueError as e:
            logger.error(f"Validation error in CheckAvailabilityTool: {e}")
            return f"❌ Validation Error: {str(e)}. Please provide a valid availability query."
        except Exception as e:
            logger.error(f"Error checking availability: {e}")
            return f"Error checking availability: {str(e)}"
    
    def _run(self, query: str, duration_minutes: int = 30) -> str:
        """Synchronous fallback - should not be used when async is available."""
        # This is a fallback for sync execution, but the tool should be used async
        return "❌ This tool requires async execution for LLM-based mode detection. Please use the async version."

class CreateEventTool(BaseTool):
    """Tool to create a new calendar event on the user's primary calendar."""
    
    name = "create_event"
    description = """Create a new calendar event on the user's primary calendar. 
    REQUIRED PARAMETERS: title, start_datetime, and end_datetime.
    NEVER call this tool without all required parameters properly formatted."""
    args_schema = CreateEventInput
    
    def _run(self, title: str, start_datetime: str, end_datetime: str, 
            attendee_emails: List[str] = None, description: str = "", location: str = "") -> str:
        """Execute the tool with enhanced validation."""
        try:
            # Validate required inputs
            title = validate_required_string(title, "title")
            start_datetime = validate_datetime_input(start_datetime, "start_datetime")
            end_datetime = validate_datetime_input(end_datetime, "end_datetime")
            
            logger.info(f"CreateEventTool called with title='{title}', start_datetime={start_datetime}, end_datetime={end_datetime}")
            
            user_id = get_current_user_id()
            user_timezone = get_user_timezone(user_id)
            
            # Get current datetime in user's timezone
            current_datetime = datetime.now(pytz.timezone(user_timezone))
            logger.info(f"Current datetime ({user_timezone}): {current_datetime.isoformat()}")
            
            # Parse the start datetime to check if it's in the past
            start_dt = datetime.fromisoformat(start_datetime)
            logger.info(f"Requested start datetime: {start_dt.isoformat()}")
            
            if start_dt < current_datetime:
                logger.warning(f"Attempted to create event in the past: {start_datetime}")
                return f"❌ Cannot create event in the past: {start_datetime}"
            
            calendar_ids = get_included_calendars(user_id)
            
            if not calendar_ids:
                return "No calendars configured for creating events. Please configure calendars in the web interface."
            
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
            
        except ValueError as e:
            logger.error(f"Validation error in CreateEventTool: {e}")
            return f"❌ Validation Error: {str(e)}. Please provide valid title, start_datetime, and end_datetime."
        except Exception as e:
            logger.error(f"Error creating event: {e}")
            return f"Error creating event: {str(e)}"

def validate_datetime_input(datetime_str: str, field_name: str) -> str:
    """Validate and normalize datetime input."""
    if not datetime_str or not datetime_str.strip():
        raise ValueError(f"{field_name} is required and cannot be empty")
    
    try:
        # Normalize timezone format
        if 'Z' in datetime_str:
            datetime_str = datetime_str.replace('Z', '+00:00')
        
        # Try to parse as ISO datetime
        parsed_dt = datetime.fromisoformat(datetime_str)
        
        # Ensure it has timezone info
        if parsed_dt.tzinfo is None:
            raise ValueError(f"{field_name} must include timezone information")
        
        return datetime_str
    except (ValueError, TypeError) as e:
        raise ValueError(f"{field_name} must be in ISO format with timezone (e.g., '2024-01-15T09:00:00+08:00'). Error: {str(e)}")

def validate_required_string(value: str, field_name: str) -> str:
    """Validate required string field."""
    if not value or not value.strip():
        raise ValueError(f"{field_name} is required and cannot be empty")
    return value.strip()

# Tool instances for use in agent (removed ListCalendarsTool as it's no longer needed)
calendar_tools = [
    GetEventsTool(),
    CheckAvailabilityTool(),
    CreateEventTool()
]