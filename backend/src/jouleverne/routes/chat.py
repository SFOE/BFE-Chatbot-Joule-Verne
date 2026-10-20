"""Chat endpoint — streams agent responses via SSE."""

import base64

from fastapi import APIRouter, Request, Depends
from sse_starlette.sse import EventSourceResponse

from ..models.chat import ChatRequest
from ..services.agent import stream_agent_response
from ..services.security import (
    limiter,
    verify_cognito_auth,
    extract_user_email,
    extract_user_sub,
)
from ..services import conversations as convo
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

    # Pseudonymous user id scopes the agent's stored transcript to the person.
    # None in local dev (no ALB headers) => agent uses the legacy un-scoped
    # layout, so chat keeps working without an identity.
    user_id = extract_user_sub(request)

    # Honour the save opt-in: when the user has NOT opted in, the agent stores
    # the transcript in the short-lived ephemeral prefix (full in-session memory
    # preserved, but cleaned up within a day). Unknown user => treat as opt-out.
    save_history = bool(user_id) and convo.get_save_enabled(user_id)

    agent_files = _build_agent_files(body)
    file_refs = [r.model_dump() for r in body.file_refs] if body.file_refs else None

    def event_generator():
        for event_type, data in stream_agent_response(
            message=body.message,
            session_id=body.session_id,
            user_id=user_id,
            save_history=save_history,
            web_search=body.web_search,
            agent_type=body.agent_type,
            specific_kb_id=body.specific_kb_id,
            capabilities=body.capabilities.model_dump() if body.capabilities else None,
            locale=body.locale,
            session_attributes=body.session_attributes,
            files=agent_files,
            file_refs=file_refs,
        ):
            yield {"event": event_type, "data": data}

    return EventSourceResponse(event_generator())