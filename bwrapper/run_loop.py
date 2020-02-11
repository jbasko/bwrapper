import dataclasses
import time
from typing import Callable, List

from bwrapper.log import LogMixin


@dataclasses.dataclass
class RunLoop(LogMixin):
    first_sleep: float = 0
    sleep: float = 0
    max_iterations: int = 0
    timeout: float = 0
    raise_on_timeout: bool = False
    current_iteration: int = dataclasses.field(default=None, init=False)
    start_time: float = dataclasses.field(default=None, init=False)
    _is_stopped: bool = dataclasses.field(default=False, init=False)

    # List of callable predicates which all should return True in order for the run loop to continue.
    # Register new ones with run_loop.predicates.append(predicate)
    predicates: List[Callable] = dataclasses.field(default_factory=list)

    class TimedOut(Exception):
        """
        Raised when the RunLoop times out and raise_on_timeout is set to True.
        """
        def __init__(self, run_loop):
            super().__init__()
            self.run_loop = run_loop

        def __str__(self):
            return str(self.run_loop)

    def should_run(self):
        """
        Returns True if the RunLoop should continue running.
        """

        if self._is_stopped:
            return False

        if self.start_time is None:
            self.start_time = time.time()
            self.current_iteration = 0

        if self.current_iteration >= self.max_iterations > 0:
            self.log.info(f"Max iterations ({self.max_iterations}) reached, stopping")
            return False

        if 0 < self.timeout < time.time() - self.start_time:
            if self.raise_on_timeout:
                raise self.TimedOut(self)
            else:
                self.log.info(f"Timeout ({self.timeout}) reached, stopping")
                return False

        for predicate in self.predicates:
            if not predicate():
                self.log.info(f"Predicate {predicate.__name__} is not true, stopping")
                return False

        self.current_iteration += 1

        self.log.debug("Sleeping")
        time.sleep(self.first_sleep if self.current_iteration == 1 else self.sleep)
        return True

    def loop_over(self, callback: Callable):
        """
        Repeatedly calls the callback as long as should_run() returns True.
        """
        while self.should_run():
            callback()

    def stop(self):
        self._is_stopped = True


class RunLoopMixin:
    run_loop_sleep = 15
    run_loop_first_sleep = 0
    run_loop_max_iterations = RunLoop.max_iterations
    run_loop_timeout = 0

    class _RunLoop:
        def __get__(self, instance, owner):
            if instance is None:
                return self
            if not hasattr(instance, "_run_loop"):
                setattr(instance, "_run_loop", RunLoop(
                    sleep=instance.run_loop_sleep,
                    first_sleep=instance.run_loop_first_sleep,
                    max_iterations=instance.run_loop_max_iterations,
                    timeout=instance.run_loop_timeout,
                ))
            return getattr(instance, "_run_loop")

    run_loop: RunLoop = _RunLoop()

    def run(self):
        self.run_loop.loop_over(self.run_single_iteration)

    def run_single_iteration(self):
        raise NotImplementedError()
