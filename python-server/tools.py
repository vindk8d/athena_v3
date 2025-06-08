from typing import List, Dict, Any, Optional, Tuple
from langchain.tools import BaseTool
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
import json
import logging
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import pytz

logger = logging.getLogger(__name__)

class CalendarToolsInput(BaseModel):
    """Base input model for calendar tools."""
    pass

class ListCalendarsInput(CalendarToolsInput):
    """Input for listing calendars."""
    pass

class GetEventsInput(CalendarToolsInput):
    """Input for getting calendar events."""
    calendar_id: str = Field(description="The calendar ID to get events from")
    start_date: str = Field(description="Start date in ISO format (YYYY-MM-DD)")
    end_date: str = Field(description="End date in ISO format (YYYY-MM-DD)")
    timezone: str = Field(default="UTC", description="Timezone for the events")

class CheckAvailabilityInput(CalendarToolsInput):
    """Input for checking availability."""
    start_datetime: str = Field(description="Start datetime in ISO format")
    end_datetime: str = Field(description="End datetime in ISO format")
    calendar_ids: List[str] = Field(description="List of calendar IDs to check")
    timezone: str = Field(default="UTC", description="Timezone for availability check")

class CreateEventInput(CalendarToolsInput):
    """Input for creating a calendar event."""
    calendar_id: str = Field(description="The calendar ID to create the event in")
    title: str = Field(description="Event title")
    description: str = Field(default="", description="Event description")
    start_datetime: str = Field(description="Start datetime in ISO format")
    end_datetime: str = Field(description="End datetime in ISO format")
    timezone: str = Field(default="UTC", description="Timezone for the event")
    attendees: List[str] = Field(default=[], description="List of attendee email addresses")
    location: str = Field(default="", description="Event location")

class CalendarService:
    """Google Calendar API service wrapper."""
    
    def __init__(self, access_token: str, refresh_token: str = None):
        """Initialize calendar service with OAuth tokens."""
        try:
            # Create credentials object
            self.credentials = Credentials(
                token=access_token,
                refresh_token=refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=None,  # Will be set if needed
                client_secret=None,  # Will be set if needed
            )
            
            # Build the calendar service
            self.service = build('calendar', 'v3', credentials=self.credentials)
            logger.info("Calendar service initialized successfully")
            
        except Exception as e:
            logger.error(f"Error initializing calendar service: {e}")
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
            # Convert dates to RFC3339 format with timezone
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
            # Use freebusy query to check availability
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

# Global calendar service instance (will be set when processing requests)
_calendar_service: Optional[CalendarService] = None

def set_calendar_service(access_token: str, refresh_token: str = None):
    """Set the global calendar service instance."""
    global _calendar_service
    _calendar_service = CalendarService(access_token, refresh_token)

def get_calendar_service() -> CalendarService:
    """Get the global calendar service instance."""
    if _calendar_service is None:
        raise ValueError("Calendar service not initialized. Call set_calendar_service first.")
    return _calendar_service

# LangChain Tools

class ListCalendarsTool(BaseTool):
    """Tool to list all calendars for the authenticated user."""
    
    name = "list_calendars"
    description = "List all calendars for the user. Use this to see available calendars before checking events or availability."
    args_schema = ListCalendarsInput
    
    def _run(self) -> str:
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
    """Tool to get events from a specific calendar."""
    
    name = "get_events"
    description = "Get events from a specific calendar for a date range. Useful for checking what meetings are scheduled."
    args_schema = GetEventsInput
    
    def _run(self, calendar_id: str, start_date: str, end_date: str, timezone: str = "UTC") -> str:
        """Execute the tool."""
        try:
            service = get_calendar_service()
            events = service.get_events(calendar_id, start_date, end_date, timezone)
            
            if not events:
                return f"No events found in calendar {calendar_id} from {start_date} to {end_date}"
            
            result = f"Events in calendar {calendar_id} from {start_date} to {end_date}:\n"
            for event in events:
                result += f"- {event['summary']} ({event['start']} - {event['end']})\n"
                if event['location']:
                    result += f"  Location: {event['location']}\n"
                if event['attendees']:
                    result += f"  Attendees: {', '.join(event['attendees'])}\n"
            
            return result
            
        except Exception as e:
            return f"Error getting events: {str(e)}"

class CheckAvailabilityTool(BaseTool):
    """Tool to check availability across multiple calendars."""
    
    name = "check_availability"
    description = "Check if a time slot is free across multiple calendars. Use this before scheduling meetings."
    args_schema = CheckAvailabilityInput
    
    def _run(self, start_datetime: str, end_datetime: str, calendar_ids: List[str], timezone: str = "UTC") -> str:
        """Execute the tool."""
        try:
            service = get_calendar_service()
            availability = service.check_availability(start_datetime, end_datetime, calendar_ids)
            
            if availability['is_free']:
                return f"✅ Time slot {start_datetime} to {end_datetime} is FREE across all calendars"
            else:
                result = f"❌ Time slot {start_datetime} to {end_datetime} has CONFLICTS:\n"
                for conflict in availability['conflicts']:
                    result += f"- Busy from {conflict['start']} to {conflict['end']}\n"
                return result
            
        except Exception as e:
            return f"Error checking availability: {str(e)}"

class CreateEventTool(BaseTool):
    """Tool to create a new calendar event."""
    
    name = "create_event"
    description = "Create a new calendar event. Use this to schedule meetings after confirming availability."
    args_schema = CreateEventInput
    
    def _run(self, calendar_id: str, title: str, description: str, start_datetime: str, 
            end_datetime: str, timezone: str = "UTC", attendees: List[str] = None, location: str = "") -> str:
        """Execute the tool."""
        try:
            service = get_calendar_service()
            event = service.create_event(
                calendar_id, title, description, start_datetime, 
                end_datetime, timezone, attendees or [], location
            )
            
            result = f"✅ Event created successfully!\n"
            result += f"Title: {event['summary']}\n"
            result += f"Time: {event['start']} to {event['end']}\n"
            result += f"Event ID: {event['id']}\n"
            if event.get('html_link'):
                result += f"Calendar link: {event['html_link']}\n"
            
            return result
            
        except Exception as e:
            return f"Error creating event: {str(e)}"

# Tool instances for use in agent
calendar_tools = [
    ListCalendarsTool(),
    GetEventsTool(),
    CheckAvailabilityTool(),
    CreateEventTool()
] 