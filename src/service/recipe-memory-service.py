from google.adk.memory import InMemoryMemoryService
from google.adk.sessions import InMemorySessionService

class RecipeMemoryService:
    def __init__(self):
        self.memory_service = InMemoryMemoryService()
        self.session_service = InMemorySessionService()
    
    async def add_session_to_memory(self, session):
        """Add a completed cooking session to memory"""
        await self.memory_service.add_session_to_memory(session)
    
    def get_memory_service(self):
        return self.memory_service
    
    def get_session_service(self):
        return self.session_service
