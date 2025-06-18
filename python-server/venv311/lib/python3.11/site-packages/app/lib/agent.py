from typing import Any, Mapping, Optional

from langchain_core.runnables import (
    RunnableBinding,
)

from app.chain import get_chain
from app.hack import USER_SPECIFIED_CHAIN


class ConfigurableAgent(RunnableBinding):
    interrupt_before_action: bool = True

    def __init__(
        self,
        *,
        interrupt_before_action: Optional[bool] = True,
        kwargs: Optional[Mapping[str, Any]] = None,
        config: Optional[Mapping[str, Any]] = None,
        **others: Any,
    ) -> None:
        others.pop("bound", None)
        _agent = USER_SPECIFIED_CHAIN.chain or get_chain(
            interrupt_before_action=False,
        )
        agent_executor = _agent.with_config({"recursion_limit": 50})
        super().__init__(
            bound=agent_executor,
            kwargs=kwargs or {},
            config=config or {},
        )


agent = ConfigurableAgent(
    assistant_id=None,
    thread_id=None,
)

if __name__ == "__main__":
    import asyncio

    from langchain.schema.messages import HumanMessage

    async def run():
        async for m in agent.astream_events(
            HumanMessage(content="whats your name"),
            config={"configurable": {"user_id": "2", "thread_id": "test1"}},
            version="v1",
        ):
            print(m)

    asyncio.run(run())
