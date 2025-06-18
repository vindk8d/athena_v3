from typing import Optional

from langgraph.graph.graph import CompiledGraph


class Hack:
    chain: Optional[CompiledGraph] = None


USER_SPECIFIED_CHAIN = Hack()
