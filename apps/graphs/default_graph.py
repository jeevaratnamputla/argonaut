
# graphs/default_graphs.py
"""DefaultGraphs for Argonaut (default `case _`, NO auto-run) with structured logging."""
from __future__ import annotations
from typing import Any, Dict, TypedDict, Optional
import os, time, uuid

from langgraph.graph import StateGraph, END

from send_response import send_response
from generic_storage import update_message, get_thread_messages
from call_llm import get_llm_response

try:
    from create_system_text import create_system_text
except Exception:
    create_system_text = None

try:
    from new_webhook_handler import MOST_IMPORTANT
except Exception:
    MOST_IMPORTANT = ""

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
    effective_user_text: str
    response_text: str
    audit: AuditState
    status: StatusState
    payload: Dict[str, Any]
    result: Dict[str, Any]
    _logger: Any

GRAPH_NAME = "DefaultGraph_NoAutoRun"

def _now() -> float: return time.time()

def _log(logger, level: str, **fields):
    if not logger: return
    prefix = GRAPH_NAME
    try:
        line = " | ".join(f"{k}={v}" for k, v in fields.items())
    except Exception:
        line = str(fields)
    msg = f"{prefix} | {line}"
    try:
        getattr(logger, {"error":"error","warning":"warning","debug":"debug"}.get(level,"info"))(msg)
    except Exception:
        pass

def node_bootstrap_thread(state: DefaultState) -> DefaultState:
    logger = state.get("_logger")
    thread_ts = state["io"]["thread_ts"]
    payload = state["payload"]
    is_first = str(payload.get("isFirstMessage","false")).lower() == "true"
    has_system = False
    try:
        msgs = get_thread_messages(thread_ts, logger=logger) or []
        has_system = any(m.get("role")=="system" for m in msgs)
        _log(logger,"debug",node="bootstrap_thread",step="loaded_history",
             run_id=state["audit"]["run_id"],thread_ts=thread_ts,messages=len(msgs),has_system=has_system)
    except Exception as e:
        _log(logger,"warning",node="bootstrap_thread",step="history_failed",
             run_id=state["audit"]["run_id"],thread_ts=thread_ts,error=repr(e))
    if is_first or not has_system:
        sys_text = ""
        if create_system_text is not None:
            try:
                sys_text = create_system_text() or ""
                _log(logger,"debug",node="bootstrap_thread",step="created_system_text",
                     run_id=state["audit"]["run_id"],thread_ts=thread_ts,size=len(sys_text))
            except Exception as e:
                _log(logger,"warning",node="bootstrap_thread",step="create_system_text_failed",
                     run_id=state["audit"]["run_id"],thread_ts=thread_ts,error=repr(e))
        if sys_text:
            update_message(thread_ts,"system",sys_text,logger=logger)
            _log(logger,"info",node="bootstrap_thread",step="system_saved",
                 run_id=state["audit"]["run_id"],thread_ts=thread_ts)
        eff = state.get("text","") or ""
        if MOST_IMPORTANT and MOST_IMPORTANT not in eff:
            eff = eff + MOST_IMPORTANT
        state["effective_user_text"] = eff
        _log(logger,"info",node="bootstrap_thread",step="most_important_appended",
             run_id=state["audit"]["run_id"],thread_ts=thread_ts,appended=bool(MOST_IMPORTANT))
        state["payload"]["isFirstMessage"] = "false"
    state["audit"]["step"]="bootstrap_thread"
    state["status"]["phase"]="received"
    state["status"]["updated_at"]=_now()
    _log(logger,"info",node="bootstrap_thread",step="done",
         run_id=state["audit"]["run_id"],thread_ts=thread_ts,is_first=is_first,has_system=has_system)
    return state

def node_save_user_message(state: DefaultState) -> DefaultState:
    logger = state.get("_logger")
    thread_ts = state["io"]["thread_ts"]
    text = state.get("effective_user_text") or state.get("text","")
    update_message(thread_ts,"user",text,logger=logger)
    _log(logger,"info",node="save_user_message",step="saved",
         run_id=state["audit"]["run_id"],thread_ts=thread_ts,size=len(text))
    state["audit"]["step"]="save_user_message"
    state["status"]["phase"]="received"
    state["status"]["updated_at"]=_now()
    return state

def node_llm_respond(state: DefaultState, max_response_tokens:int, temperature:float) -> DefaultState:
    logger = state.get("_logger")
    thread_ts = state["io"]["thread_ts"]
    _log(logger,"info",node="llm_respond",step="calling_llm",
         run_id=state["audit"]["run_id"],thread_ts=thread_ts,max_tokens=max_response_tokens,temperature=temperature)
    try:
        response = get_llm_response(thread_ts,max_response_tokens,temperature,logger=logger)
    except Exception as e:
        _log(logger,"error",node="llm_respond",step="llm_failed",
             run_id=state["audit"]["run_id"],thread_ts=thread_ts,error=repr(e))
        raise
    _log(logger,"info",node="llm_respond",step="llm_ok",
         run_id=state["audit"]["run_id"],thread_ts=thread_ts,size=len(response or ""))
    state["response_text"]=response
    state["audit"]["step"]="llm_respond"
    state["status"]["phase"]="planned"
    state["status"]["updated_at"]=_now()
    return state

def node_save_assistant_message(state: DefaultState) -> DefaultState:
    logger = state.get("_logger")
    thread_ts = state["io"]["thread_ts"]
    response = state.get("response_text","")
    update_message(thread_ts,"assistant",response,logger=logger)
    _log(logger,"info",node="save_assistant_message",step="saved",
         run_id=state["audit"]["run_id"],thread_ts=thread_ts,size=len(response))
    state["audit"]["step"]="save_assistant_message"
    state["status"]["phase"]="planned"
    state["status"]["updated_at"]=_now()
    return state

def node_post_prompt(state: DefaultState) -> DefaultState:
    logger = state.get("_logger")
    thread_ts = state["io"]["thread_ts"]
    payload = state["payload"]
    response = state.get("response_text","")
    prompt = ("NAUT " + response +
              " type RUN all caps to run the command supplied OR type RUN your-own-command here to run your own")
    send_response(payload,thread_ts,prompt,logger)
    _log(logger,"info",node="post_prompt",step="posted",
         run_id=state["audit"]["run_id"],thread_ts=thread_ts,size=len(prompt))
    state["result"]={"handled":True,"path":"POST_PROMPT"}
    state["audit"]["step"]="post_prompt"
    state["status"]["phase"]="posting"
    state["status"]["updated_at"]=_now()
    return state

def _build_graph():
    g = StateGraph(DefaultState)
    def start(state: DefaultState) -> DefaultState:
        logger = state.get("_logger")
        state["audit"]["step"]="start"
        state["status"]["updated_at"]=_now()
        _log(logger,"debug",node="start",step="entered",run_id=state["audit"]["run_id"],
             thread_ts=state["io"]["thread_ts"])
        return state
    g.add_node("start", start)
    g.add_node("bootstrap_thread", node_bootstrap_thread)
    g.add_node("save_user_message", node_save_user_message)
    def llm_wrap(state: DefaultState, config: Dict[str, Any] | None = None) -> DefaultState:
        cfg = config or {}
        return node_llm_respond(state,
                                max_response_tokens=cfg.get("max_response_tokens",200),
                                temperature=cfg.get("temperature",0.0))
    g.add_node("llm_respond", llm_wrap)
    g.add_node("save_assistant_message", node_save_assistant_message)
    g.add_node("post_prompt", node_post_prompt)
    g.set_entry_point("start")
    g.add_edge("start","bootstrap_thread")
    g.add_edge("bootstrap_thread","save_user_message")
    g.add_edge("save_user_message","llm_respond")
    g.add_edge("llm_respond","save_assistant_message")
    g.add_edge("save_assistant_message","post_prompt")
    g.add_edge("post_prompt", END)
    return g.compile()

DEFAULT_GRAPH = _build_graph()

def run_default_graph_entry(payload: Dict[str, Any], logger=None, *, max_response_tokens:int=None, temperature:float=None) -> Dict[str, Any]:
    if max_response_tokens is None:
        max_response_tokens = int(os.getenv("max_response_tokens","200"))
    if temperature is None:
        temperature = float(os.getenv("temperature","0.0"))
    try:
        _log(logger,"info",node="entry",step="invoke",
             thread_ts=(payload or {}).get("thread_ts"),
             max_tokens=max_response_tokens,temperature=temperature)
    except Exception:
        pass
    # Build state (store logger for all nodes)
    state: DefaultState = {
        "io": {"thread_ts": payload.get("thread_ts") or f"auto-{uuid.uuid4().hex[:12]}",
               "channel": payload.get("channel"),
               "user": payload.get("user")},
        "text": (payload.get("text") or "").strip(),
        "effective_user_text": (payload.get("text") or "").strip(),
        "audit": {"graph_name":GRAPH_NAME, "run_id":uuid.uuid4().hex, "step":"build_state"},
        "status": {"phase":"received", "started_at":time.time(), "updated_at":time.time()},
        "payload": dict(payload),
        "_logger": logger,
    }
    _log(logger,"debug",node="entry",step="state_built",
         run_id=state["audit"]["run_id"],thread_ts=state["io"]["thread_ts"])
    out: DefaultState = DEFAULT_GRAPH.invoke(state, config={
        "max_response_tokens": max_response_tokens, "temperature": temperature
    })
    try:
        _log(logger,"info",node="exit",step="done",
             run_id=out.get("audit",{}).get("run_id","?"),
             thread_ts=out.get("io",{}).get("thread_ts","?"),
             path=out.get("result",{}).get("path"))
    except Exception:
        pass
    return out.get("result", {"handled": True, "path": "POST_PROMPT"})
