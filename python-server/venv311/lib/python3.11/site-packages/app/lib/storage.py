from datetime import datetime, timezone
from typing import Any, List, Optional, Sequence

from langchain_core.messages import AnyMessage

from app.chain import get_chain
from app.lib.lifespan import get_pg_pool
from app.lib.schema import Assistant, Thread
from app.lib.stream import map_chunk_to_msg


async def list_assistants(user_id: str) -> List[Assistant]:
    """List all assistants for the current user."""
    async with get_pg_pool().acquire() as conn:
        return await conn.fetch("SELECT * FROM assistant WHERE user_id = $1", user_id)


async def get_assistant(user_id: str, assistant_id: str) -> Optional[Assistant]:
    """Get an assistant by ID."""
    async with get_pg_pool().acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM assistant WHERE assistant_id = $1 AND (user_id = $2 OR public = true)",
            assistant_id,
            user_id,
        )


async def list_public_assistants(assistant_ids: Sequence[str]) -> List[Assistant]:
    """List all the public assistants."""
    async with get_pg_pool().acquire() as conn:
        return await conn.fetch(
            (
                "SELECT * FROM assistant "
                "WHERE assistant_id = ANY($1::uuid[]) "
                "AND public = true;"
            ),
            assistant_ids,
        )


async def put_assistant(
    user_id: str, assistant_id: str, *, name: str, config: dict, public: bool = False
) -> Assistant:
    """Modify an assistant.

    Args:
        user_id: The user ID.
        assistant_id: The assistant ID.
        name: The assistant name.
        config: The assistant config.
        public: Whether the assistant is public.

    Returns:
        return the assistant model if no exception is raised.
    """
    updated_at = datetime.now(timezone.utc)
    async with get_pg_pool().acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                (
                    "INSERT INTO assistant (assistant_id, user_id, name, config, updated_at, public) VALUES ($1, $2, $3, $4, $5, $6) "
                    "ON CONFLICT (assistant_id) DO UPDATE SET "
                    "user_id = EXCLUDED.user_id, "
                    "name = EXCLUDED.name, "
                    "config = EXCLUDED.config, "
                    "updated_at = EXCLUDED.updated_at, "
                    "public = EXCLUDED.public;"
                ),
                assistant_id,
                user_id,
                name,
                config,
                updated_at,
                public,
            )
    return {
        "assistant_id": assistant_id,
        "user_id": user_id,
        "name": name,
        "config": config,
        "updated_at": updated_at,
        "public": public,
    }


async def list_threads(user_id: str) -> List[Thread]:
    """List all threads for the current user."""
    async with get_pg_pool().acquire() as conn:
        return await conn.fetch("SELECT * FROM thread WHERE user_id = $1", user_id)


async def get_thread(user_id: str, thread_id: str) -> Optional[Thread]:
    """Get a thread by ID."""
    async with get_pg_pool().acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM thread WHERE thread_id = $1 AND user_id = $2",
            thread_id,
            user_id,
        )


async def get_thread_state(user_id: str, thread_id: str):
    """Get all messages for a thread."""
    app = get_chain(interrupt_before_action=False)
    state = await app.aget_state({"configurable": {"thread_id": thread_id}})
    return {
        "values": [map_chunk_to_msg(c) for c in state.values]
        if isinstance(state.values, list)
        else state.values,
        "resumeable": bool(state.next),
    }


async def update_thread_state(
    user_id: str, thread_id: str, messages: Sequence[AnyMessage] | dict[str, Any]
):
    """Add messages to a thread."""
    app = get_chain(interrupt_before_action=False)
    return await app.aupdate_state({"configurable": {"thread_id": thread_id}}, messages)


async def get_thread_history(user_id: str, thread_id: str):
    """Get the history of a thread."""
    app = get_chain(interrupt_before_action=False)
    return [
        {
            "values": [map_chunk_to_msg(c) for c in c.values]
            if isinstance(c.values, list)
            else c.values,
            "resumeable": bool(c.next),
            "config": c.config,
            "parent": c.parent_config,
        }
        async for c in app.aget_state_history(
            {"configurable": {"thread_id": thread_id}}
        )
    ]


async def put_thread(
    user_id: str, thread_id: str, *, assistant_id: str, name: str
) -> Thread:
    """Modify a thread."""
    updated_at = datetime.now(timezone.utc)
    async with get_pg_pool().acquire() as conn:
        await conn.execute(
            (
                "INSERT INTO thread (thread_id, user_id, assistant_id, name, updated_at) VALUES ($1, $2, $3, $4, $5) "
                "ON CONFLICT (thread_id) DO UPDATE SET "
                "user_id = EXCLUDED.user_id,"
                "assistant_id = EXCLUDED.assistant_id, "
                "name = EXCLUDED.name, "
                "updated_at = EXCLUDED.updated_at;"
            ),
            thread_id,
            user_id,
            assistant_id,
            name,
            updated_at,
        )
        return {
            "thread_id": thread_id,
            "user_id": user_id,
            "assistant_id": assistant_id,
            "name": name,
            "updated_at": updated_at,
        }
