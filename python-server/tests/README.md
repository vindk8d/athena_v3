# LLM Methods Test Suite

This directory contains comprehensive tests for all LLM-based methods in the Executive Assistant Agent.

## 📁 File Structure

```
tests/
├── __init__.py                 # Package initialization
├── README.md                   # This file
├── test_llm_methods.py         # Core LLM functionality tests (35+ tests)
├── test_llm_edge_cases.py      # Edge cases and stress tests (25+ tests)
├── run_llm_tests.py           # Comprehensive test runner with reporting
├── demo_llm_tests.py          # Test demonstration script
└── test_summary.py            # Test coverage summary
```

## 🧪 Test Coverage

### Core LLM Methods Tested
- **`LLMMeetingInfoExtractor.extract_meeting_details()`**
  - Natural language time extraction ("half past two" → "14:30")
  - Complex meeting requests with context
  - Fallback behavior when LLM fails

- **`ExecutiveAssistantAgent._analyze_conversation_context()`**
  - Meeting request detection with nuanced language
  - Negative response detection ("I'm not available")
  - Timezone question detection

- **`ExecutiveAssistantAgent._analyze_intent()`**
  - Sophisticated intent classification
  - Urgent vs. conditional request handling
  - Tool-based intent priority

- **`ExecutiveAssistantAgent._extract_information()`**
  - Rich semantic information extraction
  - Sentiment analysis and entity recognition
  - Action item identification

- **`ExecutiveAssistantAgent._extract_missing_params_llm()`**
  - Robust error message parsing
  - Missing parameter extraction

### Robustness Features Tested
- **Fallback Mechanisms**: Graceful degradation when LLM fails
- **Input Validation**: Handling of edge cases, Unicode, empty inputs
- **Error Recovery**: Malformed JSON, timeouts, exceptions
- **Performance Under Load**: Concurrent calls, large datasets
- **Data Integrity**: Consistent output formats and validation

## 🚀 Running Tests

### Prerequisites
```bash
pip install pytest pytest-asyncio
```

### Run All Tests
```bash
# From the python-server directory
pytest tests/ -v

# Or run the comprehensive test runner
python tests/run_llm_tests.py
```

### Run Specific Test Files
```bash
# Core LLM functionality tests
pytest tests/test_llm_methods.py -v

# Edge cases and stress tests
pytest tests/test_llm_edge_cases.py -v
```

### Run with Coverage
```bash
pytest --cov=agent tests/ -v
```

### View Test Summary
```bash
python tests/test_summary.py
```

### Run Test Demonstration
```bash
python tests/demo_llm_tests.py
```

## 📊 Test Categories

### 1. Core Functionality Tests (`test_llm_methods.py`)
- **Meeting Information Extraction**: Natural language parsing
- **Conversation Context Analysis**: Nuanced understanding
- **Intent Analysis**: Sophisticated classification
- **Information Extraction**: Rich semantic analysis
- **Error Parsing**: Robust error handling
- **Integration Scenarios**: End-to-end workflows

### 2. Edge Cases & Stress Tests (`test_llm_edge_cases.py`)
- **Empty/Malformed Input**: Graceful handling
- **Unicode & Special Characters**: International support
- **Very Long Messages**: Performance under load
- **Concurrent Operations**: Thread safety
- **Timeout Simulation**: Network resilience
- **Memory Management**: Large dataset handling

### 3. Comprehensive Reporting (`run_llm_tests.py`)
- **Automated Execution**: All test suites
- **Performance Metrics**: Execution time and speed
- **Robustness Assessment**: Scoring and recommendations
- **Detailed Reporting**: JSON output for analysis

## ✅ Expected Outcomes

When all tests pass, you can expect:
- ✅ All LLM methods handle natural language correctly
- ✅ Graceful fallback when LLM services fail
- ✅ Robust handling of edge cases and malformed input
- ✅ Consistent performance under load
- ✅ Proper error recovery and logging
- ✅ Unicode and international character support
- ✅ Memory efficiency with large datasets
- ✅ Thread safety for concurrent operations

## 🎯 Benefits

1. **Production Readiness**: Ensures LLM methods are robust for deployment
2. **Reliability Assurance**: System continues working even when LLM APIs fail
3. **Performance Confidence**: Validates behavior under various load conditions
4. **User Experience Quality**: Consistent responses regardless of input
5. **Maintenance Efficiency**: Regression testing for future changes
6. **Debugging Support**: Comprehensive logging and error reporting

## 🔧 Troubleshooting

### Import Errors
If you encounter import errors, ensure you're running tests from the `python-server` directory:
```bash
cd python-server
pytest tests/ -v
```

### Missing Dependencies
Install required packages:
```bash
pip install pytest pytest-asyncio
```

### Path Issues
The test files automatically add the parent directory to the Python path, so imports should work correctly when run from the `python-server` directory.

---

**Total Test Coverage**: 60+ comprehensive test cases ensuring robust LLM method behavior. 