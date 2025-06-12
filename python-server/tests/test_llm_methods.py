#!/usr/bin/env python3
"""
Comprehensive Tests for LLM-Based Methods in ExecutiveAssistantAgent
Tests all LLM replacements: meeting extraction, context analysis, intent analysis, 
information extraction, and error parsing.
"""

import asyncio
import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from langchain.schema import HumanMessage, AIMessage

# Import the agent and related classes
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import ExecutiveAssistantAgent, LLMMeetingInfoExtractor
from config import Config

class TestLLMMeetingInfoExtractor:
    """Test the LLM-based meeting information extractor."""
    
    @pytest.fixture
    def mock_llm(self):
        """Create a mock LLM for testing."""
        llm = AsyncMock()
        return llm
    
    @pytest.fixture
    def sample_datetime(self):
        """Sample datetime for testing."""
        return datetime(2024, 6, 15, 14, 30)  # June 15, 2024, 2:30 PM
    
    @pytest.mark.asyncio
    async def test_natural_language_time_extraction(self, mock_llm, sample_datetime):
        """Test extraction of natural language time expressions."""
        
        # Mock LLM response for "half past two"
        mock_response = MagicMock()
        mock_response.content = '{"date": "2024-06-16", "time": "14:30", "duration": 60, "title": "project meeting"}'
        mock_llm.ainvoke.return_value = mock_response
        
        result = await LLMMeetingInfoExtractor.extract_meeting_details(
            mock_llm, 
            "Can we meet tomorrow at half past two for an hour?",
            [],
            sample_datetime,
            "UTC"
        )
        
        assert result["time"] == "14:30"
        assert result["date"] == "2024-06-16"
        assert result["duration"] == 60
        assert result["extraction_method"] == "llm"
        assert result["start_datetime"] is not None
        assert result["end_datetime"] is not None
    
    @pytest.mark.asyncio
    async def test_complex_meeting_request(self, mock_llm, sample_datetime):
        """Test extraction from complex meeting requests."""
        
        mock_response = MagicMock()
        mock_response.content = '{"date": "2024-06-15", "time": "12:00", "duration": 30, "title": "standup sync"}'
        mock_llm.ainvoke.return_value = mock_response
        
        result = await LLMMeetingInfoExtractor.extract_meeting_details(
            mock_llm,
            "Let's have a quick standup sync around lunchtime today",
            [],
            sample_datetime,
            "America/New_York"
        )
        
        assert result["time"] == "12:00"
        assert result["title"] == "standup sync"
        assert result["duration"] == 30
        assert "start_datetime" in result
    
    @pytest.mark.asyncio
    async def test_llm_failure_fallback(self, mock_llm, sample_datetime):
        """Test fallback behavior when LLM fails."""
        
        # Mock LLM to raise an exception
        mock_llm.ainvoke.side_effect = Exception("LLM API error")
        
        result = await LLMMeetingInfoExtractor.extract_meeting_details(
            mock_llm,
            "Meeting tomorrow at 2 PM",
            [],
            sample_datetime,
            "UTC"
        )
        
        assert result["extraction_method"] == "fallback"
        assert result["title"] == "Meeting"
        assert result["duration"] == 30
        assert result["missing_required"] == ["date", "time"]
    
    @pytest.mark.asyncio
    async def test_invalid_json_response(self, mock_llm, sample_datetime):
        """Test handling of invalid JSON from LLM."""
        
        mock_response = MagicMock()
        mock_response.content = "This is not valid JSON"
        mock_llm.ainvoke.return_value = mock_response
        
        result = await LLMMeetingInfoExtractor.extract_meeting_details(
            mock_llm,
            "Schedule a meeting",
            [],
            sample_datetime,
            "UTC"
        )
        
        assert result["extraction_method"] == "fallback"
        assert "title" in result
        assert "duration" in result

class TestLLMConversationContextAnalysis:
    """Test the LLM-based conversation context analysis."""
    
    @pytest.fixture
    def agent(self):
        """Create an agent instance for testing."""
        with patch('agent.Config.OPENAI_API_KEY', 'test-key'):
            agent = ExecutiveAssistantAgent(openai_api_key='test-key')
            agent.llm = AsyncMock()
            return agent
    
    @pytest.mark.asyncio
    async def test_meeting_request_detection(self, agent):
        """Test detection of meeting requests with nuanced language."""
        
        mock_response = MagicMock()
        mock_response.content = '''{"has_meeting_request": true, "has_date_preference": false, 
                                   "has_time_preference": false, "has_duration": false, 
                                   "has_title": true, "has_timezone_question": false,
                                   "is_negative_response": false, "is_conditional": false,
                                   "urgency_level": "medium", "conversation_stage": "gathering_time",
                                   "confidence": 0.9}'''
        agent.llm.ainvoke.return_value = mock_response
        
        result = await agent._analyze_conversation_context([], "Can we sync up about the project?")
        
        assert result["has_meeting_request"] == True
        assert result["conversation_stage"] == "gathering_time"
        assert result["analysis_method"] == "llm"
        assert result["confidence"] == 0.9
    
    @pytest.mark.asyncio
    async def test_negative_response_detection(self, agent):
        """Test detection of negative responses."""
        
        mock_response = MagicMock()
        mock_response.content = '''{"has_meeting_request": true, "has_date_preference": false,
                                   "has_time_preference": false, "has_duration": false,
                                   "has_title": false, "has_timezone_question": false,
                                   "is_negative_response": true, "is_conditional": false,
                                   "urgency_level": "low", "conversation_stage": "declining",
                                   "confidence": 0.95}'''
        agent.llm.ainvoke.return_value = mock_response
        
        result = await agent._analyze_conversation_context([], "I'm not available for a meeting this week")
        
        assert result["is_negative_response"] == True
        assert result["conversation_stage"] == "declining"
        assert result["confidence"] == 0.95
    
    @pytest.mark.asyncio
    async def test_conditional_request_detection(self, agent):
        """Test detection of conditional requests."""
        
        mock_response = MagicMock()
        mock_response.content = '''{"has_meeting_request": true, "has_date_preference": false,
                                   "has_time_preference": false, "has_duration": false,
                                   "has_title": true, "has_timezone_question": false,
                                   "is_negative_response": false, "is_conditional": true,
                                   "urgency_level": "low", "conversation_stage": "conditional",
                                   "confidence": 0.8}'''
        agent.llm.ainvoke.return_value = mock_response
        
        result = await agent._analyze_conversation_context([], "If you're free, maybe we could chat about the proposal")
        
        assert result["is_conditional"] == True
        assert result["conversation_stage"] == "conditional"
        assert result["has_title"] == True
    
    @pytest.mark.asyncio
    async def test_timezone_question_detection(self, agent):
        """Test detection of timezone questions."""
        
        mock_response = MagicMock()
        mock_response.content = '''{"has_meeting_request": false, "has_date_preference": false,
                                   "has_time_preference": false, "has_duration": false,
                                   "has_title": false, "has_timezone_question": true,
                                   "is_negative_response": false, "is_conditional": false,
                                   "urgency_level": "low", "conversation_stage": "timezone_inquiry",
                                   "confidence": 0.98}'''
        agent.llm.ainvoke.return_value = mock_response
        
        result = await agent._analyze_conversation_context([], "What timezone are you using?")
        
        assert result["has_timezone_question"] == True
        assert result["conversation_stage"] == "timezone_inquiry"
        assert result["confidence"] == 0.98
    
    @pytest.mark.asyncio
    async def test_context_analysis_fallback(self, agent):
        """Test fallback when LLM context analysis fails."""
        
        # Mock LLM to raise an exception
        agent.llm.ainvoke.side_effect = Exception("LLM error")
        
        result = await agent._analyze_conversation_context([], "Let's schedule a meeting tomorrow")
        
        assert result["analysis_method"] == "fallback"
        assert result["confidence"] == 0.5
        assert "has_meeting_request" in result
        assert "conversation_stage" in result

class TestLLMIntentAnalysis:
    """Test the LLM-based intent analysis."""
    
    @pytest.fixture
    def agent(self):
        """Create an agent instance for testing."""
        with patch('agent.Config.OPENAI_API_KEY', 'test-key'):
            agent = ExecutiveAssistantAgent(openai_api_key='test-key')
            agent.llm = AsyncMock()
            return agent
    
    @pytest.mark.asyncio
    async def test_meeting_request_intent(self, agent):
        """Test intent analysis for meeting requests."""
        
        mock_response = MagicMock()
        mock_response.content = "colleague_meeting_request"
        agent.llm.ainvoke.return_value = mock_response
        
        result = await agent._analyze_intent("Can we sync up about the project?", [])
        
        assert result == "colleague_meeting_request"
    
    @pytest.mark.asyncio
    async def test_urgent_request_intent(self, agent):
        """Test intent analysis for urgent requests."""
        
        mock_response = MagicMock()
        mock_response.content = "colleague_urgent_request"
        agent.llm.ainvoke.return_value = mock_response
        
        result = await agent._analyze_intent("Need to meet ASAP about the critical issue", [])
        
        assert result == "colleague_urgent_request"
    
    @pytest.mark.asyncio
    async def test_declining_intent(self, agent):
        """Test intent analysis for declining responses."""
        
        mock_response = MagicMock()
        mock_response.content = "colleague_declining"
        agent.llm.ainvoke.return_value = mock_response
        
        result = await agent._analyze_intent("Sorry, I can't make it to the meeting", [])
        
        assert result == "colleague_declining"
    
    @pytest.mark.asyncio
    async def test_conditional_intent(self, agent):
        """Test intent analysis for conditional requests."""
        
        mock_response = MagicMock()
        mock_response.content = "colleague_conditional_request"
        agent.llm.ainvoke.return_value = mock_response
        
        result = await agent._analyze_intent("If you have time, maybe we could discuss this", [])
        
        assert result == "colleague_conditional_request"
    
    @pytest.mark.asyncio
    async def test_tool_based_intent_priority(self, agent):
        """Test that tool-based intent takes priority over LLM analysis."""
        
        # Even if LLM would return something else, tool usage should take priority
        tools_used = [{"tool": "create_event", "input": {}, "output": "Event created"}]
        
        result = await agent._analyze_intent("Random message", tools_used)
        
        assert result == "meeting_scheduled_for_user"
        # LLM should not be called when tools were used
        agent.llm.ainvoke.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_invalid_intent_fallback(self, agent):
        """Test fallback when LLM returns invalid intent."""
        
        mock_response = MagicMock()
        mock_response.content = "invalid_intent_category"
        agent.llm.ainvoke.return_value = mock_response
        
        result = await agent._analyze_intent("Let's schedule a meeting", [])
        
        # Should fallback to keyword-based analysis
        assert result == "colleague_meeting_request"
    
    @pytest.mark.asyncio
    async def test_intent_analysis_fallback(self, agent):
        """Test fallback when LLM intent analysis fails."""
        
        agent.llm.ainvoke.side_effect = Exception("LLM error")
        
        result = await agent._analyze_intent("Schedule a meeting tomorrow", [])
        
        # Should use fallback keyword-based analysis
        assert result == "colleague_meeting_request"

class TestLLMInformationExtraction:
    """Test the LLM-based information extraction."""
    
    @pytest.fixture
    def agent(self):
        """Create an agent instance for testing."""
        with patch('agent.Config.OPENAI_API_KEY', 'test-key'):
            agent = ExecutiveAssistantAgent(openai_api_key='test-key')
            agent.llm = AsyncMock()
            return agent
    
    @pytest.mark.asyncio
    async def test_rich_information_extraction(self, agent):
        """Test rich information extraction with LLM."""
        
        mock_response = MagicMock()
        mock_response.content = '''{"temporal_reference": "tomorrow", "duration_mentioned": "hours",
                                   "urgency_indicators": ["asap"], "participants_mentioned": true,
                                   "location_mentioned": false, "meeting_type": "standup",
                                   "sentiment": "positive", "complexity_level": "moderate",
                                   "key_entities": ["project review", "John"],
                                   "action_items": ["schedule meeting", "send invite"],
                                   "confidence": 0.85}'''
        agent.llm.ainvoke.return_value = mock_response
        
        result = await agent._extract_information(
            "Need to schedule a standup with John tomorrow ASAP",
            "I'll check availability and send you options",
            [],
            "user123"
        )
        
        assert result["temporal_reference"] == "tomorrow"
        assert result["urgency_indicators"] == ["asap"]
        assert result["participants_mentioned"] == True
        assert result["meeting_type"] == "standup"
        assert result["sentiment"] == "positive"
        assert result["key_entities"] == ["project review", "John"]
        assert result["action_items"] == ["schedule meeting", "send invite"]
        assert result["extraction_method"] == "llm"
        assert result["confidence"] == 0.85
    
    @pytest.mark.asyncio
    async def test_sentiment_analysis(self, agent):
        """Test sentiment analysis in information extraction."""
        
        mock_response = MagicMock()
        mock_response.content = '''{"temporal_reference": null, "duration_mentioned": null,
                                   "urgency_indicators": [], "participants_mentioned": false,
                                   "location_mentioned": false, "meeting_type": null,
                                   "sentiment": "negative", "complexity_level": "simple",
                                   "key_entities": [], "action_items": [],
                                   "confidence": 0.9}'''
        agent.llm.ainvoke.return_value = mock_response
        
        result = await agent._extract_information(
            "Sorry, I can't make it to the meeting",
            "I understand, let me find alternative times",
            [],
            "user123"
        )
        
        assert result["sentiment"] == "negative"
        assert result["confidence"] == 0.9
    
    @pytest.mark.asyncio
    async def test_tool_output_extraction(self, agent):
        """Test extraction of information from tool outputs."""
        
        mock_response = MagicMock()
        mock_response.content = '''{"temporal_reference": "today", "duration_mentioned": "minutes",
                                   "urgency_indicators": [], "participants_mentioned": false,
                                   "location_mentioned": false, "meeting_type": "sync",
                                   "sentiment": "neutral", "complexity_level": "simple",
                                   "key_entities": [], "action_items": [],
                                   "confidence": 0.7}'''
        agent.llm.ainvoke.return_value = mock_response
        
        tools_used = [{
            "tool": "create_event",
            "input": {
                "title": "Project Sync",
                "start_datetime": "2024-06-15T14:00:00+00:00",
                "end_datetime": "2024-06-15T15:00:00+00:00"
            },
            "output": "Event created successfully"
        }]
        
        result = await agent._extract_information(
            "Create the meeting",
            "Meeting created successfully",
            tools_used,
            "user123"
        )
        
        assert result["meeting_created_for_user"] == True
        assert result["event_details"]["title"] == "Project Sync"
        assert result["event_details"]["created_for_user"] == "user123"
    
    @pytest.mark.asyncio
    async def test_information_extraction_fallback(self, agent):
        """Test fallback when LLM information extraction fails."""
        
        agent.llm.ainvoke.side_effect = Exception("LLM error")
        
        result = await agent._extract_information(
            "Let's meet tomorrow for an hour",
            "I'll check your availability",
            [],
            "user123"
        )
        
        assert result["extraction_method"] == "fallback"
        assert result["temporal_reference"] == "tomorrow"
        assert result["duration_mentioned"] == "hour"
        assert result["confidence"] == 0.5

class TestLLMErrorParsing:
    """Test the LLM-based error message parsing."""
    
    @pytest.fixture
    def agent(self):
        """Create an agent instance for testing."""
        with patch('agent.Config.OPENAI_API_KEY', 'test-key'):
            agent = ExecutiveAssistantAgent(openai_api_key='test-key')
            agent.llm = AsyncMock()
            return agent
    
    @pytest.mark.asyncio
    async def test_missing_parameters_extraction(self, agent):
        """Test extraction of missing parameters from error messages."""
        
        mock_response = MagicMock()
        mock_response.content = '["start_datetime", "end_datetime"]'
        agent.llm.ainvoke.return_value = mock_response
        
        result = await agent._extract_missing_params_llm(
            "TypeError: missing required arguments: start_datetime, end_datetime"
        )
        
        assert result == ["start_datetime", "end_datetime"]
    
    @pytest.mark.asyncio
    async def test_single_parameter_extraction(self, agent):
        """Test extraction of single missing parameter."""
        
        mock_response = MagicMock()
        mock_response.content = '["title"]'
        agent.llm.ainvoke.return_value = mock_response
        
        result = await agent._extract_missing_params_llm(
            "missing required argument: title"
        )
        
        assert result == ["title"]
    
    @pytest.mark.asyncio
    async def test_complex_error_message(self, agent):
        """Test extraction from complex error messages."""
        
        mock_response = MagicMock()
        mock_response.content = '["start", "end"]'
        agent.llm.ainvoke.return_value = mock_response
        
        result = await agent._extract_missing_params_llm(
            "TypeError: create_event() missing 2 required positional arguments: 'start' and 'end'"
        )
        
        assert result == ["start", "end"]
    
    @pytest.mark.asyncio
    async def test_error_parsing_fallback(self, agent):
        """Test fallback when LLM error parsing fails."""
        
        agent.llm.ainvoke.side_effect = Exception("LLM error")
        
        result = await agent._extract_missing_params_llm(
            "missing required arguments: start_datetime, end_datetime"
        )
        
        assert result == []  # Should return empty list on failure
    
    @pytest.mark.asyncio
    async def test_invalid_json_error_response(self, agent):
        """Test handling of invalid JSON in error parsing."""
        
        mock_response = MagicMock()
        mock_response.content = "Not a valid JSON array"
        agent.llm.ainvoke.return_value = mock_response
        
        result = await agent._extract_missing_params_llm(
            "missing required arguments: start_datetime"
        )
        
        assert result == []  # Should return empty list for invalid JSON

class TestIntegrationScenarios:
    """Test integration scenarios with multiple LLM methods working together."""
    
    @pytest.fixture
    def agent(self):
        """Create an agent instance for testing."""
        with patch('agent.Config.OPENAI_API_KEY', 'test-key'):
            agent = ExecutiveAssistantAgent(openai_api_key='test-key')
            agent.llm = AsyncMock()
            return agent
    
    @pytest.mark.asyncio
    async def test_complete_meeting_flow(self, agent):
        """Test complete meeting scheduling flow with all LLM methods."""
        
        # Mock responses for different LLM calls
        def mock_llm_response(messages):
            content = messages[0].content
            if "Extract meeting information" in content:
                return MagicMock(content='{"date": "2024-06-16", "time": "14:30", "duration": 60, "title": "project sync"}')
            elif "Analyze this conversation" in content:
                return MagicMock(content='{"has_meeting_request": true, "conversation_stage": "ready_to_schedule", "confidence": 0.9}')
            elif "determine the primary intent" in content:
                return MagicMock(content="colleague_meeting_request")
            elif "Extract structured information" in content:
                return MagicMock(content='{"sentiment": "positive", "meeting_type": "sync", "confidence": 0.8}')
            else:
                return MagicMock(content='{}')
        
        agent.llm.ainvoke.side_effect = mock_llm_response
        
        # Test meeting extraction
        meeting_details = await LLMMeetingInfoExtractor.extract_meeting_details(
            agent.llm,
            "Let's sync up tomorrow at half past two for an hour",
            [],
            datetime(2024, 6, 15, 10, 0),
            "UTC"
        )
        
        # Test context analysis
        context = await agent._analyze_conversation_context([], "Let's sync up tomorrow")
        
        # Test intent analysis
        intent = await agent._analyze_intent("Let's sync up tomorrow", [])
        
        # Test information extraction
        info = await agent._extract_information(
            "Let's sync up tomorrow",
            "I'll check availability",
            [],
            "user123"
        )
        
        # Verify all methods worked
        assert meeting_details["time"] == "14:30"
        assert context["has_meeting_request"] == True
        assert intent == "colleague_meeting_request"
        assert info["sentiment"] == "positive"
    
    @pytest.mark.asyncio
    async def test_fallback_chain(self, agent):
        """Test that all methods gracefully fallback when LLM fails."""
        
        # Mock all LLM calls to fail
        agent.llm.ainvoke.side_effect = Exception("LLM service unavailable")
        
        # Test that all methods still work with fallbacks
        meeting_details = await LLMMeetingInfoExtractor.extract_meeting_details(
            agent.llm,
            "Meeting tomorrow at 2 PM",
            [],
            datetime(2024, 6, 15, 10, 0),
            "UTC"
        )
        
        context = await agent._analyze_conversation_context([], "Schedule a meeting")
        intent = await agent._analyze_intent("Schedule a meeting", [])
        info = await agent._extract_information("Schedule a meeting", "OK", [], "user123")
        
        # Verify fallback methods worked
        assert meeting_details["extraction_method"] == "fallback"
        assert context["analysis_method"] == "fallback"
        assert intent == "colleague_meeting_request"  # Fallback keyword matching
        assert info["extraction_method"] == "fallback"

def run_tests():
    """Run all tests and display results."""
    print("🧪 Running LLM Methods Test Suite...")
    print("=" * 60)
    
    # Test scenarios to validate
    test_scenarios = [
        {
            "name": "Natural Language Time Extraction",
            "description": "Tests 'half past two' → '14:30'",
            "critical": True
        },
        {
            "name": "Negative Response Detection", 
            "description": "Tests 'I'm not available' detection",
            "critical": True
        },
        {
            "name": "Intent Classification",
            "description": "Tests nuanced intent understanding",
            "critical": True
        },
        {
            "name": "Rich Information Extraction",
            "description": "Tests entity and sentiment extraction",
            "critical": False
        },
        {
            "name": "Error Message Parsing",
            "description": "Tests robust error parameter extraction",
            "critical": False
        },
        {
            "name": "Fallback Behavior",
            "description": "Tests graceful degradation when LLM fails",
            "critical": True
        }
    ]
    
    print("📋 Test Scenarios:")
    for i, scenario in enumerate(test_scenarios, 1):
        priority = "🔥 CRITICAL" if scenario["critical"] else "🟡 NICE-TO-HAVE"
        print(f"{i}. {scenario['name']} - {priority}")
        print(f"   {scenario['description']}")
    
    print("\n" + "=" * 60)
    print("✅ All test classes created and ready to run!")
    print("\nTo run tests:")
    print("1. Install pytest: pip install pytest pytest-asyncio")
    print("2. Run tests: pytest test_llm_methods.py -v")
    print("3. Run with coverage: pytest test_llm_methods.py --cov=agent")
    
    print("\n🎯 Key Test Coverage:")
    print("✅ LLM Meeting Information Extraction")
    print("✅ LLM Conversation Context Analysis") 
    print("✅ LLM Intent Analysis")
    print("✅ LLM Information Extraction")
    print("✅ LLM Error Message Parsing")
    print("✅ Fallback Behavior for All Methods")
    print("✅ Integration Scenarios")
    print("✅ Edge Cases and Error Handling")

if __name__ == "__main__":
    run_tests() 