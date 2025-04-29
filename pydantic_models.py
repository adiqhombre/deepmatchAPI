from pydantic import BaseModel

class StartSessionResponse(BaseModel):
    session_id: str
    reply: str
    done: bool

class MessageRequest(BaseModel):
    session_id: str
    user_input: str

class MessageResponse(BaseModel):
    reply: str
    done: bool
    profile: dict | None = None