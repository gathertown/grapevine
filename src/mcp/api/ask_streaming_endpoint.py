"""REST API endpoint for streaming question answers via JWT authentication."""

import json

from fastapi import APIRouter, Request
from fastmcp.server.context import Context, set_context
from starlette.responses import StreamingResponse

from src.mcp.mcp_instance import get_mcp
from src.mcp.utils.auth_middleware import AuthenticatedReqDetails, authenticate_request
from src.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


async def event_generator(
    query: str,
    auth_details: AuthenticatedReqDetails,
    previous_response_id: str | None,
):
    """Generate Server-Sent Events from ask_agent_streaming tool."""
    # Import at function level to avoid circular dependencies
    import asyncio

    from src.mcp.api.agent import stream_advanced_search_answer
    from src.mcp.api.prompts import build_system_prompt
    from src.utils.tenant_config import get_tenant_company_context, get_tenant_company_name

    # Create context for the streaming call - must be done outside try block
    mcp = get_mcp()
    context = Context(fastmcp=mcp)
    context.set_state("tenant_id", auth_details.tenant_id)

    if auth_details.permission_audience:
        context.set_state("permission_audience", auth_details.permission_audience)
    if auth_details.permission_principal_token:
        context.set_state("permission_principal_token", auth_details.permission_principal_token)

    # Set context for the entire generator lifetime
    with set_context(context):
        try:
            # Get company information for system prompt
            company_name, company_context_text = await asyncio.gather(
                get_tenant_company_name(auth_details.tenant_id),
                get_tenant_company_context(auth_details.tenant_id),
            )

            # Build system prompt with company information
            system_prompt = await build_system_prompt(
                company_name=company_name,
                company_context_text=company_context_text,
                output_format=None,
                tenant_id=auth_details.tenant_id,
            )

            # Stream events directly from the agent
            async for event in stream_advanced_search_answer(
                query=query,
                system_prompt=system_prompt,
                context=context,
                previous_response_id=previous_response_id,
                files=[],
                reasoning_effort="medium",
                verbosity=None,
                output_format=None,
                model="gpt-5",
            ):
                # Stream each event to the client
                yield f"data: {json.dumps(event)}\n\n"

            # Send done signal
            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error("Error in event generator", error=str(e), exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'data': str(e)})}\n\n"


@router.post("/ask/stream")
async def ask_streaming_endpoint(request: Request) -> StreamingResponse:
    """REST API endpoint for streaming question answers.

    Requires JWT or API Key authentication via Authorization: Bearer header.
    Returns Server-Sent Events (SSE) stream with answer chunks and events.
    """
    try:
        details, error_response = await authenticate_request(request)

        if error_response:
            # Convert JSONResponse to StreamingResponse for consistent return type
            import json

            # Extract status code and body from JSONResponse
            status_code = error_response.status_code
            # We need to re-serialize the body for SSE format
            # error_response.body is bytes, so we decode it
            body_bytes = error_response.body
            if hasattr(body_bytes, "decode"):
                body_str = body_bytes.decode("utf-8")
            else:
                body_str = str(body_bytes)

            try:
                body_content = json.loads(body_str)
                error_msg = body_content.get("error", "Authentication failed")
            except json.JSONDecodeError:
                error_msg = "Authentication failed"

            return StreamingResponse(
                iter([f"data: {json.dumps({'type': 'error', 'data': error_msg})}\n\n"]),
                media_type="text/event-stream",
                status_code=status_code,
            )

        # At this point, we have a valid tenant_id because error_response is None
        assert details is not None

        try:
            body = await request.json()
        except json.JSONDecodeError:
            return StreamingResponse(
                iter(
                    [
                        f"data: {json.dumps({'type': 'error', 'data': 'Invalid JSON in request body'})}\n\n"
                    ]
                ),
                media_type="text/event-stream",
                status_code=400,
            )

        query = body.get("query")
        previous_response_id = body.get("previous_response_id")

        if not query:
            return StreamingResponse(
                iter([f"data: {json.dumps({'type': 'error', 'data': 'query is required'})}\n\n"]),
                media_type="text/event-stream",
                status_code=400,
            )

        return StreamingResponse(
            event_generator(query, details, previous_response_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
            },
        )

    except Exception as e:
        logger.error("Error in /ask/stream endpoint", error=str(e))
        return StreamingResponse(
            iter(
                [
                    f"data: {json.dumps({'type': 'error', 'data': f'Internal server error: {str(e)}'})}\n\n"
                ]
            ),
            media_type="text/event-stream",
            status_code=500,
        )
