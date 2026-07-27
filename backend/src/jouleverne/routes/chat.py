"""Chat endpoint — streams agent responses via SSE."""

from fastapi import APIRouter, Request, Depends
from sse_starlette.sse import EventSourceResponse

from ..models.chat import ChatRequest
from ..services.agent import stream_agent_response
from ..services.security import limiter, verify_cognito_auth
from ..config import settings

router = APIRouter(prefix="/v1", tags=["chat"])


@router.post("/chat")
@limiter.limit(settings.RATE_LIMIT)
async def chat(
    request: Request,
    body: ChatRequest,
    _auth: None = Depends(verify_cognito_auth),
):
    """Stream agent response as Server-Sent Events.

    Event types:
    - token: text chunk from the agent
    - trace: reasoning/tool call step
    - citation: source reference
    - done: stream complete
    - error: something went wrong
    """

    def event_generator():
        for event_type, data in stream_agent_response(
            message=body.message,
            session_id=body.session_id,
            web_search=body.web_search,
            session_attributes=body.session_attributes,
            files=body.files,
        ):
            yield {"event": event_type, "data": data}

    return EventSourceResponse(event_generator())
