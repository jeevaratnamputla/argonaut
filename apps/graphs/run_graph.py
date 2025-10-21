from typing import Any, Dict
# minimal import to avoid side effects
from langgraph.graph import StateGraph, END

def build_run_graph():
    # placeholder state and single pass-through node
    class S(dict): pass
    g = StateGraph(S)

    def start(state: S) -> S:
        # do nothing for now; you’ll add nodes later
        state["__passthrough__"] = True
        return state
    g.add_node("start", start)
    g.set_entry_point("start")
    g.add_edge("start", END)
    return g.compile()

RUN_GRAPH = build_run_graph()

def run_graph_entry(payload: Dict[str, Any], logger):
    # bridge payload to graph state
    state = {"payload": payload}
    out = RUN_GRAPH.invoke(state)
    logger.info("RunGraph completed passthrough=%s", out.get("__passthrough__"))
    return None  # returning None ensures fallback to legacy for Phase 1
