#!/usr/bin/env python3
"""
Setup script for LangGraph Studio debugging.
This script validates the environment and helps set up LangGraph Studio.
"""

import os
import sys
import subprocess
from pathlib import Path

def check_environment():
    """Check if all required environment variables are set."""
    required_vars = [
        "OPENAI_API_KEY",
        "LANGCHAIN_API_KEY"
    ]
    
    # Load from langgraph_studio.env if it exists
    env_file = Path("langgraph_studio.env")
    if env_file.exists():
        print("✓ Found langgraph_studio.env file")
        with open(env_file) as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    key, value = line.strip().split("=", 1)
                    if value and not value.startswith("your_"):
                        os.environ[key] = value
    else:
        print("❌ langgraph_studio.env file not found")
        return False
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var) or os.getenv(var).startswith("your_"):
            missing_vars.append(var)
    
    if missing_vars:
        print(f"❌ Missing or placeholder environment variables: {', '.join(missing_vars)}")
        return False
    
    print("✓ All required environment variables are set")
    return True

def check_dependencies():
    """Check if all required packages are installed."""
    try:
        import langgraph
        import langchain_openai
        import langsmith
        print("✓ All required packages are installed")
        return True
    except ImportError as e:
        print(f"❌ Missing package: {e}")
        return False

def install_langchain_cli():
    """Install LangChain CLI if not already installed."""
    try:
        result = subprocess.run(["langchain", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            print("✓ LangChain CLI is already installed")
            return True
    except FileNotFoundError:
        pass
    
    print("Installing LangChain CLI...")
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "langchain-cli"], check=True)
        print("✓ LangChain CLI installed successfully")
        return True
    except subprocess.CalledProcessError:
        print("❌ Failed to install LangChain CLI")
        return False

def main():
    """Main setup function."""
    print("🚀 Setting up LangGraph Studio for Athena Agent")
    print("=" * 50)
    
    # Check current directory
    studio_dir = Path(__file__).parent
    parent_dir = studio_dir.parent
    
    if not (parent_dir / "agent.py").exists():
        print("❌ Please ensure you're in the correct directory structure")
        print("   Expected: python-server/studio/setup_studio.py")
        sys.exit(1)
    
    # Check environment
    if not check_environment():
        print("\n📝 Next steps:")
        print("1. Copy your API keys from /app/.env.local")
        print("2. Update the studio/langgraph_studio.env file with your actual values")
        print("3. Make sure to set LANGCHAIN_API_KEY (get it from https://smith.langchain.com)")
        sys.exit(1)
    
    # Check dependencies
    if not check_dependencies():
        print("Run: pip install -r ../requirements.txt")
        sys.exit(1)
    
    # Install LangChain CLI
    if not install_langchain_cli():
        sys.exit(1)
    
    print("\n✅ Setup complete! You can now run LangGraph Studio:")
    print("   cd python-server/studio")
    print("   langchain serve --port=8123")
    print("\nThen open: http://localhost:8123")
    print("\nYour agent graph will be available as 'athena_agent'")

if __name__ == "__main__":
    main() 