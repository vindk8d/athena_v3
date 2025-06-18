"""
LangGraph Studio entry point for Athena Executive Assistant Agent.
This file provides a simplified interface for debugging in LangGraph Studio.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from the studio directory FIRST
load_dotenv(Path(__file__).parent / "langgraph_studio.env")

# Add parent directory to path to import agent modules
sys.path.append(str(Path(__file__).parent.parent))

from agent import AthenaLangGraphAgent

# Ensure OPENAI_API_KEY is set
if not os.getenv("OPENAI_API_KEY"):
    raise ValueError("OPENAI_API_KEY not found in environment variables")

# Create and expose the agent graph for LangGraph Studio
def create_graph():
    """Create and return the LangGraph agent for Studio debugging."""
    openai_api_key = os.getenv("OPENAI_API_KEY")
    model_name = os.getenv("LLM_MODEL", "gpt-3.5-turbo")
    temperature = float(os.getenv("LLM_TEMPERATURE", "0.3"))
    
    if not openai_api_key:
        raise ValueError("OPENAI_API_KEY not found in environment variables")
    
    # Create the agent
    agent = AthenaLangGraphAgent(
        openai_api_key=openai_api_key,
        model_name=model_name,
        temperature=temperature
    )
    
    return agent.graph

# Export the graph for LangGraph Studio
graph = create_graph() 