"""On demand: started on use or warm-up, kept while used, stopped after the idle time, each use
restarting the clock; a failed start is reported and tried again on the next use."""

import asyncio

from mei.ondemand import OnDemand


def resource(idle_s=0.2, fail=0):
    log: list[str] = []
    attempts = [0]

    async def start():
        attempts[0] += 1
        await asyncio.sleep(0.05)
        if attempts[0] <= fail:
            raise RuntimeError("no GPU")
        log.append("start")
        return f"engine{attempts[0]}"

    async def stop(value):
        log.append(f"stop {value}")
    return OnDemand("test", start, stop, idle_s), log


async def test_started_on_use_and_stopped_after_idle():
    od, log = resource()
    assert od.ready is None
    assert await od.get() == "engine1" and od.ready == "engine1"
    await asyncio.sleep(0.3)
    assert od.ready is None and log == ["start", "stop engine1"]
    assert await od.get() == "engine2"  # used again: started again
    await od.close()


async def test_each_use_restarts_the_idle_clock():
    od, log = resource(idle_s=0.2)
    await od.get()
    for _ in range(4):
        await asyncio.sleep(0.1)
        await od.get()
    assert log == ["start"]  # 0.5 s in use, never 0.2 s idle
    await asyncio.sleep(0.3)
    assert log == ["start", "stop engine1"]


async def test_warm_starts_ahead_without_waiting_and_shares_one_start():
    od, log = resource()
    od.warm()
    assert od.ready is None  # starting, not up yet
    values = await asyncio.gather(od.get(), od.get())
    assert values == ["engine1", "engine1"] and log == ["start"]
    await od.close()
    assert log == ["start", "stop engine1"] and od.ready is None


async def test_a_failed_start_is_reported_and_the_next_use_tries_again():
    od, _ = resource(fail=1)
    od.warm()
    await asyncio.sleep(0.1)
    assert od.ready is None and od.error == "no GPU"
    assert await od.get() == "engine2" and od.error == ""
    await od.close()


async def test_closing_while_starting_leaves_nothing_running():
    od, log = resource()
    od.warm()
    await od.close()
    await asyncio.sleep(0.1)
    assert od.ready is None and log == []
