"""Feedback endpoint — save user ratings and comments."""

from fastapi import APIRouter, Request, Depends

from ..models.feedback import FeedbackRequest, FeedbackResponse
from ..services.feedback import save_feedback
from ..services.security import limiter, verify_cognito_auth
from ..config import settings

router = APIRouter(prefix="/v1", tags=["feedback"])


@router.post("/feedback", response_model=FeedbackResponse)
@limiter.limit(settings.RATE_LIMIT)
async def submit_feedback(
    request: Request,
    body: FeedbackRequest,
    _auth: None = Depends(verify_cognito_auth),
):
    """Save user feedback (thumbs up/down + optional comment) to S3."""
    s3_key, timestamp = save_feedback(
        session_id=body.session_id,
        message_index=body.message_index,
        rating=body.rating,
        user_query=body.user_query,
        agent_response=body.agent_response,
        agent_variant=body.agent_variant,
        comment=body.comment,
        retrieved_chunks=body.retrieved_chunks,
        tools_used=body.tools_used,
        s3_key_override=body.s3_key_override,
        original_timestamp=body.original_timestamp,
    )
    return FeedbackResponse(s3_key=s3_key, timestamp=timestamp)
