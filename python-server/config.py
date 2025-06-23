import os
from pathlib import Path
from dotenv import load_dotenv

# Detect if we're in a production environment
IS_PRODUCTION = os.getenv("RENDER") or os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("VERCEL") or os.getenv("HEROKU_APP_NAME")

if not IS_PRODUCTION:
    # Development mode: Try to load from .env file
    ROOT_DIR = Path(__file__).parent.parent
    ENV_FILE = ROOT_DIR / ".env"
    
    if ENV_FILE.exists():
        load_dotenv(ENV_FILE)
        print(f"✅ Development: Loaded environment variables from: {ENV_FILE}")
    else:
        # Fallback: try to load from current directory
        load_dotenv()
        print(f"⚠️  Development: .env file not found at {ENV_FILE}, trying current directory")
else:
    # Production mode: Environment variables should already be set by the platform
    print("✅ Production: Using platform-provided environment variables")

class Config:
    # OpenAI Configuration
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    
    # Supabase Configuration
    SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY") or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")
    SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    
    # Database Configuration (for PostgreSQL checkpointing)
    DATABASE_URL = os.getenv("DATABASE_URL")
    POSTGRES_CONNECTION_STRING = os.getenv("POSTGRES_CONNECTION_STRING")
    
    # Server Configuration
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", 8000))
    
    # LangChain Configuration
    LLM_MODEL = os.getenv("LLM_MODEL", "gpt-3.5-turbo")
    LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    
    # Environment-aware frontend URL configuration
    FRONTEND_URL = os.getenv("FRONTEND_URL", "https://athena-v3-rwuk.onrender.com" if IS_PRODUCTION else "http://localhost:3000")
    
    @classmethod
    def validate(cls):
        """Validate that required environment variables are set."""
        if not cls.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY environment variable is required")
        
        return True 