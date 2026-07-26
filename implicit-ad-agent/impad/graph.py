"""P2.5 graph: normalize → plan → tool groups → evidence-only Judge."""
from __future__ import annotations
from langgraph.graph import StateGraph, START, END
from .state import AdCheckState
from .agents import (supervisor, route_next, nlp_agent,
                     vision_agent, behavior_agent, judge)

ROUTES = {"nlp": "nlp", "vision": "vision", "behavior": "behavior", "judge": "judge"}


def build_graph():
    g = StateGraph(AdCheckState)
    g.add_node("supervisor", supervisor)
    g.add_node("nlp", nlp_agent)
    g.add_node("vision", vision_agent)
    g.add_node("behavior", behavior_agent)
    g.add_node("judge", judge)

    g.add_edge(START, "supervisor")
    for src in ("supervisor", "nlp", "vision", "behavior"):
        g.add_conditional_edges(src, route_next, ROUTES)
    g.add_edge("judge", END)
    return g.compile()


graph = build_graph()


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sample = {"post": {
        "text": "这支面霜我亲测三个月，无限回购，链接在评论区，姐妹们码住！",
        "blogger": "小美的日常", "comments": ["求链接", "已买"],
        "history": ["今天去图书馆看了一下午书", "分享几段最近读到的句子"]}}
    print(graph.invoke(sample)["report"])
