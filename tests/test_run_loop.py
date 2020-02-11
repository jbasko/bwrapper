import time

from bwrapper.run_loop import RunLoop


def test_run_loop_respects_max_iterations():
    run_loop = RunLoop(max_iterations=5)
    assert run_loop.current_iteration is None

    calls = []

    run_loop.loop_over(lambda: calls.append(1))
    assert len(calls) == 5
    assert run_loop.current_iteration == 5

    assert not run_loop.should_run()
    assert run_loop.current_iteration == 5

    run_loop.loop_over(lambda: calls.append(1))
    assert len(calls) == 5
    assert run_loop.current_iteration == 5


def test_run_loop_respects_timeout():
    run_loop = RunLoop(timeout=0.01, max_iterations=10000)

    count = 0

    def callback():
        nonlocal count
        count += 1

    start_time = time.time()
    run_loop.loop_over(callback)
    end_time = time.time()

    assert end_time - start_time < 0.05
    assert count > 10
