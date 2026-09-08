import os
from typing import Literal
from langgraph.graph import StateGraph, START, END
from agent.models import AgentState
from agent.nodes import (
    triage_node,
    guardrail_audit_node,
    emergency_bypass_node,
    db_lookup_node,
    response_node
)

def route_after_guardrail(state: AgentState) -> Literal["emergency_bypass_node", "db_lookup_node", "response_node"]:
    guardrail = state.get("guardrail_result")
    if not guardrail:
        return "response_node"
    if guardrail.is_emergency:
        return "emergency_bypass_node"
    if not guardrail.is_safe:
        return "response_node"
    return "db_lookup_node"

builder = StateGraph(AgentState)
builder.add_node("triage_node", triage_node)
builder.add_node("guardrail_audit_node", guardrail_audit_node)
builder.add_node("emergency_bypass_node", emergency_bypass_node)
builder.add_node("db_lookup_node", db_lookup_node)
builder.add_node("response_node", response_node)

builder.add_edge(START, "triage_node")
builder.add_edge("triage_node", "guardrail_audit_node")
builder.add_conditional_edges(
    "guardrail_audit_node",
    route_after_guardrail,
    {
        "emergency_bypass_node": "emergency_bypass_node",
        "db_lookup_node": "db_lookup_node",
        "response_node": "response_node"
    }
)
builder.add_edge("emergency_bypass_node", END)
builder.add_edge("db_lookup_node", "response_node")
builder.add_edge("response_node", END)

# In FastAPI, we compile this with a checkpointer dynamically or globally if the connection is ready
# We will provide a function to get the compiled graph
def get_compiled_graph(checkpointer=None):
    return builder.compile(checkpointer=checkpointer)

