from src.core.database import get_db
from src.core.security import decode_token
from src.exceptions import JSRError
from src.models import Feedback
from src.schemas.feedback import FeedbackRequest, FeedbackResponse

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


router = APIRouter(prefix='/api/feedback', tags=['auth'])


@router.post('/', response_model=FeedbackResponse, status_code=200)
async def save_feedback(payload: FeedbackRequest, request: Request, session: AsyncSession = Depends(get_db)) -> dict[str, bool]:
  fb = Feedback(**payload.model_dump())
  await fb.save(session)
  return dict(processed=True)
