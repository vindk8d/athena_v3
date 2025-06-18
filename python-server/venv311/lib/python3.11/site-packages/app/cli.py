import asyncio
import importlib.util
import os
import pathlib
import sys
from typing import Optional

import asyncpg
import click
import uvicorn
from langgraph.pregel import Pregel
from langgraph.checkpoint import CheckpointAt

from app.hack import USER_SPECIFIED_CHAIN
from app.lib.checkpoint import PostgresCheckpoint
from app.lib.lifespan import connect


@click.group()
def cli():
    pass


@cli.command()
@click.argument(
    "path",
    required=False,
    type=click.Path(exists=True, file_okay=True, dir_okay=False, resolve_path=True),
)
@click.option("--debug", is_flag=True, help="Print debug information", default=False)
def start(path: Optional[str], debug: bool):
    os.environ.update(
        {
            "POSTGRES_PORT": "5433",
            "POSTGRES_DB": "postgres",
            "POSTGRES_USER": "postgres",
            "POSTGRES_PASSWORD": "postgres",
            "POSTGRES_HOST": "localhost",
        }
    )

    if path is None:
        print("Starting LangGraph Studio with demo graph")
    else:
        print(f"Starting LangGraph Studio with graph at path: {path}")

        try:
            module_name = "graph_module"
            spec = importlib.util.spec_from_file_location(module_name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
        except ImportError as e:
            print(f"Could not import python module at path: {path} debug: {e}")
            return
        try:
            graph = module.graph
        except AttributeError as e:
            print(f"Could not find `graph` in module at path: {path}. debug: {e}")
            return
        if isinstance(graph, Pregel):
            pass
        else:
            print(f"Graph is not a compiled LangGraph graph: {graph}")
            return

        graph.checkpointer = PostgresCheckpoint(at=CheckpointAt.END_OF_STEP)

        USER_SPECIFIED_CHAIN.chain = graph

    # uvicorn.run(app, host="0.0.0.0", port=8100)
    server = uvicorn.Server(uvicorn.Config("app.server:app", host="0.0.0.0", port=8100))
    compose_spec = pathlib.Path(__file__).parent / "docker-compose-cli.yml"

    async def serve_once_ready():
        for _ in range(120):
            conn: Optional[asyncpg.Connection] = None
            try:
                print("Waiting for database to be ready...")
                conn = await connect()
                await conn.execute("select * from assistant limit 1")
                break
            except Exception as exc:
                if debug:
                    print(f"Database not ready, retrying... {exc}")
                if conn:
                    await conn.close()
                await asyncio.sleep(1)
        else:
            raise Exception("Database not ready after 120 seconds. Exiting...")

        await server.serve()

    async def run_both():
        try:
            await asyncio.gather(
                exec_cmd("docker", "compose", "-f", str(compose_spec.resolve()), "up"),
                serve_once_ready(),
            )
        finally:
            await exec_cmd(
                "docker", "compose", "-f", str(compose_spec.resolve()), "down"
            )

    server.config.setup_event_loop()
    asyncio.run(run_both())


async def exec_cmd(cmd: str, *args: str):
    proc = await asyncio.create_subprocess_exec(cmd, *args)
    await proc.communicate()

    if (
        proc.returncode != 0  # success
        and proc.returncode != 130  # user interrupt
    ):
        raise Exception(f"Command failed: {cmd} {' '.join(args)}")
