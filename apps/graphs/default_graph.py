"""
DefaultGraph for Argonaut (handles the default `case _` branch only).
[...truncated header comment for brevity in this cell...]
"""
from __future__ import annotations
from typing import Any, Dict, TypedDict, Optional
import os
import time
import uuid

# LangGraph imports
try:
    from langgraph.graph import StateGraph, END
except Exception as e:  # pragma: no cover
    raise RuntimeError(
        "LangGraph is not available. Install `langgraph>=0.2.0` to use DefaultGraph."
    ) from e

# ---- Import your existing helpers (module names should match your repo) ----
from send_response import send_response
from generic_storage import update_message
from call_llm import get_llm_response
# The default graph optionally re-enters legacy RUN path:
# Adjust this import to your project structure if needed.
from __main__ import handle_event_text


class IOState(TypedDict, total=False):
    thread_ts: str
    channel: Optional[str]
    user: Optional[str]


class FlagsState(TypedDict, total=False):
    auto_run: bool


class OutputsState(TypedDict, total=False):
    stdout: Optional[str]
    stderr: Optional[str]
    returncode: Optional[int]
    truncated: Optional[bool]


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
    response_text: str
    flags: FlagsState
    outputs: OutputsState
    audit: AuditState
    status: StatusState
    payload: Dict[str, Any]
    result: Dict[str, Any]  # return value sentinel


GRAPH_NAME = "DefaultGraph"


def _now() -> float:
    return time.time()


def _build_state(payload: Dict[str, Any],
                 max_response_tokens: int,
                 temperature: float,
                 auto_run: bool) -> DefaultState:
    thread_ts = payload.get("thread_ts") or f"auto-{uuid.uuid4().hex[:12]}"
    channel = payload.get("channel")
    user = payload.get("user")
    text = (payload.get("text") or "").strip()

    state: DefaultState = {
        "io": {"thread_ts": thread_ts, "channel": channel, "user": user},
        "text": text,
        "flags": {"auto_run": bool(auto_run)},
        "outputs": {},
        "audit": {"graph_name": GRAPH_NAME, "run_id": uuid.uuid4().hex, "step": "build_state"},
        "status": {"phase": "received", "started_at": _now(), "updated_at": _now()},
        "payload": dict(payload),
    }
    return state


def node_save_user_message(state: DefaultState) -> DefaultState:
    thread_ts = state["io"]["thread_ts"]
    text = state.get("text", "")
    update_message(thread_ts, "user", text, logger=None)
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


def node_save_assistant_message(state: DefaultState) -> DefaultState:
    thread_ts = state["io"]["thread_ts"]
    response = state.get("response_text", "")
    update_message(thread_ts, "assistant", response, logger=None)
    state["audit"]["step"] = "save_assistant_message"
    state["status"]["phase"] = "planned"
    state["status"]["updated_at"] = _now()
    return state


def route_after_assistant(state: DefaultState) -> str:
    auto_run = state.get("flags", {}).get("auto_run", False)
    return "auto_run" if auto_run else "post_prompt"


def node_maybe_auto_run(state: DefaultState, logger=None) -> DefaultState:
    payload = dict(state["payload"])
    payload["text"] = "RUN"
    result = handle_event_text(payload, logger)
    state["result"] = {"handled": True, "path": "AUTO_RUN", "legacy_result": result}
    state["audit"]["step"] = "maybe_auto_run"
    state["status"]["phase"] = "executing"
    state["status"]["updated_at"] = _now()
    return state


def node_post_prompt(state: DefaultState, logger=None) -> DefaultState:
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


def _build_graph():
    g = StateGraph(DefaultState)

    def start(state: DefaultState) -> DefaultState:
        state["audit"]["step"] = "start"
        state["status"]["updated_at"] = _now()
        return state

    g.add_node("start", start)
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
    g.add_node("maybe_auto_run", node_maybe_auto_run)
    g.add_node("post_prompt", node_post_prompt)

    g.set_entry_point("start")
    g.add_edge("start", "save_user_message")
    g.add_edge("save_user_message", "llm_respond")
    g.add_edge("llm_respond", "save_assistant_message")

    g.add_conditional_edges(
        "save_assistant_message",
        route_after_assistant,
        {
            "auto_run": "maybe_auto_run",
            "post_prompt": "post_prompt",
        },
    )

    g.add_edge("maybe_auto_run", END)
    g.add_edge("post_prompt", END)

    return g.compile()


DEFAULT_GRAPH = _build_graph()


def run_default_graph_entry(payload: Dict[str, Any],
                            logger=None,
                            *,
                            max_response_tokens: int = None,
                            temperature: float = None,
                            auto_run: Optional[bool] = None) -> Dict[str, Any]:
    if max_response_tokens is None:
        max_response_tokens = int(os.getenv("max_response_tokens", "200"))
    if temperature is None:
        temperature = float(os.getenv("temperature", "0.0"))
    if auto_run is None:
        auto_run = os.getenv("AUTO_RUN", "false").lower() == "true"

    # Initial state creation (no side-effects)
    state = _build_state(payload, max_response_tokens, temperature, auto_run)

    out: DefaultState = DEFAULT_GRAPH.invoke(
        state,
        config={
            "max_response_tokens": max_response_tokens,
            "temperature": temperature,
            "logger": logger,
        },
    )
    return out.get("result", {"handled": True, "path": "UNKNOWN"})