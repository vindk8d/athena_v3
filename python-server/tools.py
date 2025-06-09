# Import necessary modules and types
from typing import List, Dict, Any, Optional, Tuple  # Import types for type hinting
from langchain.tools import BaseTool  # Import BaseTool for creating custom tools
from pydantic import BaseModel, Field  # Import for creating data models and fields
from datetime import datetime, timedelta  # Import for date and time operations
import json  # Import for JSON operations (not used in this snippet)
import logging  # Import for logging functionality
from google.oauth2.credentials import Credentials  # Import for handling OAuth credentials
from googleapiclient.discovery import build  # Import for building Google API client
from googleapiclient.errors import HttpError  # Import for handling Google API errors
import pytz  # Import for timezone operations
import os  # Import for environment variables
from google.auth.transport.requests import Request  # Import for refreshing access tokens
from supabase import create_client, Client  # Import for database operations

# Set up logging
logger = logging.getLogger(__name__)  # Create a logger instance for this module

# Initialize Supabase client for database operations
def get_supabase_client():
    """Get Supabase client for database operations."""
    supabase_url = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    supabase_key = os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")
    
    if not supabase_url or not supabase_key:
        logger.error("Supabase credentials not found in environment variables")
        return None
    
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

# Define base input model for calendar tools
class CalendarToolsInput(BaseModel):
    """Base input model for calendar tools."""
    pass  # This is an empty base class for other input models to inherit from

# Define input model for checking availability
class CheckAvailabilityInput(BaseModel):
    """Input model for checking calendar availability."""
    start_datetime: str = Field(description="Start datetime in ISO format with timezone (e.g., '2024-01-15T09:00:00+08:00')")
    end_datetime: str = Field(description="End datetime in ISO format with timezone (e.g., '2024-01-15T10:00:00+08:00')")
    duration_minutes: Optional[int] = Field(default=30, description="Meeting duration in minutes for context")

# Define input model for getting events
class GetEventsInput(BaseModel):
    """Input model for getting calendar events."""
    start_datetime: str = Field(description="Start datetime in ISO format with timezone")
    end_datetime: str = Field(description="End datetime in ISO format with timezone")

# Define input model for creating events
class CreateEventInput(BaseModel):
    """Input model for creating calendar events."""
    title: str = Field(description="Event title/subject")
    start_datetime: str = Field(description="Start datetime in ISO format with timezone")
    end_datetime: str = Field(description="End datetime in ISO format with timezone")
    attendee_emails: Optional[List[str]] = Field(default=[], description="List of attendee email addresses")
    description: Optional[str] = Field(default="", description="Event description")
    location: Optional[str] = Field(default="", description="Event location")

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

def set_calendar_service(access_token: str, refresh_token: str = None):
    """Set the global calendar service instance."""
    global _calendar_service
    _calendar_service = CalendarService(access_token, refresh_token)

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
    description = "Get events from the user's calendars for a date range. Useful for checking what meetings are scheduled."
    args_schema = GetEventsInput
    
    def _run(self, start_datetime: str, end_datetime: str) -> str:
        """Execute the tool."""
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
            
        except Exception as e:
            logger.error(f"Error getting events: {e}")
            return f"Error getting events: {str(e)}"

class CheckAvailabilityTool(BaseTool):
    """Tool to check availability across user's configured calendars."""
    
    name = "check_availability"
    description = "Check if a time slot is free across the user's configured calendars. Requires start_datetime and end_datetime in ISO format with timezone."
    args_schema = CheckAvailabilityInput
    
    def _run(self, start_datetime: str, end_datetime: str, duration_minutes: int = 30) -> str:
        """Execute the tool."""
        try:
            user_id = get_current_user_id()
            calendar_ids = get_included_calendars(user_id)
            
            if not calendar_ids:
                return "No calendars configured for availability checking. Please configure calendars in the web interface."
            
            service = get_calendar_service()
            availability = service.check_availability(start_datetime, end_datetime, calendar_ids)
            
            if availability['is_free']:
                return f"✅ Time slot {start_datetime} to {end_datetime} is FREE across all configured calendars"
            else:
                result = f"❌ Time slot {start_datetime} to {end_datetime} has CONFLICTS:\n"
                for conflict in availability['conflicts']:
                    result += f"- Busy from {conflict['start']} to {conflict['end']}\n"
                return result
            
        except Exception as e:
            logger.error(f"Error checking availability: {e}")
            return f"Error checking availability: {str(e)}"

class CreateEventTool(BaseTool):
    """Tool to create a new calendar event on the user's primary calendar."""
    
    name = "create_event"
    description = "Create a new calendar event on the user's primary calendar. Use this to schedule meetings after confirming availability."
    args_schema = CreateEventInput
    
    def _run(self, title: str, start_datetime: str, end_datetime: str, 
            attendee_emails: List[str] = None, description: str = "", location: str = "") -> str:
        """Execute the tool."""
        try:
            user_id = get_current_user_id()
            calendar_ids = get_included_calendars(user_id)
            
            if not calendar_ids:
                return "No calendars configured for creating events. Please configure calendars in the web interface."
            
            # Use the first configured calendar (usually primary) for creating events
            primary_calendar = calendar_ids[0]
            
            service = get_calendar_service()
            
            # Extract timezone from start_datetime
            timezone = "UTC"
            if '+' in start_datetime:
                timezone_offset = start_datetime.split('+')[1]
                timezone = f"UTC+{timezone_offset}"
            elif 'T' in start_datetime and start_datetime.endswith('Z'):
                timezone = "UTC"
            
            event = service.create_event(
                primary_calendar, title, description, start_datetime, 
                end_datetime, timezone, attendee_emails or [], location
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
            logger.error(f"Error creating event: {e}")
            return f"Error creating event: {str(e)}"

# Tool instances for use in agent (removed ListCalendarsTool as it's no longer needed)
calendar_tools = [
    GetEventsTool(),
    CheckAvailabilityTool(),
    CreateEventTool()
]