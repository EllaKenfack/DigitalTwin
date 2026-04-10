"""
Lambda entry point to smoke-test conversation flow (Bedrock + memory).

Deploy as a separate Lambda function and set the handler to:
  conversation_test_handler.lambda_handler

Use the same IAM role and env vars as the main API (USE_S3, S3_BUCKET, BEDROCK_MODEL_ID, etc.).

Invoke with an empty payload or:
  {"message": "optional user text", "session_id": "optional-uuid"}
"""

import json
import uuid
from datetime import datetime

from server import call_bedrock, load_conversation, save_conversation


def _parse_payload(event: dict) -> dict:
    if not event:
        return {}
    body = event.get("body")
    if body:
        if isinstance(body, str):
            return json.loads(body) if body.strip() else {}
        return body
    # Direct Lambda invoke (no API Gateway wrapper)
    if "message" in event or "session_id" in event:
        return event
    return {}


def lambda_handler(event, context):
    """
    One full chat turn: load history, call Bedrock, persist messages.
    Returns API Gateway-compatible response when invoked via HTTP; plain dict is fine for direct invoke.
    """
    try:
        payload = _parse_payload(event or {})
        message = payload.get("message") or (
            "Reply with one short sentence so we can verify the conversation path works."
        )
        session_id = payload.get("session_id") or str(uuid.uuid4())

        conversation = load_conversation(session_id)
        assistant_response = call_bedrock(conversation, message)

        now = datetime.now().isoformat()
        conversation.append({"role": "user", "content": message, "timestamp": now})
        conversation.append(
            {"role": "assistant", "content": assistant_response, "timestamp": now}
        )
        save_conversation(session_id, conversation)

        result = {
            "ok": True,
            "session_id": session_id,
            "response": assistant_response,
            "message_count": len(conversation),
        }
        return _response(200, result)
    except Exception as e:
        # call_bedrock raises FastAPI HTTPException on Bedrock errors
        status = getattr(e, "status_code", None)
        detail = getattr(e, "detail", None)
        if status is not None and detail is not None:
            err = detail if isinstance(detail, str) else str(detail)
            return _response(status, {"ok": False, "error": err})
        return _response(500, {"ok": False, "error": str(e)})


def _response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }
