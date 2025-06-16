#!/usr/bin/env python3
"""
Test script for the enhanced executive assistant agent with robust error prevention.
This script demonstrates the validation and error handling improvements.
"""

import asyncio
import logging
from datetime import datetime
import pytz
from agent import ExecutiveAssistantAgent, MeetingInfoExtractor, ToolInputValidator
from unittest.mock import Mock

# Set up logging to see the enhanced debugging output
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def test_meeting_info_extraction():
    """Test the MeetingInfoExtractor with various inputs."""
    logger.info("=== TESTING MEETING INFO EXTRACTION ===")
    
    current_datetime = datetime.now(pytz.timezone('UTC'))
    
    test_cases = [
        {
            "message": "Can we schedule a meeting for tomorrow at 2 PM for 30 minutes?",
            "expected_fields": ["date", "time", "duration"]
        },
        {
            "message": "I'd like to discuss the project with you.",
            "expected_fields": ["title"]
        },
        {
            "message": "Meeting about the quarterly review next week",
            "expected_fields": ["title", "date"]
        },
        {
            "message": "Can we meet?",
            "expected_fields": []
        }
    ]
    
    for i, case in enumerate(test_cases):
        logger.info(f"\n--- Test Case {i + 1} ---")
        logger.info(f"Message: {case['message']}")
        
        details = MeetingInfoExtractor.extract_meeting_details(
            case["message"], [], current_datetime, 'UTC'
        )
        
        logger.info(f"Extracted details: {details}")
        logger.info(f"Missing required: {details.get('missing_required', [])}")

def test_tool_input_validation():
    """Test the ToolInputValidator with various inputs."""
    logger.info("\n=== TESTING TOOL INPUT VALIDATION ===")
    
    test_cases = [
        {
            "tool": "check_availability",
            "inputs": {
                "start_datetime": "2024-01-15T09:00:00+08:00",
                "end_datetime": "2024-01-15T10:00:00+08:00"
            },
            "should_be_valid": True
        },
        {
            "tool": "check_availability",
            "inputs": {
                "start_datetime": "",
                "end_datetime": "2024-01-15T10:00:00+08:00"
            },
            "should_be_valid": False
        },
        {
            "tool": "create_event",
            "inputs": {
                "title": "Team Meeting",
                "start_datetime": "2024-01-15T09:00:00+08:00",
                "end_datetime": "2024-01-15T10:00:00+08:00"
            },
            "should_be_valid": True
        },
        {
            "tool": "create_event",
            "inputs": {
                "title": "",
                "start_datetime": "2024-01-15T09:00:00+08:00",
                "end_datetime": "2024-01-15T10:00:00+08:00"
            },
            "should_be_valid": False
        }
    ]
    
    for i, case in enumerate(test_cases):
        logger.info(f"\n--- Validation Test {i + 1} ---")
        logger.info(f"Tool: {case['tool']}")
        logger.info(f"Inputs: {case['inputs']}")
        
        if case["tool"] == "check_availability":
            result = ToolInputValidator.validate_check_availability(
                case["inputs"].get("start_datetime", ""),
                case["inputs"].get("end_datetime", "")
            )
        elif case["tool"] == "create_event":
            result = ToolInputValidator.validate_create_event(
                case["inputs"].get("title", ""),
                case["inputs"].get("start_datetime", ""),
                case["inputs"].get("end_datetime", "")
            )
        
        logger.info(f"Validation result: {result}")
        logger.info(f"Expected valid: {case['should_be_valid']}, Got valid: {result['is_valid']}")

def simulate_agent_conversation():
    """Simulate various conversation scenarios to test the enhanced agent."""
    logger.info("\n=== SIMULATING AGENT CONVERSATIONS ===")
    
    # Mock the required dependencies
    mock_memory_manager = Mock()
    mock_memory = Mock()
    mock_memory.get_messages.return_value = []
    mock_memory.add_message = Mock()
    mock_memory_manager.get_memory.return_value = mock_memory
    
    # Test conversation scenarios
    scenarios = [
        {
            "name": "Incomplete meeting request",
            "message": "Can we schedule a meeting?",
            "expected_behavior": "Should ask for missing details"
        },
        {
            "name": "Complete meeting request",
            "message": "Can we schedule a meeting for tomorrow at 2 PM for 30 minutes about the project?",
            "expected_behavior": "Should have all required information"
        },
        {
            "name": "Vague time reference",
            "message": "Let's meet sometime next week",
            "expected_behavior": "Should ask for specific time"
        }
    ]
    
    for scenario in scenarios:
        logger.info(f"\n--- Scenario: {scenario['name']} ---")
        logger.info(f"Message: {scenario['message']}")
        logger.info(f"Expected: {scenario['expected_behavior']}")
        
        # Test the conversation context analysis
        current_datetime = datetime.now(pytz.timezone('UTC'))
        details = MeetingInfoExtractor.extract_meeting_details(
            scenario["message"], [], current_datetime, 'UTC'
        )
        
        logger.info(f"Extracted details: {details}")
        
        # Check if we have enough information for tool calls
        has_required_info = not details.get('missing_required', [])
        logger.info(f"Has required info for tools: {has_required_info}")

def test_datetime_validation():
    """Test datetime validation functions."""
    logger.info("\n=== TESTING DATETIME VALIDATION ===")
    
    from tools import validate_datetime_input
    
    test_cases = [
        {
            "input": "2024-01-15T09:00:00+08:00",
            "should_pass": True
        },
        {
            "input": "2024-01-15T09:00:00Z",
            "should_pass": True
        },
        {
            "input": "",
            "should_pass": False
        },
        {
            "input": "invalid-datetime",
            "should_pass": False
        },
        {
            "input": "2024-01-15T09:00:00",  # No timezone
            "should_pass": False
        }
    ]
    
    for i, case in enumerate(test_cases):
        logger.info(f"\n--- DateTime Test {i + 1} ---")
        logger.info(f"Input: '{case['input']}'")
        
        try:
            result = validate_datetime_input(case["input"], "test_field")
            logger.info(f"✅ Validation passed: {result}")
            passed = True
        except ValueError as e:
            logger.info(f"❌ Validation failed: {e}")
            passed = False
        
        expected = case["should_pass"]
        logger.info(f"Expected to pass: {expected}, Actually passed: {passed}")
        
        if expected != passed:
            logger.warning(f"⚠️  Test case mismatch!")

def main():
    """Run all tests."""
    logger.info("🚀 Starting Enhanced Agent Tests")
    
    try:
        test_meeting_info_extraction()
        test_tool_input_validation()
        simulate_agent_conversation()
        test_datetime_validation()
        
        logger.info("\n✅ All tests completed successfully!")
        
    except Exception as e:
        logger.error(f"❌ Test failed with error: {e}")
        raise

if __name__ == "__main__":
    main() 