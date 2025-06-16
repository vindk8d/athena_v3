# Athena LangGraph Architecture

## Main Flow Diagram

```mermaid
graph TD
    START([START]) --> input_interpreter["🔍 Input Interpreter<br/>- Classify intent<br/>- Extract temporal refs<br/>- Analyze context"]
    
    input_interpreter --> decision1{Calendar Related?}
    
    decision1 -->|Yes| planner["📋 Planner<br/>- Create execution plan<br/>- Assess info completeness<br/>- Determine next steps"]
    decision1 -->|No| response_generator["💬 Response Generator<br/>- Generate final response<br/>- Handle greetings/general"]
    
    planner --> decision2{Plan Decision}
    
    decision2 -->|Needs Time Parsing| time_normalizer["⏰ Time Normalizer<br/>- Parse 'tomorrow'<br/>- Normalize to ISO format<br/>- Handle timezones"]
    decision2 -->|Missing Info| clarification["❓ Clarification<br/>- Generate questions<br/>- Request missing data<br/>- Natural language"]
    decision2 -->|Ready| execution["⚡ Execution<br/>- Run calendar tools<br/>- Check availability<br/>- Create events"]
    decision2 -->|Simple Response| response_generator
    
    time_normalizer --> planner
    clarification --> END([END - Awaiting User])
    execution --> response_generator
    response_generator --> END([END - Complete])
    
    %% Styling
    classDef startEnd fill:#e1f5fe,stroke:#01579b,stroke-width:3px
    classDef interpreter fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    classDef planner fill:#e8f5e8,stroke:#1b5e20,stroke-width:2px
    classDef normalizer fill:#fff3e0,stroke:#e65100,stroke-width:2px
    classDef clarification fill:#fce4ec,stroke:#880e4f,stroke-width:2px
    classDef execution fill:#e0f2f1,stroke:#004d40,stroke-width:2px
    classDef response fill:#f1f8e9,stroke:#33691e,stroke-width:2px
    classDef decision fill:#fff8e1,stroke:#f57f17,stroke-width:2px
    
    class START,END startEnd
    class input_interpreter interpreter
    class planner planner
    class time_normalizer normalizer
    class clarification clarification
    class execution execution
    class response_generator response
    class decision1,decision2 decision
```

## Description

This diagram shows the sophisticated reasoning flow of Athena's LangGraph-based agent:

### Nodes:
1. **Input Interpreter** 🔍: Analyzes incoming messages, classifies intent, and extracts temporal references
2. **Planner** 📋: Creates execution plans and assesses information completeness
3. **Time Normalizer** ⏰: Converts natural language time references to ISO format
4. **Clarification** ❓: Generates natural follow-up questions when information is missing
5. **Execution** ⚡: Executes calendar tools and processes results
6. **Response Generator** 💬: Creates final responses based on context and results

### Conditional Edges:
- **Calendar vs Direct Response**: Routes calendar-related requests through planning
- **Planner Decision Tree**: Determines if time normalization, clarification, or execution is needed

### Key Benefits:
- ✅ Handles incomplete requests gracefully
- ✅ Normalizes time expressions automatically  
- ✅ Asks clarifying questions naturally
- ✅ Plans multi-step operations
- ✅ Provides sophisticated reasoning capabilities
- ✅ Enhanced user experience with natural conversation flow
