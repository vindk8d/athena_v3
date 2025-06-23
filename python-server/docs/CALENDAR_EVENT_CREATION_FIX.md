# Calendar Event Creation Fix

## Problem Analysis

The Google Calendar API event creation was failing with this error:
```
ERROR: HTTP error creating event: <HttpError 403 when requesting https://www.googleapis.com/calendar/v3/calendars/p%23weeknum%40group.v.calendar.google.com/events?alt=json returned "You need to have writer access to this calendar.">
```

### Root Cause
The system was attempting to create events on the first calendar returned by `get_included_calendars()`, which happened to be a read-only calendar (`p#weeknum@group.v.calendar.google.com` - Week Numbers calendar). This calendar has `access_role: "reader"`, meaning no write permissions.

### Calendar Analysis
From the database query, the user had these calendars:
1. `p#weeknum@group.v.calendar.google.com` - Week Numbers (reader) ❌
2. `en.usa#holiday@group.v.calendar.google.com` - US Holidays (reader) ❌
3. `vin.perez@ninjavan.co` - Work calendar (freeBusyReader) ❌
4. **`jose.alvin.perez@gmail.com`** - Vin's Calendar (owner, primary) ✅
5. `en.philippines#holiday@group.v.calendar.google.com` - PH Holidays (reader) ❌
6. `family04025008707235305459@group.calendar.google.com` - Family (owner) ✅

## Solution Implemented

### 1. Enhanced Calendar Prioritization
Modified `get_included_calendars()` in both `agent_main.py` and `tools.py` to return calendars in order of write access priority:

**Priority Order:**
1. **Primary calendars** (`is_primary: true`)
2. **Writable calendars** (`access_role: 'owner'` or `'writer'`)
3. **Read-only calendars** (`access_role: 'reader'`, `'freeBusyReader'`, etc.)

### 2. Enhanced Error Handling
Added robust fallback logic in `create_event_tool()`:
- If the primary calendar fails with permission errors, automatically try the next writable calendar
- Provides clear error messages when no writable calendars are available
- Logs detailed information about calendar selection attempts

### 3. Database Query Enhancement
Updated calendar selection queries to include `access_role` and `is_primary` fields:
```sql
SELECT calendar_id, access_role, is_primary 
FROM calendar_list 
WHERE user_id = ? AND calendar_type = 'google' AND to_include_in_check = true
```

## Additional Fix: Invalid Attendee Email Validation

### Problem
The system was encountering another error after fixing the calendar permissions:
```
ERROR: HTTP error creating event: <HttpError 400 when requesting https://www.googleapis.com/calendar/v3/calendars/jose.alvin.perez%40gmail.com/events?alt=json returned "Invalid attendee email.". Details: "[{'domain': 'global', 'reason': 'invalid', 'message': 'Invalid attendee email.'}]">
```

### Root Cause
When users specified "just me" for attendees, the system was passing `['']` (a list containing an empty string) to the Google Calendar API, which rejects empty email addresses as invalid.

### Solution
Added comprehensive email validation in all calendar event creation functions:

```python
# Filter out empty/invalid attendee emails
if attendees:
    valid_emails = [email.strip() for email in attendees if email and email.strip()]
    if valid_emails:
        event_body['attendees'] = [{'email': email} for email in valid_emails]
```

**Files Modified for Email Validation:**
- `agent_main.py`: Lines 508-511, 736-739, 757, 775, 1029-1031
- `tools.py`: Lines 643-646, 1044, 1051

## Expected Result

After the fix, calendar selection for event creation:
1. **Primary**: `jose.alvin.perez@gmail.com` (owner, primary) - Will be selected first ✅
2. **Fallback**: `family04025008707235305459@group.calendar.google.com` (owner) - Available if primary fails
3. **Read-only calendars**: Still included for availability checking but not for event creation
4. **Attendee emails**: Empty strings are filtered out, preventing "Invalid attendee email" errors

## Files Modified

### `python-server/agent_main.py`
- Enhanced `get_included_calendars()` function (lines 267-302)
- Added fallback logic in `create_event_tool()` (lines 708-738)
- Added attendee email validation in `create_event()` (lines 508-511)
- Added attendee email validation in `create_event_tool()` (lines 736-739)
- Added attendee email validation in `modify_event_tool()` (lines 1029-1031)

### `python-server/tools.py`  
- Enhanced `get_included_calendars()` function (lines 43-78)
- Added attendee email validation in `create_event()` (lines 643-646)
- Added attendee email validation in `CreateEventTool._run()` (lines 1044, 1051)

## Testing the Fix

1. **Restart the Python server** to apply changes
2. **Try creating an event** through the chat interface with "just me" as attendee
3. **Check logs** for calendar selection priority messages:
   ```
   INFO: Found 6 included calendars for user (primary: 1, writable: 1, readonly: 4)
   ```
4. **Verify no attendee email errors** appear in logs

## Additional Improvements

### Future Enhancements
1. **User Calendar Selection**: Allow users to specify which calendar to use for event creation
2. **Calendar Health Check**: Periodically verify calendar write permissions
3. **Smart Calendar Detection**: Automatically detect and prioritize work vs personal calendars based on usage patterns
4. **Better Attendee Parsing**: Enhanced logic to interpret "just me", "no attendees", etc.

### Monitoring
- Monitor logs for `"Successfully created event on fallback calendar"` messages
- Track calendar permission errors to identify problematic calendar configurations
- Alert on `"No writable calendars available"` errors
- Monitor for any remaining "Invalid attendee email" errors

## Prevention
- The enhanced calendar prioritization prevents this issue from recurring
- New calendar integrations will automatically follow the same priority rules
- Users should be notified if they have no writable calendars configured
- Attendee email validation prevents API errors from malformed email addresses 