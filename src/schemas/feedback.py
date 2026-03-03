from pydantic import BaseModel, Field
from src.models import Feedback


class FeedbackRequest(BaseModel):
  name: str
  email: str 
  message: str
  
class FeedbackResponse(BaseModel):
  processed: bool
  