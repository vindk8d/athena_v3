from typing import List, Dict, Any, Optional
from langchain.memory import ConversationBufferMemory
from langchain.schema import BaseMessage, HumanMessage, AIMessage
from supabase import create_client, Client
import os
import logging

logger = logging.getLogger(__name__)

class DatabaseMemory:
    """Manages conversation memory with database persistence and retrieval."""
    
    def __init__(self):
        self.supabase_url = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
        self.supabase_key = os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")
        
        if not self.supabase_url or not self.supabase_key:
            logger.warning("Supabase credentials not found. Database memory will be disabled.")
            self.supabase = None
        else:
            self.supabase: Client = create_client(self.supabase_url, self.supabase_key)
    
    async def get_recent_messages(self, contact_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Retrieve the last N messages for a contact from the database."""
        if not self.supabase:
            return []
        
        try:
            response = self.supabase.table('messages').select(
                'sender, content, created_at, metadata'
            ).eq(
                'contact_id', contact_id
            ).order(
                'created_at', desc=True
            ).limit(limit).execute()
            
            if response.data:
                # Reverse to get chronological order (oldest first)
                return list(reversed(response.data))
            return []
            
        except Exception as e:
            logger.error(f"Error retrieving messages from database: {e}")
            return []
    
    def convert_db_messages_to_langchain(self, db_messages: List[Dict[str, Any]]) -> List[BaseMessage]:
        """Convert database messages to LangChain message format."""
        langchain_messages = []
        
        for msg in db_messages:
            content = msg.get('content', '')
            sender = msg.get('sender', 'unknown')
            
            if sender == 'user':
                langchain_messages.append(HumanMessage(content=content))
            elif sender == 'bot':
                langchain_messages.append(AIMessage(content=content))
            # Skip system messages or unknown senders
            
        return langchain_messages


class EnhancedConversationMemory:
    """Enhanced conversation memory that combines buffer memory with database history."""
    
    def __init__(self, contact_id: str, max_token_limit: int = 2000):
        self.contact_id = contact_id
        self.max_token_limit = max_token_limit
        self.db_memory = DatabaseMemory()
        
        # Initialize the buffer memory
        self.buffer_memory = ConversationBufferMemory(
            return_messages=True,
            memory_key="chat_history"
        )
        
        # Flag to track if we've loaded database history
        self._db_history_loaded = False
    
    async def load_database_history(self) -> None:
        """Load recent conversation history from database."""
        if self._db_history_loaded:
            return
        
        try:
            db_messages = await self.db_memory.get_recent_messages(self.contact_id, limit=5)
            langchain_messages = self.db_memory.convert_db_messages_to_langchain(db_messages)
            
            # Add messages to buffer memory
            for message in langchain_messages:
                self.buffer_memory.chat_memory.add_message(message)
            
            self._db_history_loaded = True
            logger.info(f"Loaded {len(langchain_messages)} messages from database for contact {self.contact_id}")
            
        except Exception as e:
            logger.error(f"Error loading database history: {e}")
    
    async def add_message(self, message: BaseMessage) -> None:
        """Add a message to the conversation memory."""
        self.buffer_memory.chat_memory.add_message(message)
        
        # Simple token management - remove oldest messages if we exceed limit
        self._manage_memory_size()
    
    def _manage_memory_size(self) -> None:
        """Manage memory size by removing oldest messages if needed."""
        messages = self.buffer_memory.chat_memory.messages
        
        # Simple approximation: average 4 chars per token
        total_chars = sum(len(msg.content) for msg in messages)
        estimated_tokens = total_chars // 4
        
        if estimated_tokens > self.max_token_limit:
            # Remove oldest messages (keep system message if it exists)
            messages_to_remove = estimated_tokens - self.max_token_limit // 2
            chars_removed = 0
            
            # Start from index 1 to preserve potential system message at index 0
            start_idx = 1 if messages and hasattr(messages[0], 'type') and messages[0].type == 'system' else 0
            
            for i in range(start_idx, len(messages)):
                if chars_removed >= messages_to_remove * 4:
                    break
                chars_removed += len(messages[i].content)
                
            # Remove the calculated number of messages
            remove_count = i - start_idx if i > start_idx else 0
            if remove_count > 0:
                for _ in range(remove_count):
                    if len(messages) > start_idx + 1:  # Keep at least one message
                        messages.pop(start_idx)
                
                logger.info(f"Removed {remove_count} messages to manage memory size")
    
    async def get_messages(self) -> List[BaseMessage]:
        """Get all messages from memory."""
        await self.load_database_history()
        return self.buffer_memory.chat_memory.messages
    
    async def get_memory_variables(self) -> Dict[str, Any]:
        """Get memory variables for use in chains."""
        await self.load_database_history()
        return self.buffer_memory.load_memory_variables({})
    
    def clear(self) -> None:
        """Clear the conversation memory."""
        self.buffer_memory.clear()
        self._db_history_loaded = False


class MemoryManager:
    """Manages conversation memories for multiple contacts."""
    
    def __init__(self):
        self.memories: Dict[str, EnhancedConversationMemory] = {}
    
    def get_memory(self, contact_id: str) -> EnhancedConversationMemory:
        """Get or create memory for a contact."""
        if contact_id not in self.memories:
            self.memories[contact_id] = EnhancedConversationMemory(contact_id)
        
        return self.memories[contact_id]
    
    async def add_user_message(self, contact_id: str, content: str) -> None:
        """Add a user message to the contact's memory."""
        memory = self.get_memory(contact_id)
        await memory.add_message(HumanMessage(content=content))
    
    async def add_ai_message(self, contact_id: str, content: str) -> None:
        """Add an AI message to the contact's memory."""
        memory = self.get_memory(contact_id)
        await memory.add_message(AIMessage(content=content))
    
    def clear_memory(self, contact_id: str) -> None:
        """Clear memory for a specific contact."""
        if contact_id in self.memories:
            self.memories[contact_id].clear()
    
    def cleanup_inactive_memories(self, max_inactive_time: int = 3600) -> None:
        """Remove memories that haven't been accessed recently (future enhancement)."""
        # This could be implemented with last_accessed tracking
        pass

# Global memory manager instance
memory_manager = MemoryManager() 