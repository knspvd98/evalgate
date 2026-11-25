import asyncio
import json
import os
import sys

import pytest

from evalgate.cli import main


def test_stdio_lists_runs_compares_and_retrieves(tmp_path):
    mcp = pytest.importorskip("mcp")
    from mcp.client.stdio import stdio_client
    assert main(["init", str(tmp_path)]) == 0

    async def exercise():
        options = mcp.StdioServerParameters(
            command=sys.executable, args=["-c", "from evalgate.mcp_server import main; main()"],
            env={**os.environ, "EVALGATE_WORKSPACE": str(tmp_path)},
        )
        async with stdio_client(options) as pipes, mcp.ClientSession(*pipes) as session:
            await session.initialize()
            tools = await session.list_tools()
            assert {t.name for t in tools.tools} == {"list_suites", "run_suite", "compare_runs", "get_run_results"}
            ids = []
            for recording in ("baseline", "regression"):
                result = await session.call_tool("run_suite", {"suite": "water-utility-intake", "recording": recording})
                assert not result.isError
                row = json.loads(result.content[0].text)
                assert row["passed"] == (recording == "baseline")
                ids.append(row["run_id"])
            result = await session.call_tool("get_run_results", {"run_id": ids[0]})
            assert len(json.loads(result.content[0].text)["cases"]) == 8
            result = await session.call_tool("compare_runs", dict(zip(("baseline", "candidate"), ids)))
            assert "forbidden_action" in json.loads(result.content[0].text)["close-request"]
    asyncio.run(exercise())
