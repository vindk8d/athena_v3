# Enhanced Availability Checking - Two Mode System

## Overview

The availability checking system has been enhanced to support two distinct modes:

1. **Timespan Inquiry Mode**: Returns available time slots within a period
2. **Specific Slot Inquiry Mode**: Checks if a specific time slot is available

The system uses an LLM to intelligently determine which mode to use based on the natural language query, with a fallback to keyword-based detection.

## How It Works

### 1. Mode Detection (LLM-Based)

The system analyzes queries like:

```python
# Timespan inquiries
"What slots are available tomorrow?"
"Show me free time next week" 
"Is he available tomorrow?"

# Specific slot inquiries  
"Is 2 PM tomorrow free?"
"Check if Monday at 10 AM is available"
"Is noon today available?"
```

### 2. Time Reference Parsing

Intelligent parsing of relative time references:

- **"today"** → 8 AM to 6 PM today (business hours)
- **"tomorrow"** → 8 AM to 6 PM tomorrow
- **"next week"** → Monday 8 AM to Friday 6 PM next week
- **"monday"** → 8 AM to 6 PM next Monday
- **"this week"** → Remaining business days this week

### 3. Specific Time Extraction

For specific slot inquiries, the system extracts:

- **"2 PM"** → 14:00
- **"10:30 AM"** → 10:30
- **"noon"** → 12:00
- **"afternoon"** → 14:00 (2 PM)
- **"morning"** → 09:00 (9 AM)

## Enhanced CheckAvailabilityTool

### New Interface

```python
# OLD (rigid):
check_availability(
    start_datetime="2024-01-15T09:00:00+08:00",
    end_datetime="2024-01-15T10:00:00+08:00", 
    duration_minutes=30
)

# NEW (natural):
check_availability(
    query="What slots are available tomorrow?",
    duration_minutes=30
)
```

### Mode 1: Timespan Inquiry

**Input**: `"What slots are available tomorrow?"`

**Output**:
```
✅ Found 12 available 30-minute slots tomorrow:
1. 08:00 - 08:30
2. 08:30 - 09:00  
3. 09:00 - 09:30
4. 10:30 - 11:00
5. 11:00 - 11:30
...and 7 more slots available
```

### Mode 2: Specific Slot Inquiry

**Input**: `"Is 2 PM tomorrow free?"`

**Output**:
```
✅ Time slot 2024-01-16 14:00 to 14:30 PST is FREE across all configured calendars
```

or

```
❌ Time slot 2024-01-16 14:00 to 14:30 PST has CONFLICTS:
- Busy from 14:00 to 15:00
```

## Technical Implementation

### 1. LLM Mode Detection

```python
async def determine_availability_mode(query: str, llm_instance=None) -> Dict[str, Any]:
    """Use LLM to determine if this is a timespan inquiry or specific slot inquiry."""
    
    mode_prompt = f"""Analyze this availability inquiry and determine the mode:
    
Query: "{query}"

Determine the inquiry type:
- "timespan_inquiry": User wants to see available slots within a time period
- "specific_slot_inquiry": User wants to check if a specific time slot is available

Return JSON: {{"mode": "timespan_inquiry", "temporal_reference": "tomorrow", ...}}"""
    
    # LLM analysis with fallback to keyword-based detection
```

### 2. Intelligent Time Parsing

```python
def parse_relative_time_reference(time_ref: str, user_timezone: str, base_datetime: datetime):
    """Parse relative time references like 'tomorrow', 'next week', etc."""
    
    if time_ref_lower == 'tomorrow':
        tomorrow = base_datetime + timedelta(days=1)
        start = tomorrow.replace(hour=8, minute=0, second=0, microsecond=0)
        end = tomorrow.replace(hour=18, minute=0, second=0, microsecond=0)
    # ... more parsing logic
```

### 3. Specific Time Extraction

```python
def parse_specific_time_from_query(query: str, temporal_reference: str, user_timezone: str):
    """Parse specific time from query when in specific_slot_inquiry mode."""
    
    # Regex patterns for "2 PM", "14:00", "2:30 PM", etc.
    time_patterns = [
        r'(\d{1,2}):(\d{2})\s*(am|pm)?',  # 2:30 PM, 14:30
        r'(\d{1,2})\s*(am|pm)',           # 2 PM, 2AM
        r'(\d{1,2})\s*o\'?clock',         # 2 o'clock
    ]
    # ... parsing logic
```

## Benefits

### 1. User Experience
- **Natural language interface**: Users ask questions naturally
- **No format requirements**: No need to provide ISO datetime strings
- **Intelligent interpretation**: System understands context and intent

### 2. Robustness  
- **LLM-powered**: Sophisticated understanding of natural language
- **Fallback mechanisms**: Keyword-based detection if LLM fails
- **Error handling**: Graceful degradation with helpful error messages

### 3. Flexibility
- **Two distinct modes**: Handles different types of availability questions
- **Timezone aware**: Automatically handles user's timezone
- **Configurable duration**: Supports different meeting lengths

## Example Interactions

### Before (Error-Prone)
```
User: "What slots is he available tomorrow?"
Agent: "I need the specific date for tomorrow and the preferred meeting duration to check availability. Could you please provide me with the date you have in mind for the meeting?"
```

### After (Intelligent)
```
User: "What slots is he available tomorrow?"
Agent: "✅ Found 8 available 30-minute slots tomorrow (2024-01-16):
1. 08:00 - 08:30
2. 09:00 - 09:30  
3. 10:30 - 11:00
4. 14:00 - 14:30
5. 15:00 - 15:30
...and 3 more slots available

Would any of these times work for your meeting?"
```

## Integration Points

### 1. Agent Setup
```python
# In main.py - set LLM instance for tools
agent = get_agent()
set_calendar_service(access_token, refresh_token, user_id, agent.llm)
```

### 2. Tool Usage
```python
# The agent can now handle natural language availability queries
# CheckAvailabilityTool automatically detects mode and processes accordingly
```

### 3. Async Support
```python
# Tool is now async to support LLM mode detection
async def _arun(self, query: str, duration_minutes: int = 30) -> str:
    mode_analysis = await determine_availability_mode(query, get_llm_instance())
    # ... process based on detected mode
```

This enhancement makes the availability checking much more robust and user-friendly, eliminating the need for users to provide specific datetime formats and enabling natural conversation about scheduling. 