"""
DefaultGraphs for Argonaut (handles the default `case _` branch only, NO auto-run).

Flow:
1) Bootstrap (if first message or no system msg): write system prompt; append MOST_IMPORTANT to user's first turn.
2) Save user message
3) Call LLM for assistant reply
4) Save assistant message
5) Post "NAUT ... type RUN ..." prompt back to the channel
6) END

This module intentionally contains NO auto-run logic.
"""

from __future__ import annotations
from typing import Any, Dict, TypedDict, Optional
import os
import time
import uuid

# LangGraph
from langgraph.graph import StateGraph, END

# Your existing helpers
from send_response import send_response
from generic_storage import update_message, get_thread_messages
from call_llm import get_llm_response

# System prompt builder
try:
    from create_system_text import create_system_text
except Exception:
    create_system_text = None  # will be handled gracefully

# Try to import MOST_IMPORTANT guidance from your webhook module; fallback to empty if not importable
try:
    from new_webhook_handler import MOST_IMPORTANT  # adjust if the constant lives elsewhere
except Exception:
    MOST_IMPORTANT = ""


# ---------------------
# State schema (minimal)
# ---------------------
class IOState(TypedDict, total=False):
    thread_ts: str
    channel: Optional[str]
    user: Optional[str]


class AuditState(TypedDict, total=False):
    graph_name: str
    run_id: str
    step: str


class StatusState(TypedDict, total=False):
    phase: str
    started_at: float
    updated_at: float


class DefaultState(TypedDict, total=False):
    io: IOState
    text: str
    effective_user_text: str  # user text possibly appended with MOST_IMPORTANT
    response_text: str
    audit: AuditState
    status: StatusState
    payload: Dict[str, Any]
    result: Dict[str, Any]  # return sentinel


GRAPH_NAME = "DefaultGraph_NoAutoRun"


def _now() -> float:
    return time.time()


def _build_state(payload: Dict[str, Any],
                 max_response_tokens: int,
                 temperature: float) -> DefaultState:
    """Create initial state from payload (no side-effects)."""
    thread_ts = payload.get("thread_ts") or f"auto-{uuid.uuid4().hex[:12]}"
    channel = payload.get("channel")
    user = payload.get("user")
    text = (payload.get("text") or "").strip()

    state: DefaultState = {
        "io": {"thread_ts": thread_ts, "channel": channel, "user": user},
        "text": text,
        "effective_user_text": text,
        "audit": {"graph_name": GRAPH_NAME, "run_id": uuid.uuid4().hex, "step": "build_state"},
        "status": {"phase": "received", "started_at": _now(), "updated_at": _now()},
        "payload": dict(payload),
    }
    return state


# -----------------
# Graph node logic
# -----------------
def node_bootstrap_thread(state: DefaultState, logger=None) -> DefaultState:
    """
    Ensure the thread has a system message before the first assistant turn.
    If payload indicates first message, or no system message exists in history,
    inject system prompt and append MOST_IMPORTANT to the user's first message.
    """
    thread_ts = state["io"]["thread_ts"]
    payload = state["payload"]
    is_first = str(payload.get("isFirstMessage", "false")).lower() == "true"

    # Check if a system message already exists in storage
    has_system = False
    try:
        msgs = get_thread_messages(thread_ts, logger=logger) or []
        has_system = any((m.get("role") == "system") for m in msgs)
    except Exception:
        has_system = False  # default to injecting if we can't verify

    if is_first or not has_system:
        # 1) Inject system message
        sys_text = ""
        if create_system_text is not None:
            try:
                sys_text = create_system_text() or ""
            except Exception:
                sys_text = ""
        if sys_text:
            update_message(thread_ts, "system", sys_text, logger=logger)

        # 2) Append MOST_IMPORTANT to the user's first message for parity
        eff = state.get("text", "") or ""
        if MOST_IMPORTANT and MOST_IMPORTANT not in eff:
            eff = eff + MOST_IMPORTANT
        state["effective_user_text"] = eff

        # Mark that we've handled bootstrap
        state["payload"]["isFirstMessage"] = "false"

    state["audit"]["step"] = "bootstrap_thread"
    state["status"]["phase"] = "received"
    state["status"]["updated_at"] = _now()
    return state


def node_save_user_message(state: DefaultState, logger=None) -> DefaultState:
    thread_ts = state["io"]["thread_ts"]
    text = state.get("effective_user_text") or state.get("text", "")
    update_message(thread_ts, "user", text, logger=logger)
    state["audit"]["step"] = "save_user_message"
    state["status"]["phase"] = "received"
    state["status"]["updated_at"] = _now()
    return state


def node_llm_respond(state: DefaultState,
                     max_response_tokens: int,
                     temperature: float,
                     logger=None) -> DefaultState:
    thread_ts = state["io"]["thread_ts"]
    response = get_llm_response(
        thread_ts,
        max_response_tokens,
        temperature,
        logger=logger
    )
    state["response_text"] = response
    state["audit"]["step"] = "llm_respond"
    state["status"]["phase"] = "planned"
    state["status"]["updated_at"] = _now()
    return state


def node_save_assistant_message(state: DefaultState, logger=None) -> DefaultState:
    thread_ts = state["io"]["thread_ts"]
    response = state.get("response_text", "")
    update_message(thread_ts, "assistant", response, logger=logger)
    state["audit"]["step"] = "save_assistant_message"
    state["status"]["phase"] = "planned"
    state["status"]["updated_at"] = _now()
    return state


def node_post_prompt(state: DefaultState, logger=None) -> DefaultState:
    """Post the NAUT prompt asking the user to type RUN."""
    thread_ts = state["io"]["thread_ts"]
    payload = state["payload"]
    response = state.get("response_text", "")

    prompt = (
        "NAUT " + response +
        " type RUN all caps to run the command supplied OR type RUN your-own-command here to run your own"
    )
    send_response(payload, thread_ts, prompt, logger)
    state["result"] = {"handled": True, "path": "POST_PROMPT"}
    state["audit"]["step"] = "post_prompt"
    state["status"]["phase"] = "posting"
    state["status"]["updated_at"] = _now()
    return state


# -----------------
# Graph definition
# -----------------
def _build_graph():
    g = StateGraph(DefaultState)

    def start(state: DefaultState) -> DefaultState:
        state["audit"]["step"] = "start"
        state["status"]["updated_at"] = _now()
        return state

    g.add_node("start", start)
    g.add_node("bootstrap_thread", node_bootstrap_thread)
    g.add_node("save_user_message", node_save_user_message)

    def llm_respond_wrapper(state: DefaultState, config: Dict[str, Any] | None = None) -> DefaultState:
        cfg = config or {}
        return node_llm_respond(
            state,
            max_response_tokens=cfg.get("max_response_tokens", 200),
            temperature=cfg.get("temperature", 0.0),
            logger=cfg.get("logger"),
        )
    g.add_node("llm_respond", llm_respond_wrapper)

    g.add_node("save_assistant_message", node_save_assistant_message)
    g.add_node("post_prompt", node_post_prompt)

    g.set_entry_point("start")
    g.add_edge("start", "bootstrap_thread")
    g.add_edge("bootstrap_thread", "save_user_message")
    g.add_edge("save_user_message", "llm_respond")
    g.add_edge("llm_respond", "save_assistant_message")
    g.add_edge("save_assistant_message", "post_prompt")
    g.add_edge("post_prompt", END)

    return g.compile()


DEFAULT_GRAPH = _build_graph()


def run_default_graph_entry(payload: Dict[str, Any],
                            logger=None,
                            *,
                            max_response_tokens: int = None,
                            temperature: float = None) -> Dict[str, Any]:
    """
    Entry point used by the dispatcher for the default case only.
    NO auto-run: always posts the NAUT prompt after saving the assistant reply.
    """
    if max_response_tokens is None:
        max_response_tokens = int(os.getenv("max_response_tokens", "200"))
    if temperature is None:
        temperature = float(os.getenv("temperature", "0.0"))

    state = _build_state(payload, max_response_tokens, temperature)
    out: DefaultState = DEFAULT_GRAPH.invoke(
        state,
        config={"max_response_tokens": max_response_tokens, "temperature": temperature, "logger": logger},
    )
    return out.get("result", {"handled": True, "path": "POST_PROMPT"})
