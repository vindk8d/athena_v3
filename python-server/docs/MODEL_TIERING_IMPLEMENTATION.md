# Model Tiering Implementation

## Overview

Athena now implements **intelligent model tiering** to optimize costs while maintaining high-quality performance. This separates simple tasks from complex reasoning tasks using different OpenAI models.

## Model Assignment Strategy

### Simple Model (GPT-3.5-turbo)
**Used for predictable, structured tasks:**
- **Intent Classification**: Determining user intent from messages
- **Conversation Summarization**: Creating concise conversation summaries
- **Temperature**: 0.1 (lower for consistency)

### Complex Model (GPT-4o) 
**Used for complex reasoning tasks:**
- **Calendar Execution**: Main conversation handling and tool coordination
- **Time Parsing**: Converting natural language to datetime (via global LLM instance)
- **Tool Operations**: Calendar availability checks, meeting creation, etc.
- **Temperature**: 0.3 (standard for balanced creativity/consistency)

## Implementation Details

### Configuration
```python
# Environment Variables
LLM_SIMPLE_MODEL=gpt-3.5-turbo   # Default for simple tasks
LLM_MODEL=gpt-4o                 # Default for complex tasks
LLM_TEMPERATURE=0.3              # Temperature for complex model
```

### Agent Architecture
```python
class SimpleAthenaAgent:
    def __init__(self):
        self.simple_llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0.1)
        self.complex_llm = ChatOpenAI(model="gpt-4o", temperature=0.3)
        
        # Agents use appropriate models
        self.intent_classifier = create_agent(self.simple_llm)    # Simple
        self.execution_decider = create_agent(self.complex_llm)   # Complex
```

### Usage Tracking
```python
# Automatic tracking of model calls
self.model_usage = {
    "simple_model_calls": 0,
    "complex_model_calls": 0,
    "simple_model": "gpt-3.5-turbo",
    "complex_model": "gpt-4o"
}

# Get usage statistics
usage_stats = agent.get_model_usage_stats()
# Returns: {"simple_model_calls": 2, "complex_model_calls": 1, "cost_ratio": "2:1"}
```

## Cost Impact

### Expected Savings
- **Intent Classification**: ~80% cost reduction (GPT-4o → GPT-3.5-turbo)
- **Summarization**: ~80% cost reduction (GPT-4o → GPT-3.5-turbo)
- **Overall**: ~40-60% total cost reduction depending on conversation patterns

### Quality Maintenance
- **Simple tasks**: GPT-3.5-turbo is sufficient for structured classification and summarization
- **Complex tasks**: GPT-4o maintains high quality for reasoning-heavy operations
- **Time parsing**: Still uses GPT-4o for accuracy in datetime conversion

## Monitoring

### Logging
```
💰 Using gpt-3.5-turbo (call #1)  # Simple model usage
🧠 Using gpt-4o (call #2)         # Complex model usage
📊 Model Usage - Simple: 2, Complex: 1, Ratio: 2:1
```

### Response Metadata
```json
{
  "model_usage": {
    "simple_model_calls": 2,
    "complex_model_calls": 1,
    "total_calls": 3,
    "cost_ratio": "2:1",
    "simple_model": "gpt-3.5-turbo",
    "complex_model": "gpt-4o"
  }
}
```

## Benefits

1. **Cost Optimization**: 40-60% reduction in LLM costs
2. **Performance Maintained**: Complex reasoning still uses advanced model
3. **Intelligent Routing**: Tasks automatically routed to appropriate model
4. **Usage Visibility**: Complete tracking and monitoring
5. **Configurable**: Models can be adjusted via environment variables
6. **Backwards Compatible**: No changes required to existing API calls

## Future Enhancements

1. **Dynamic Model Selection**: Choose model based on conversation complexity
2. **Cost Budgeting**: Automatic fallback to cheaper models when budget limits approached
3. **A/B Testing**: Compare performance across different model combinations
4. **Caching**: Cache simple responses to avoid repeated model calls 