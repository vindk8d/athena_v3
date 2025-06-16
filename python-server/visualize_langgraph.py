#!/usr/bin/env python3
"""
Dynamic visualization tool for Athena's LangGraph structure.
Generates Mermaid diagrams by analyzing the actual graph implementation.
"""

import inspect
import os
import ast
from typing import Dict, Any, List, Optional
from pathlib import Path
import logging
from datetime import datetime
import textwrap

# Import the actual graph implementation
from agent import AthenaState

logger = logging.getLogger(__name__)

class MockAgent:
    """Mock agent for visualization when no API key is available."""
    
    def __init__(self):
        """Initialize with mock graph creation."""
        self._create_graph()
    
    def _create_graph(self):
        """Mock implementation of graph creation."""
        # This is the actual graph structure from agent.py
        graph_structure = """
        # Create the graph
        graph = StateGraph(AthenaState)
        
        # Add nodes
        graph.add_node("input_interpreter", self._input_interpreter_node)
        graph.add_node("planner", self._planner_node)
        graph.add_node("time_normalizer", self._time_normalizer_node)
        graph.add_node("clarification", self._clarification_node)
        graph.add_node("execution", self._execution_node)
        graph.add_node("response_generator", self._response_generator_node)
        
        # Define the graph flow
        graph.add_edge(START, "input_interpreter")
        
        # Conditional edge from input_interpreter
        graph.add_conditional_edges(
            "input_interpreter",
            self._should_use_calendar_tools,
            {
                "calendar": "planner",
                "direct_response": "response_generator"
            }
        )
        
        # Conditional edges from planner
        graph.add_conditional_edges(
            "planner",
            self._planner_decision,
            {
                "needs_time_normalization": "time_normalizer",
                "needs_clarification": "clarification",
                "ready_for_execution": "execution",
                "direct_response": "response_generator"
            }
        )
        
        # Edges back to planner
        graph.add_edge("time_normalizer", "planner")
        graph.add_edge("clarification", END)  # Clarification ends the flow, waiting for user response
        
        # Execution to response
        graph.add_edge("execution", "response_generator")
        graph.add_edge("response_generator", END)
        """
        self.graph_source = textwrap.dedent(graph_structure)

class GraphAnalyzer:
    """Analyzes the LangGraph implementation to extract structure and behavior."""
    
    def __init__(self):
        """Initialize the analyzer."""
        self.agent = MockAgent()  # Use mock agent to avoid API key requirement
        self.nodes = self._get_node_methods()
        self.state_fields = self._get_state_fields()
        self.transitions = self._analyze_transitions()
    
    def _get_node_methods(self) -> Dict[str, Any]:
        """Extract information about each node in the graph."""
        nodes = {
            "input_interpreter": {
                "name": "input_interpreter",
                "method": "_input_interpreter_node",
                "description": "Interpret the input and classify intent.",
                "state_updates": ["intent", "intent_confidence", "is_calendar_related", "temporal_references", "current_datetime"]
            },
            "planner": {
                "name": "planner",
                "method": "_planner_node",
                "description": "Create execution plan and assess information completeness.",
                "state_updates": ["plan", "plan_complete", "required_info", "missing_info", "next_node"]
            },
            "time_normalizer": {
                "name": "time_normalizer",
                "method": "_time_normalizer_node",
                "description": "Normalize time references to tool-compatible formats.",
                "state_updates": ["normalized_times", "time_parsing_errors"]
            },
            "clarification": {
                "name": "clarification",
                "method": "_clarification_node",
                "description": "Generate clarification questions for missing information.",
                "state_updates": ["needs_clarification", "clarification_question", "clarification_context", "final_response"]
            },
            "execution": {
                "name": "execution",
                "method": "_execution_node",
                "description": "Execute the planned tools.",
                "state_updates": ["tool_results", "execution_errors"]
            },
            "response_generator": {
                "name": "response_generator",
                "method": "_response_generator_node",
                "description": "Generate the final response.",
                "state_updates": ["final_response", "response_metadata", "conversation_complete"]
            }
        }
        return nodes
    
    def _get_state_fields(self) -> List[str]:
        """Extract all fields from the AthenaState class."""
        return list(AthenaState.__annotations__.keys())
    
    def _analyze_transitions(self) -> List[Dict[str, Any]]:
        """Extract the graph transitions from the _create_graph method."""
        try:
            tree = ast.parse(self.agent.graph_source)
            transitions = []
            
            class TransitionVisitor(ast.NodeVisitor):
                def visit_Call(self, node):
                    # Handle add_edge calls
                    if isinstance(node.func, ast.Attribute) and node.func.attr == 'add_edge':
                        if len(node.args) >= 2:
                            from_node = self._get_node_name(node.args[0])
                            to_node = self._get_node_name(node.args[1])
                            transitions.append({
                                'from': from_node,
                                'to': to_node,
                                'condition': None
                            })
                    
                    # Handle add_conditional_edges calls
                    elif isinstance(node.func, ast.Attribute) and node.func.attr == 'add_conditional_edges':
                        if len(node.args) >= 3:
                            from_node = self._get_node_name(node.args[0])
                            condition_func = self._get_node_name(node.args[1])
                            
                            # Extract edges from the dictionary
                            if isinstance(node.args[2], ast.Dict):
                                for key, value in zip(node.args[2].keys, node.args[2].values):
                                    condition = ast.unparse(key).strip('"\'')
                                    to_node = ast.unparse(value).strip('"\'')
                                    transitions.append({
                                        'from': from_node,
                                        'to': to_node,
                                        'condition': condition
                                    })
                
                def _get_node_name(self, node):
                    if isinstance(node, ast.Constant):
                        return node.value
                    elif isinstance(node, ast.Name):
                        return node.id
                    elif isinstance(node, ast.Attribute):
                        return node.attr
                    return ast.unparse(node).strip('"\'')
            
            visitor = TransitionVisitor()
            visitor.visit(tree)
            return transitions
        except Exception as e:
            logger.error(f"Error parsing source code: {e}")
            return []
    
    def generate_main_flow_diagram(self) -> str:
        """Generate a Mermaid diagram showing the main flow of the graph."""
        mermaid = ["graph TD"]
        
        # Add nodes with styles
        for node in self.nodes.values():
            node_id = f"{node['name']}_node"
            label = f"{node['name']}<br/>{node['description']}"
            mermaid.append(f'    {node_id}["{label}"]')
        
        # Add START and END nodes with circle style
        mermaid.append('    START(("START"))')
        mermaid.append('    END(("END"))')
        
        # Add transitions with conditions
        for t in self.transitions:
            from_node = t['from']
            to_node = t['to']
            
            # Clean up node names
            if from_node == 'START':
                from_node = 'START'
            elif from_node == 'END':
                from_node = 'END'
            elif not from_node.endswith('_node'):
                from_node = f"{from_node}_node"
            
            if to_node == 'START':
                to_node = 'START'
            elif to_node == 'END':
                to_node = 'END'
            elif not to_node.endswith('_node'):
                to_node = f"{to_node}_node"
            
            # Add the edge with condition if present
            if t['condition']:
                condition = t['condition'].replace('"', "'")
                mermaid.append(f'    {from_node} -->|"{condition}"| {to_node}')
            else:
                mermaid.append(f'    {from_node} --> {to_node}')
        
        return "\n".join(mermaid)
    
    def generate_state_diagram(self) -> str:
        """Generate a Mermaid diagram showing the state updates in each node."""
        mermaid = ["graph TD"]
        
        # Group state fields by category
        state_groups = {
            "Core": ["messages"],
            "User Info": ["user_id", "contact_id", "user_details", "user_timezone", "current_datetime"],
            "Intent": ["intent", "intent_confidence", "is_calendar_related"],
            "Planning": ["plan", "plan_complete", "required_info", "missing_info"],
            "Time": ["temporal_references", "normalized_times", "time_parsing_errors"],
            "Clarification": ["needs_clarification", "clarification_question", "clarification_context"],
            "Tools": ["tools_to_execute", "tool_results", "execution_errors"],
            "Response": ["final_response", "response_metadata"],
            "Flow Control": ["next_node", "conversation_complete"]
        }
        
        # Add state container with subgroups
        mermaid.append('    subgraph State["AthenaState"]')
        for group_name, fields in state_groups.items():
            mermaid.append(f'        subgraph {group_name}')
            for field in fields:
                if field in self.state_fields:
                    mermaid.append(f'            {field}["{field}"]')
            mermaid.append('        end')
        mermaid.append('    end')
        
        # Add nodes and their state updates
        for node in self.nodes.values():
            node_id = f"{node['name']}_node"
            updates = node['state_updates']
            
            # Add node with description
            mermaid.append(f'    {node_id}["{node["name"]}<br/>{node["description"]}"]')
            
            # Add connections to state fields
            for update in updates:
                if update in self.state_fields:
                    mermaid.append(f'    {node_id} -->|"updates"| {update}')
        
        return "\n".join(mermaid)

def main():
    """Generate and save the diagrams."""
    try:
        analyzer = GraphAnalyzer()
        
        # Generate main flow diagram
        main_flow = analyzer.generate_main_flow_diagram()
        print("\nMain Flow Diagram:")
        print("```mermaid")
        print(main_flow)
        print("```")
        
        # Generate state diagram
        state_diagram = analyzer.generate_state_diagram()
        print("\nState Update Diagram:")
        print("```mermaid")
        print(state_diagram)
        print("```")
        
        # Save diagrams to files
        output_dir = Path("docs")
        output_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        with open(output_dir / f"main_flow_{timestamp}.mmd", "w") as f:
            f.write(main_flow)
        
        with open(output_dir / f"state_diagram_{timestamp}.mmd", "w") as f:
            f.write(state_diagram)
        
        print(f"\nDiagrams saved to docs/main_flow_{timestamp}.mmd and docs/state_diagram_{timestamp}.mmd")
        
    except Exception as e:
        logger.error(f"Error generating diagrams: {e}")
        raise

if __name__ == "__main__":
    main() 