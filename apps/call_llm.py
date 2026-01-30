# ...imports unchanged...
import os
import json
import requests
from typing import List, Dict, Any
from openai import OpenAI
from generic_storage import get_thread_messages

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
CLAUDE_BASE_URL = "https://api.anthropic.com/v1/"
# Encryption service (Argonaut privacy-filter)
PRIVACY_FILTER_URL = os.getenv("PRIVACY_FILTER_URL", "https://privacy-filter.argonaut.svc.cluster.local:7070")
ENCRYPTION_ENABLED = os.getenv("ENCRYPTION_ENABLED", "false").strip().lower() == "true"
ENCRYPTION_TIMEOUT = float(os.getenv("ENCRYPTION_TIMEOUT", "10"))


def _enc_enabled() -> bool:
    # Only encrypt if explicitly enabled and we have a URL
    return ENCRYPTION_ENABLED and bool(PRIVACY_FILTER_URL)

def _pf_post(endpoint: str, payload: Dict[str, Any], logger=None) -> Dict[str, Any]:
    url = f"{PRIVACY_FILTER_URL.rstrip('/')}/{endpoint.lstrip('/')}"
    try:
        r = requests.post(url, json=payload, timeout=ENCRYPTION_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        if logger:
            logger.warning(f"[privacy-filter] {endpoint} failed: {e}. Proceeding without transform.")
        # Return pass-through on failure
        return {"text": payload.get("text", "")}

def _encrypt_text(text: str, scope_id: str, logger=None) -> str:
    if not _enc_enabled():
        return text
    resp = _pf_post("encrypt", {"text": text, "scope_id": scope_id, "enabled": True}, logger=logger)
    return resp.get("text", text)

def _decrypt_text(text: str, scope_id: str, logger=None) -> str:
    if not _enc_enabled():
        return text
    resp = _pf_post("decrypt", {"text": text, "scope_id": scope_id}, logger=logger)
    return resp.get("text", text)

def _encrypt_messages(msgs: List[Dict[str, str]], scope_id: str, logger=None) -> List[Dict[str, str]]:
    """Encrypts each message.content (string). Leaves roles intact."""
    if not _enc_enabled():
        return msgs
    out: List[Dict[str, str]] = []
    for m in msgs:
        content = m.get("content", "")
        if isinstance(content, str) and content:
            enc = _encrypt_text(content, scope_id, logger=logger)
            out.append({**m, "content": enc})
        else:
            out.append(m)
    return out


def _split_system(messages: List[Dict[str, str]]) -> tuple[str, List[Dict[str, str]]]:
    """If first message is system, return (system_text, remaining_messages)."""
    if messages and (messages[0].get("role") or "").strip().lower() == "system":
        return messages[0].get("content", "") or "", messages[1:]
    return "", messages

def _extract_text_from_webhook_response(resp_obj: Any) -> str:
    # (unchanged) ...
    if not isinstance(resp_obj, dict):
        return str(resp_obj)
    raw = resp_obj.get("response")
    if raw is None:
        return json.dumps(resp_obj)
    try:
        parsed = json.loads(raw)
        content = parsed.get("content")
        if isinstance(content, list):
            pieces = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    t = block.get("text")
                    if isinstance(t, str):
                        pieces.append(t)
            if pieces:
                return "".join(pieces)
        if isinstance(parsed.get("output_text"), str):
            return parsed["output_text"]
        if isinstance(parsed.get("completion"), str):
            return parsed["completion"]
        return json.dumps(parsed)
    except Exception:
        return str(raw)

def _call_bedrock_webhook(messages: List[Dict[str, str]], system_text: str,
                          temperature: float, max_tokens: int, logger=None) -> str:
    """
    POSTs to claude_chat.py.
    Adds optional 'system' when present; removes 'system' from messages list.
    """
    url = os.getenv("CLAUDE_WEBHOOK_URL")
    if not url:
        raise RuntimeError("CLAUDE_WEBHOOK_URL not set (required for Bedrock webhook mode)")

    token = os.getenv("CLAUDE_WEBHOOK_TOKEN")
    timeout = float(os.getenv("WEBHOOK_TIMEOUT", "30"))

    payload: Dict[str, Any] = {
        "messages": messages,           # user/assistant only
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
    }
    if system_text:
        payload["system"] = system_text

    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    if logger:
        logger.info(f"Calling Bedrock webhook: {url}")

    r = requests.post(url, headers=headers, json=payload, timeout=timeout)
    r.raise_for_status()
    data = r.json() if "application/json" in (r.headers.get("Content-Type") or "") else {"response": r.text}
    text = _extract_text_from_webhook_response(data)

    if logger:
        logger.debug(f"Webhook raw response: {data}")
        logger.info("Bedrock webhook responded successfully.")

    return text

def get_llm_response(thread_ts, max_response_tokens, temperature, logger=None):
    use_bedrock = os.getenv("USE_BEDROCK", "false").lower() == "true" or bool(os.getenv("CLAUDE_WEBHOOK_URL"))
    openai_key = os.getenv("OPENAI_API_KEY")
    claude_key = os.getenv("CLAUDE_API_KEY") or os.getenv("ANTHROPIC_API_KEY")  # optional
    gemini_key = os.getenv("GEMINI_API_KEY")

    client = None
    provider = None
    model_to_use = None

    try:
        # Load history (unchanged)
        msgs = get_thread_messages(thread_ts, logger=logger)
        chat_messages = [{
            "role": m.get("role", "") or "user",
            "content": m.get("content", "") or ""
        } for m in msgs]

        # 🔐 NEW: encrypt message contents (system/user/assistant) before we do anything else
        # (scope_id = thread_ts gives “same-secret” equality inside this thread)
        enc_messages = _encrypt_messages(chat_messages, scope_id=str(thread_ts), logger=logger)

        # Extract system for Bedrock only (do it on the encrypted messages so system is protected too)
        system_text, non_system_msgs = _split_system(enc_messages)

        # 1) Bedrock (via webhook)
        if use_bedrock:
            provider = "BedrockWebhook"
            raw = _call_bedrock_webhook(
                messages=non_system_msgs,   # already encrypted
                system_text=system_text,    # already encrypted
                temperature=temperature,
                max_tokens=max_response_tokens,
                logger=logger,
            )
            return _decrypt_text(raw, scope_id=str(thread_ts), logger=logger)

        # 2) OpenAI
        if openai_key:
            provider = "OpenAI"
            client = OpenAI(api_key=openai_key)
            model_to_use = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        # 3) Claude (OpenAI-compatible)
        elif claude_key:
            provider = "Claude(OpenAI-compat)"
            client = OpenAI(api_key=claude_key, base_url=CLAUDE_BASE_URL)
            model_to_use = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5")

        # 4) Gemini (OpenAI-compatible)
        elif gemini_key:
            provider = "Gemini(OpenAI-compat)"
            client = OpenAI(api_key=gemini_key, base_url=GEMINI_BASE_URL)
            model_to_use = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

        else:
            if logger: logger.error("No provider configured.")
            return "Error: No provider configured."

        if logger:
            logger.info(f"Using provider: {provider} with model: {model_to_use}")

        # For OpenAI/Claude-compat/Gemini, send the ENCRYPTED list with system intact
        completion = client.chat.completions.create(
            messages=enc_messages,      # ⬅️ encrypted messages
            model=model_to_use,
            max_tokens=max_response_tokens,
            temperature=temperature,
            top_p=float(os.getenv("top_p", 0.5)),
        )
        raw_text = completion.choices[0].message.content or ""

        # 🔓 Decrypt before returning
        return _decrypt_text(raw_text, scope_id=str(thread_ts), logger=logger)

    except requests.HTTPError as e:
        if logger:
            logger.error(f"Webhook HTTP error: {e} - {getattr(e.response, 'text', '')}")
        return "Error: Webhook HTTP error."
    except Exception as e:
        if logger:
            logger.error(f"Error in get_llm_response with {provider}: {e}")
        return "Error processing your request."
