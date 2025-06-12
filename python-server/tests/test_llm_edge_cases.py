#!/usr/bin/env python3
"""
Edge Case Tests for LLM-Based Methods in ExecutiveAssistantAgent
Tests unusual scenarios, malformed inputs, and stress conditions.
"""

import asyncio
import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from langchain.schema import HumanMessage, AIMessage

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import ExecutiveAssistantAgent, LLMMeetingInfoExtractor

class TestLLMEdgeCases:
    """Test edge cases and unusual scenarios for LLM methods."""
    
    @pytest.fixture
    def agent(self):
        """Create an agent instance for testing."""
        with patch('agent.Config.OPENAI_API_KEY', 'test-key'):
            agent = ExecutiveAssistantAgent(openai_api_key='test-key')
            agent.llm = AsyncMock()
            return agent
    
    @pytest.fixture
    def mock_llm(self):
        """Create a mock LLM for testing."""
        return AsyncMock()
    
    @pytest.mark.asyncio
    async def test_empty_message_handling(self, agent):
        """Test handling of empty or whitespace-only messages."""
        
        mock_response = MagicMock()
        mock_response.content = '''{"has_meeting_request": false, "has_date_preference": false,
                                   "has_time_preference": false, "has_duration": false,
                                   "has_title": false, "has_timezone_question": false,
                                   "is_negative_response": false, "is_conditional": false,
                                   "urgency_level": "low", "conversation_stage": "initial",
                                   "confidence": 0.1}'''
        agent.llm.ainvoke.return_value = mock_response
        
        # Test empty string
        result = await agent._analyze_conversation_context([], "")
        assert result["confidence"] == 0.1
        assert result["conversation_stage"] == "initial"
        
        # Test whitespace only
        result = await agent._analyze_conversation_context([], "   \n\t  ")
        assert result["confidence"] == 0.1
    
    @pytest.mark.asyncio
    async def test_very_long_message_handling(self, agent):
        """Test handling of extremely long messages."""
        
        # Create a very long message (over 10,000 characters)
        long_message = "I need to schedule a meeting " * 500
        
        mock_response = MagicMock()
        mock_response.content = '''{"has_meeting_request": true, "has_date_preference": false,
                                   "has_time_preference": false, "has_duration": false,
                                   "has_title": false, "has_timezone_question": false,
                                   "is_negative_response": false, "is_conditional": false,
                                   "urgency_level": "medium", "conversation_stage": "gathering_time",
                                   "confidence": 0.8}'''
        agent.llm.ainvoke.return_value = mock_response
        
        result = await agent._analyze_conversation_context([], long_message)
        assert result["has_meeting_request"] == True
        assert result["confidence"] == 0.8
    
    @pytest.mark.asyncio
    async def test_special_characters_and_unicode(self, mock_llm):
        """Test handling of special characters and Unicode in messages."""
        
        mock_response = MagicMock()
        mock_response.content = '{"date": "2024-06-16", "time": "14:30", "duration": 30, "title": "café meeting"}'
        mock_llm.ainvoke.return_value = mock_response
        
        # Test with emojis and special characters
        message = "Let's meet at the café tomorrow at 2:30 PM 😊 ñoño"
        
        result = await LLMMeetingInfoExtractor.extract_meeting_details(
            mock_llm,
            message,
            [],
            datetime(2024, 6, 15, 10, 0),
            "UTC"
        )
        
        assert result["title"] == "café meeting"
        assert result["time"] == "14:30"
    
    @pytest.mark.asyncio
    async def test_malformed_json_responses(self, mock_llm):
        """Test handling of various malformed JSON responses from LLM."""
        
        malformed_responses = [
            '{"date": "2024-06-16", "time": "14:30"',  # Missing closing brace
            '{"date": 2024-06-16, "time": "14:30"}',   # Unquoted date
            '{"date": "2024-06-16" "time": "14:30"}',  # Missing comma
            'Not JSON at all',                          # Not JSON
            '{"date": null, "time": undefined}',       # Invalid null/undefined
            '',                                        # Empty response
            '[]',                                      # Array instead of object
        ]
        
        for malformed_json in malformed_responses:
            mock_response = MagicMock()
            mock_response.content = malformed_json
            mock_llm.ainvoke.return_value = mock_response
            
            result = await LLMMeetingInfoExtractor.extract_meeting_details(
                mock_llm,
                "Schedule a meeting",
                [],
                datetime(2024, 6, 15, 10, 0),
                "UTC"
            )
            
            # Should fallback gracefully
            assert result["extraction_method"] == "fallback"
            assert "title" in result
            assert "duration" in result
    
    @pytest.mark.asyncio
    async def test_llm_timeout_simulation(self, agent):
        """Test handling of LLM timeouts."""
        
        # Simulate timeout with asyncio.TimeoutError
        agent.llm.ainvoke.side_effect = asyncio.TimeoutError("LLM request timed out")
        
        result = await agent._analyze_conversation_context([], "Schedule a meeting")
        
        # Should fallback gracefully
        assert result["analysis_method"] == "fallback"
        assert "has_meeting_request" in result
    
    @pytest.mark.asyncio
    async def test_mixed_language_input(self, mock_llm):
        """Test handling of mixed language inputs."""
        
        mock_response = MagicMock()
        mock_response.content = '{"date": "2024-06-16", "time": "14:30", "duration": 60, "title": "reunión importante"}'
        mock_llm.ainvoke.return_value = mock_response
        
        # Mixed English/Spanish
        message = "Necesito schedule una reunión mañana at 2:30 PM por favor"
        
        result = await LLMMeetingInfoExtractor.extract_meeting_details(
            mock_llm,
            message,
            [],
            datetime(2024, 6, 15, 10, 0),
            "UTC"
        )
        
        assert result["title"] == "reunión importante"
        assert result["time"] == "14:30"
    
    @pytest.mark.asyncio
    async def test_ambiguous_time_expressions(self, mock_llm):
        """Test handling of ambiguous time expressions."""
        
        ambiguous_expressions = [
            "sometime next week",
            "when you're free",
            "ASAP but not urgent",
            "maybe tomorrow or the day after",
            "in the morning or afternoon",
        ]
        
        for expression in ambiguous_expressions:
            mock_response = MagicMock()
            mock_response.content = '{"date": null, "time": null, "duration": 30, "title": "meeting"}'
            mock_llm.ainvoke.return_value = mock_response
            
            result = await LLMMeetingInfoExtractor.extract_meeting_details(
                mock_llm,
                f"Let's meet {expression}",
                [],
                datetime(2024, 6, 15, 10, 0),
                "UTC"
            )
            
            # Should handle gracefully with null values
            assert result["date"] is None
            assert result["time"] is None
            assert "date" in result["missing_required"]
            assert "time" in result["missing_required"]
    
    @pytest.mark.asyncio
    async def test_contradictory_information(self, mock_llm):
        """Test handling of contradictory information in messages."""
        
        mock_response = MagicMock()
        mock_response.content = '{"date": "2024-06-16", "time": "14:00", "duration": 30, "title": "meeting"}'
        mock_llm.ainvoke.return_value = mock_response
        
        # Contradictory message
        message = "Let's meet tomorrow at 2 PM, no wait, make it 3 PM, actually let's do 2 PM"
        
        result = await LLMMeetingInfoExtractor.extract_meeting_details(
            mock_llm,
            message,
            [],
            datetime(2024, 6, 15, 10, 0),
            "UTC"
        )
        
        # LLM should resolve the contradiction
        assert result["time"] == "14:00"  # Should pick one time
    
    @pytest.mark.asyncio
    async def test_context_analysis_with_conversation_history(self, agent):
        """Test context analysis with complex conversation history."""
        
        # Create complex conversation history
        history = [
            HumanMessage(content="Hi there!"),
            AIMessage(content="Hello! How can I help you?"),
            HumanMessage(content="I was thinking about the project"),
            AIMessage(content="Which project are you referring to?"),
            HumanMessage(content="The one we discussed last week"),
            AIMessage(content="I see, what about it?"),
            HumanMessage(content="Maybe we should meet to discuss it"),
        ]
        
        mock_response = MagicMock()
        mock_response.content = '''{"has_meeting_request": true, "has_date_preference": false,
                                   "has_time_preference": false, "has_duration": false,
                                   "has_title": true, "has_timezone_question": false,
                                   "is_negative_response": false, "is_conditional": true,
                                   "urgency_level": "low", "conversation_stage": "conditional",
                                   "confidence": 0.7}'''
        agent.llm.ainvoke.return_value = mock_response
        
        result = await agent._analyze_conversation_context(history, "What do you think?")
        
        assert result["has_meeting_request"] == True
        assert result["is_conditional"] == True
        assert result["has_title"] == True
    
    @pytest.mark.asyncio
    async def test_intent_analysis_edge_cases(self, agent):
        """Test intent analysis with edge case messages."""
        
        edge_case_messages = [
            ("???", "colleague_general_conversation"),
            ("!!!", "colleague_general_conversation"),
            ("OK", "colleague_general_conversation"),
            ("No", "colleague_declining"),
            ("Yes please", "colleague_general_conversation"),
            ("Help", "colleague_general_conversation"),
        ]
        
        for message, expected_fallback in edge_case_messages:
            # Mock LLM to return invalid intent
            mock_response = MagicMock()
            mock_response.content = "invalid_intent"
            agent.llm.ainvoke.return_value = mock_response
            
            result = await agent._analyze_intent(message, [])
            
            # Should fallback to keyword-based analysis
            assert result == expected_fallback
    
    @pytest.mark.asyncio
    async def test_information_extraction_with_no_information(self, agent):
        """Test information extraction when there's minimal information."""
        
        mock_response = MagicMock()
        mock_response.content = '''{"temporal_reference": null, "duration_mentioned": null,
                                   "urgency_indicators": [], "participants_mentioned": false,
                                   "location_mentioned": false, "meeting_type": null,
                                   "sentiment": "neutral", "complexity_level": "simple",
                                   "key_entities": [], "action_items": [],
                                   "confidence": 0.2}'''
        agent.llm.ainvoke.return_value = mock_response
        
        result = await agent._extract_information(
            "OK",
            "Understood",
            [],
            "user123"
        )
        
        assert result["sentiment"] == "neutral"
        assert result["confidence"] == 0.2
        assert result["key_entities"] == []
        assert result["action_items"] == []
    
    @pytest.mark.asyncio
    async def test_error_parsing_with_unusual_errors(self, agent):
        """Test error parsing with unusual error message formats."""
        
        unusual_errors = [
            "Something went wrong",
            "Error: undefined is not a function",
            "500 Internal Server Error",
            "Connection timeout",
            "Invalid API key",
            "",  # Empty error
        ]
        
        for error_msg in unusual_errors:
            mock_response = MagicMock()
            mock_response.content = "[]"  # Empty array
            agent.llm.ainvoke.return_value = mock_response
            
            result = await agent._extract_missing_params_llm(error_msg)
            
            # Should return empty list for non-parameter errors
            assert result == []
    
    @pytest.mark.asyncio
    async def test_concurrent_llm_calls(self, agent):
        """Test handling of concurrent LLM calls."""
        
        # Mock LLM with delay to simulate real API calls
        async def mock_llm_with_delay(messages):
            await asyncio.sleep(0.1)  # Small delay
            mock_response = MagicMock()
            mock_response.content = '''{"has_meeting_request": true, "conversation_stage": "gathering_time", "confidence": 0.8}'''
            return mock_response
        
        agent.llm.ainvoke = mock_llm_with_delay
        
        # Make multiple concurrent calls
        tasks = [
            agent._analyze_conversation_context([], f"Meeting request {i}")
            for i in range(5)
        ]
        
        results = await asyncio.gather(*tasks)
        
        # All should complete successfully
        assert len(results) == 5
        for result in results:
            assert result["has_meeting_request"] == True
            assert result["confidence"] == 0.8

class TestLLMStressTests:
    """Stress tests for LLM methods under load."""
    
    @pytest.fixture
    def agent(self):
        """Create an agent instance for testing."""
        with patch('agent.Config.OPENAI_API_KEY', 'test-key'):
            agent = ExecutiveAssistantAgent(openai_api_key='test-key')
            agent.llm = AsyncMock()
            return agent
    
    @pytest.mark.asyncio
    async def test_rapid_successive_calls(self, agent):
        """Test rapid successive calls to LLM methods."""
        
        mock_response = MagicMock()
        mock_response.content = '''{"has_meeting_request": true, "confidence": 0.8}'''
        agent.llm.ainvoke.return_value = mock_response
        
        # Make 20 rapid calls
        results = []
        for i in range(20):
            result = await agent._analyze_conversation_context([], f"Message {i}")
            results.append(result)
        
        # All should succeed
        assert len(results) == 20
        for result in results:
            assert result["has_meeting_request"] == True
    
    @pytest.mark.asyncio
    async def test_memory_usage_with_large_history(self, agent):
        """Test memory usage with very large conversation history."""
        
        # Create large conversation history (1000 messages)
        large_history = []
        for i in range(1000):
            if i % 2 == 0:
                large_history.append(HumanMessage(content=f"User message {i}"))
            else:
                large_history.append(AIMessage(content=f"Assistant message {i}"))
        
        mock_response = MagicMock()
        mock_response.content = '''{"has_meeting_request": true, "confidence": 0.8}'''
        agent.llm.ainvoke.return_value = mock_response
        
        # Should handle large history gracefully (only uses last 10 messages)
        result = await agent._analyze_conversation_context(large_history, "New message")
        
        assert result["has_meeting_request"] == True
        assert result["confidence"] == 0.8

def run_edge_case_tests():
    """Run edge case tests and display results."""
    print("🧪 Running LLM Edge Case Test Suite...")
    print("=" * 60)
    
    edge_case_scenarios = [
        {
            "name": "Empty/Whitespace Messages",
            "description": "Tests handling of empty or whitespace-only inputs",
            "critical": True
        },
        {
            "name": "Very Long Messages",
            "description": "Tests handling of extremely long messages (10k+ chars)",
            "critical": True
        },
        {
            "name": "Special Characters & Unicode",
            "description": "Tests emojis, accents, and special characters",
            "critical": True
        },
        {
            "name": "Malformed JSON Responses",
            "description": "Tests various malformed JSON from LLM",
            "critical": True
        },
        {
            "name": "LLM Timeout Simulation",
            "description": "Tests graceful handling of LLM timeouts",
            "critical": True
        },
        {
            "name": "Mixed Language Input",
            "description": "Tests handling of multilingual messages",
            "critical": False
        },
        {
            "name": "Ambiguous Time Expressions",
            "description": "Tests vague time references like 'sometime'",
            "critical": False
        },
        {
            "name": "Contradictory Information",
            "description": "Tests messages with conflicting details",
            "critical": False
        },
        {
            "name": "Concurrent LLM Calls",
            "description": "Tests multiple simultaneous LLM requests",
            "critical": True
        },
        {
            "name": "Stress Testing",
            "description": "Tests rapid successive calls and large data",
            "critical": False
        }
    ]
    
    print("📋 Edge Case Test Scenarios:")
    for i, scenario in enumerate(edge_case_scenarios, 1):
        priority = "🔥 CRITICAL" if scenario["critical"] else "🟡 NICE-TO-HAVE"
        print(f"{i}. {scenario['name']} - {priority}")
        print(f"   {scenario['description']}")
    
    print("\n" + "=" * 60)
    print("✅ Edge case tests created and ready to run!")
    print("\nTo run edge case tests:")
    print("1. pytest test_llm_edge_cases.py -v")
    print("2. pytest test_llm_edge_cases.py::TestLLMEdgeCases -v")
    print("3. pytest test_llm_edge_cases.py::TestLLMStressTests -v")
    
    print("\n🎯 Edge Case Coverage:")
    print("✅ Empty/Invalid Input Handling")
    print("✅ Malformed LLM Response Handling")
    print("✅ Unicode and Special Character Support")
    print("✅ Timeout and Error Recovery")
    print("✅ Concurrent Request Handling")
    print("✅ Memory Usage with Large Data")
    print("✅ Ambiguous Input Resolution")
    print("✅ Stress Testing Under Load")

if __name__ == "__main__":
    run_edge_case_tests() 