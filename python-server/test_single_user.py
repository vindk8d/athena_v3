#!/usr/bin/env python3
"""
Test script for single-user executive assistant functionality
"""

import asyncio
import json
from agent import get_agent

async def test_single_user_agent():
    """Test the single-user executive assistant agent"""
    
    # Mock single user details
    user_details = {
        'name': 'Sarah Johnson',
        'email': 'sarah.johnson@company.com',
        'working_hours_start': '09:00:00',
        'working_hours_end': '17:00:00',
        'meeting_duration': 30,
        'buffer_time': 15
    }
    
    # Test scenarios
    test_scenarios = [
        {
            'contact_id': 'colleague_1',
            'message': 'Hello',
            'expected_intro': 'Sarah Johnson\'s executive assistant'
        },
        {
            'contact_id': 'colleague_2', 
            'message': 'I\'d like to schedule a meeting with Sarah',
            'expected_content': 'meeting'
        },
        {
            'contact_id': 'colleague_3',
            'message': 'What\'s Sarah\'s availability next week?',
            'expected_content': 'availability'
        }
    ]
    
    print("🧪 Testing Single-User Executive Assistant Agent")
    print("=" * 50)
    
    # Get the agent
    agent = get_agent()
    
    for i, scenario in enumerate(test_scenarios, 1):
        print(f"\n📋 Test {i}: {scenario['message']}")
        print("-" * 30)
        
        try:
            # Process the message
            result = await agent.process_message(
                contact_id=scenario['contact_id'],
                message=scenario['message'],
                user_id='single_user_id',
                user_details=user_details,
                access_token=None  # No calendar access for test
            )
            
            print(f"✅ Response: {result['response'][:100]}...")
            print(f"🎯 Intent: {result['intent']}")
            print(f"📊 Info: {json.dumps(result['extracted_info'], indent=2)}")
            
            # Check if response contains expected content
            response_lower = result['response'].lower()
            if 'expected_intro' in scenario:
                if scenario['expected_intro'].lower() in response_lower:
                    print("✅ Proper executive assistant introduction detected")
                else:
                    print("❌ Missing executive assistant introduction")
            
            if 'expected_content' in scenario:
                if scenario['expected_content'].lower() in response_lower:
                    print(f"✅ Expected content '{scenario['expected_content']}' found")
                else:
                    print(f"❌ Expected content '{scenario['expected_content']}' not found")
            
        except Exception as e:
            print(f"❌ Error: {e}")
    
    print("\n" + "=" * 50)
    print("🎉 Single-User Executive Assistant Test Complete")

if __name__ == "__main__":
    # Run the test
    asyncio.run(test_single_user_agent()) 