
# graphs/default_graphs.py
"""DefaultGraphs for Argonaut (extended default case) with structured logging and command review."""
from __future__ import annotations
from typing import Any, Dict, TypedDict, Optional
import os, time, uuid, re

from langgraph.graph import StateGraph, END

from send_response import send_response
from generic_storage import update_message, get_thread_messages
from call_llm import get_llm_response
from execute_run_command import execute_run_command

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
    refined_response_text: str
    detected_command: str
    help_command: str
    help_result: Dict[str, Any]
    audit: AuditState
    status: StatusState
    payload: Dict[str, Any]
    result: Dict[str, Any]
    _logger: Any

GRAPH_NAME = "DefaultGraph_NoAutoRun_WithCommandReview"

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

SEPARATORS_PATTERN = re.compile(r"\s*(\|\||\||&&|&|;|:)\s*")

def _extract_argocd_command(text: str) -> str:
    if not text:
        return ""
    blocks = re.findall(r"```(?:bash|shell)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE)
    candidates = []
    for b in blocks:
        for line in b.splitlines():
            s = line.strip()
            if s.startswith("argocd "):
                candidates.append(s)
    if not candidates:
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("argocd "):
                candidates.append(s)
    if not candidates:
        return ""
    cmd = candidates[0]
    parts = SEPARATORS_PATTERN.split(cmd, maxsplit=1)
    if parts:
        cmd = parts[0].strip()
    return cmd.strip("` '\"")

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

def node_detect_command(state: DefaultState) -> DefaultState:
    logger = state.get("_logger")
    reply = state.get("response_text","") or ""
    cmd = _extract_argocd_command(reply)
    state["detected_command"] = cmd
    _log(logger,"info",node="detect_command",step="done",has_command=bool(cmd),command=cmd[:160])
    return state

def node_review_command_llm(state: DefaultState, max_response_tokens:int, temperature:float) -> DefaultState:
    logger = state.get("_logger")
    thread_ts = state["io"]["thread_ts"]
    cmd = state.get("detected_command") or ""
    if not cmd:
        _log(logger,"debug",node="review_command_llm",step="skip_no_command")
        return state
    prompt = (
        "Extract only the pure argocd command from the prior assistant reply, remove any pipes/semicolons, "
        "and output ONE line with the same command appended with --help. Return only the command, nothing else."
    )
    update_message(thread_ts, "user", prompt, logger=logger)
    _log(logger,"info",node="review_command_llm",step="ask_extract_help",original=cmd)
    help_line = get_llm_response(thread_ts, max_response_tokens, temperature, logger=logger) or ""
    help_cmd = _extract_argocd_command(help_line)
    if help_cmd and not help_cmd.endswith(" --help"):
        help_cmd = help_cmd + " --help"
    state["help_command"] = help_cmd
    _log(logger,"info",node="review_command_llm",step="got_help_cmd",help_command=help_cmd)
    return state

def node_execute_help_command(state: DefaultState) -> DefaultState:
    logger = state.get("_logger")
    help_cmd = (state.get("help_command") or "").strip()
    thread_ts = state["io"]["thread_ts"]
    if not help_cmd:
        _log(logger,"debug",node="execute_help_command",step="skip_no_help_cmd")
        return state
    _log(logger,"info",node="execute_help_command",step="run",cmd=help_cmd)
    result = execute_run_command(help_cmd, logger=logger)
    state["help_result"] = result or {}
    tool_msg = (
        f"TOOL Command: {help_cmd}\nCommand Output:\n{(result or {}).get('stdout','')}\n"
        f"Command Error:\n{(result or {}).get('stderr','')}\nReturn Code:\n{(result or {}).get('returncode','')}"
    )
    update_message(thread_ts, "user", tool_msg, logger=logger)
    _log(logger,"info",node="execute_help_command",step="done",
         rc=(result or {}).get("returncode"), out_len=len((result or {}).get("stdout","")))
    return state

def node_refine_command_llm(state: DefaultState, max_response_tokens:int, temperature:float) -> DefaultState:
    logger = state.get("_logger")
    thread_ts = state["io"]["thread_ts"]
    if not state.get("detected_command"):
        _log(logger,"debug",node="refine_command_llm",step="skip_no_command")
        return state
    refine_prompt = (
        "Given the previous assistant suggestion and the output of the argocd --help command we just executed, "
        "revise the recommendation if needed. If no change is needed, restate succinctly. "
        "Keep it brief and include at most ONE final recommended command in a fenced code block."
    )
    update_message(thread_ts, "user", refine_prompt, logger=logger)
    _log(logger,"info",node="refine_command_llm",step="ask_refine")
    refined = get_llm_response(thread_ts, max_response_tokens, temperature, logger=logger) or ""
    state["refined_response_text"] = refined
    update_message(thread_ts, "assistant", refined, logger=logger)
    _log(logger,"info",node="refine_command_llm",step="done",size=len(refined))
    return state

def node_post_prompt(state: DefaultState) -> DefaultState:
    logger = state.get("_logger")
    thread_ts = state["io"]["thread_ts"]
    payload = state["payload"]
    final_text = state.get("refined_response_text") or state.get("response_text","")
    prompt = (
        "NAUT " + final_text +
        " type RUN all caps to run the command supplied OR type RUN your-own-command here to run your own"
    )
    send_response(payload, thread_ts, prompt, logger)
    _log(logger,"info",node="post_prompt",step="posted",size=len(prompt))
    state["result"] = {"handled": True, "path": "POST_PROMPT"}
    state["audit"]["step"] = "post_prompt"
    state["status"]["phase"] = "posting"
    state["status"]["updated_at"] = _now()
    return state

def _build_graph():
    g = StateGraph(DefaultState)
    def start(state: DefaultState) -> DefaultState:
        logger = state.get("_logger")
        state["audit"]["step"]="start"
        state["status"]["updated_at"]=_now()
        _log(logger,"debug",node="start",step="entered",
             run_id=state["audit"]["run_id"],thread_ts=state["io"]["thread_ts"])
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
    g.add_node("detect_command", node_detect_command)

    def review_wrap(state: DefaultState, config: Dict[str, Any] | None = None) -> DefaultState:
        cfg = config or {}
        return node_review_command_llm(state,
                                       max_response_tokens=cfg.get("max_response_tokens",200),
                                       temperature=cfg.get("temperature",0.0))
    g.add_node("review_command_llm", review_wrap)

    g.add_node("execute_help_command", node_execute_help_command)

    def refine_wrap(state: DefaultState, config: Dict[str, Any] | None = None) -> DefaultState:
        cfg = config or {}
        return node_refine_command_llm(state,
                                       max_response_tokens=cfg.get("max_response_tokens",200),
                                       temperature=cfg.get("temperature",0.0))
    g.add_node("refine_command_llm", refine_wrap)

    g.add_node("post_prompt", node_post_prompt)

    g.set_entry_point("start")
    g.add_edge("start","bootstrap_thread")
    g.add_edge("bootstrap_thread","save_user_message")
    g.add_edge("save_user_message","llm_respond")
    g.add_edge("llm_respond","save_assistant_message")
    g.add_edge("save_assistant_message","detect_command")
    def route_after_detect(state: DefaultState) -> str:
        return "review_command_llm" if state.get("detected_command") else "post_prompt"
    g.add_conditional_edges("detect_command", route_after_detect,
                            {"review_command_llm":"review_command_llm","post_prompt":"post_prompt"})
    g.add_edge("review_command_llm","execute_help_command")
    g.add_edge("execute_help_command","refine_command_llm")
    g.add_edge("refine_command_llm","post_prompt")
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
