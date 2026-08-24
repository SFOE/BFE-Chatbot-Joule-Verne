"""Chat endpoint — streams agent responses via SSE."""

import base64

from fastapi import APIRouter, Request, Depends
from sse_starlette.sse import EventSourceResponse

from ..models.chat import ChatRequest
from ..services.agent import stream_agent_response
from ..services.security import limiter, verify_cognito_auth, extract_user_email
from ..services.usage import log_usage
from ..config import settings

router = APIRouter(prefix="/v1", tags=["chat"])


def _build_agent_files(body: ChatRequest) -> list[dict] | None:
    """Convert frontend file payloads to Bedrock sessionState.files format."""
    if not body.files:
        return None
    agent_files = []
    for f in body.files:
        agent_files.append({
            "name": f.name,
            "source": {
                "sourceType": "BYTE_CONTENT",
                "byteContent": {
                    "data": base64.b64decode(f.data),
                    "mediaType": f.media_type,
                },
            },
            "useCase": "CODE_INTERPRETER",
        })
    return agent_files


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
    log_usage(extract_user_email(request), locale=body.locale, web_search=body.web_search)

    agent_files = _build_agent_files(body)

    def event_generator():
        for event_type, data in stream_agent_response(
            message=body.message,
            session_id=body.session_id,
            web_search=body.web_search,
            locale=body.locale,
            session_attributes=body.session_attributes,
            files=agent_files,
        ):
            yield {"event": event_type, "data": data}

    return EventSourceResponse(event_generator())
