#!/bin/bash
# Script to generate PNG files from Mermaid diagrams
# Requires: npm install -g @mermaid-js/mermaid-cli

echo "🎨 Generating PNG diagrams from Mermaid files..."

# Check if mmdc is installed
if ! command -v mmdc &> /dev/null; then
    echo "❌ mermaid-cli not found. Install with: npm install -g @mermaid-js/mermaid-cli"
    exit 1
fi

# Extract and convert main architecture diagram
echo "📊 Converting main architecture diagram..."
sed -n '/```mermaid/,/```/p' docs/athena_langgraph_architecture.md | sed '1d;$d' > temp_architecture.mmd
mmdc -i temp_architecture.mmd -o docs/athena_langgraph_architecture.png -t dark -b transparent

# Extract and convert detailed flow diagram  
echo "🔄 Converting detailed flow diagram..."
sed -n '/```mermaid/,/```/p' docs/detailed_flow.md | sed '1d;$d' > temp_flow.mmd
mmdc -i temp_flow.mmd -o docs/detailed_flow.png -t dark -b transparent

# Cleanup temp files
rm -f temp_*.mmd

echo "✅ PNG diagrams generated successfully!"
echo "📁 Files created:"
echo "   - docs/athena_langgraph_architecture.png"
echo "   - docs/detailed_flow.png"
