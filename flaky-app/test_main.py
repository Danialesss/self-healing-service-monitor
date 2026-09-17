import asyncio
import multiprocessing

import main


def test_health_reports_ok() -> None:
    result = asyncio.run(main.health())

    assert result == {"status": "ok"}


def test_start_leak_only_creates_one_background_task() -> None:
    async def exercise() -> None:
        main._leaked_chunks.clear()
        main._leak_task = None

        first_result = await main.start_leak()
        first_task = main._leak_task
        second_result = await main.start_leak()

        assert first_result == {"status": "leak started"}
        assert second_result == {"status": "leak already running"}
        assert main._leak_task is first_task

        assert first_task is not None
        first_task.cancel()
        await asyncio.gather(first_task, return_exceptions=True)
        main._leak_task = None
        main._leaked_chunks.clear()

    asyncio.run(exercise())


def run_crash_endpoint() -> None:
    asyncio.run(main.crash())


def test_crash_endpoint_exits_process() -> None:
    process = multiprocessing.Process(target=run_crash_endpoint)
    process.start()
    process.join(timeout=5)

    assert process.exitcode == 1