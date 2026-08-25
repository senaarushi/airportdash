#region Imports
from __future__ import annotations
import operator
from typing import Annotated, Callable, Awaitable

from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, START, END
# NOTE: exact LangGraph API surface (StateGraph/START/END/add_node/add_edge/
# compile signatures) should be double-checked against your installed
# langgraph==1.2.9 docs, this follows the pattern that's been stable across
# most recent versions but pinned-version specifics can drift.

from app.core.event_bus import Blackboard
from app.core.models import AirportStatus
from app.core.proposals import AgentProposal

from app.agents.gate_agent import gate_agent_node
from app.agents.crew_agent import crew_agent_node
from app.agents.ats_agent import ats_agent_node
from app.agents.disruption_agent import disruption_agent_node
from app.agents.orchestrator import orchestrator_node
#endregion Imports


#region State
class GraphState(BaseModel):
    """
    The state object passed between every node in a single tick's graph
    invocation. Deliberately holds TWO different views of the world,
    matching the read-isolation decision:

    - snapshot: AirportStatus — a detached, read-only copy of board taken
      once at the start of the tick. This is ALL that gate_agent,
      crew_agent, ats_agent, and disruption_agent ever see. Because it's
      typed as AirportStatus (not Blackboard), those 4 nodes have no
      type-level access to Blackboard.lock or Blackboard.log_decision()
      at all, the restriction is enforced by the type system, not just a
      comment telling agents not to write here.

    - board: Blackboard — the LIVE, mutable shared instance. Only
      orchestrator_node touches this. This is what makes single-writer
      (Decision #19) real rather than aspirational: nothing else in the
      graph even has a reference capable of mutating shared state.

    - proposals: accumulates across the 4 concurrent agent nodes via the
      operator.add reducer, each node returns {"proposals": [...]} with
      just its own new proposals, LangGraph merges them into one combined
      list for orchestrator_node to process. Starts empty each tick since
      a fresh GraphState is constructed per tick (see run_tick_via_graph
      below), no manual reset needed between ticks.
    """

    snapshot: AirportStatus
    board: Blackboard
    proposals: Annotated[list[AgentProposal], operator.add] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}
#endregion State


#region Graph construction
def build_graph():
    """
    Wires the 5 agents into a fan-out/fan-in graph:

        START -> gate_agent      \
        START -> crew_agent       \
        START -> ats_agent         >---> orchestrator -> END
        START -> disruption_agent /

    Gate, Crew, ATS, and Disruption run concurrently (LangGraph handles
    this automatically for nodes that share no data dependency, they all
    branch from START and converge on orchestrator), since none of them
    depend on each other's output, only on the shared read-only snapshot.
    Orchestrator only runs once ALL FOUR have completed and their proposals
    have been merged, this is what makes it correct for Orchestrator to
    assume it has the full picture before resolving conflicts.

    This is a graph-per-tick design (Decision #22): one call to
    compiled_graph.ainvoke(...) represents exactly one simulation tick's
    worth of agent reasoning. Temporal looping across many ticks stays
    owned by Simulator, this graph has no cycles.
    """
    graph = StateGraph(GraphState)

    graph.add_node("gate_agent", gate_agent_node)
    graph.add_node("crew_agent", crew_agent_node)
    graph.add_node("ats_agent", ats_agent_node)
    graph.add_node("disruption_agent", disruption_agent_node)
    graph.add_node("orchestrator", orchestrator_node)

    # Fan-out: all 4 independent agents branch directly from START
    graph.add_edge(START, "gate_agent")
    graph.add_edge(START, "crew_agent")
    graph.add_edge(START, "ats_agent")
    graph.add_edge(START, "disruption_agent")

    # Fan-in: all 4 converge on orchestrator
    graph.add_edge("gate_agent", "orchestrator")
    graph.add_edge("crew_agent", "orchestrator")
    graph.add_edge("ats_agent", "orchestrator")
    graph.add_edge("disruption_agent", "orchestrator")

    graph.add_edge("orchestrator", END)

    return graph.compile()
#endregion Graph construction


#region Simulator integration
def make_tick_handler(compiled_graph) -> Callable[[Blackboard], Awaitable[None]]:
    """
    Adapts the compiled graph into exactly the shape Simulator's on_tick
    expects: Callable[[Blackboard], Awaitable[None]]. This is the one
    place the two independently-built pieces (Simulator, agents/graph.py)
    connect, everything upstream of this function was written and tested
    with zero knowledge of the other's existence, on purpose.

    Usage (in main.py, once written):
        compiled = build_graph()
        sim = Simulator(board, bus, on_tick=make_tick_handler(compiled))
    """

    async def handler(board: Blackboard) -> None:
        snapshot = AirportStatus.model_validate(board.model_dump())
        initial_state = GraphState(snapshot=snapshot, board=board, proposals=[])
        await compiled_graph.ainvoke(initial_state)
        # No return value needed, orchestrator_node has already applied
        # everything it decided directly onto `board` (the live reference),
        # which is the same object Simulator holds, so Simulator sees the
        # updated state automatically on its next tick.

    return handler
#endregion Simulator integration