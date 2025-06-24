# Template Variable Fix for Calendar Execution Error

## Problem Description

The system was failing with the following error in the Calendar Execution Node:

```
ERROR:agent_main:Calendar execution error: "Input to ChatPromptTemplate is missing variables {'colleague_nickname', 'user_nickname'}.  Expected: ['agent_scratchpad', 'colleague_nickname', 'messages', 'user_nickname'] Received: ['messages', 'intermediate_steps', 'agent_scratchpad']
```

## Root Cause

The issue was in the `_create_execution_decider()` method in `agent_main.py`. The ChatPromptTemplate system prompt contained hardcoded template variable references like `{user_nickname}` and `{colleague_nickname}`, but these variables were not being passed to the agent executor when invoked.

## Solution

Removed the template variable references from the execution_prompt system message in the `_create_execution_decider()` method. The personalization is already properly handled in the `_calendar_execution_node()` method, which:

1. Fetches user and colleague information from the cache
2. Creates personalized SystemMessage objects with the actual names/nicknames
3. Inserts these messages into the conversation context before invoking the agent executor

## Changes Made

- **File**: `python-server/agent_main.py`
- **Method**: `_create_execution_decider()`
- **Change**: Replaced template variables like `{user_nickname}` and `{colleague_nickname}` with generic placeholders like `[user]` and `[colleague]` in the system prompt text

## Impact

- ✅ Eliminates the ChatPromptTemplate missing variables error
- ✅ Maintains proper personalization through the calendar execution node's context injection
- ✅ No functional changes to the agent's behavior
- ✅ All existing personalization logic remains intact

## Technical Notes

The calendar execution node already creates personalized system messages for different interaction contexts:
- `clarification_answer`: Adds context-aware system messages
- `general_conversation`: Adds introduction and greeting context  
- Other intents: Adds extraction and workflow context

This approach is more flexible than hardcoding template variables in the base prompt template. 