"""
Jobsy is a single-process worker or job scheduler (when called with --enqueue).
"""

import argparse
import contextlib
import dataclasses
import importlib
import itertools
import logging
import multiprocessing
import os
import time
from typing import Callable, Dict, Iterator, List, Tuple, Union

from bwrapper.log import LogMixin
from bwrapper.run_loop import RunLoopMixin
from bwrapper.sqs import SqsMessage, SqsQueue

log = logging.getLogger(__name__)


class JobsyException(Exception):
    pass


class _JobFailed(JobsyException):
    pass


class _BadMessage(JobsyException):
    pass


DEFAULT_TIMEOUT = 10
MAX_PROCESS_CHECK_INTERVAL = 30


@dataclasses.dataclass
class Job:
    func: Callable
    args: Tuple
    kwargs: Dict
    timeout: int
    message: SqsMessage

    def run_in_separate_process(self, log: logging.Logger):
        """
        Runs the function in a separate process, but this call is still blocking.
        This keeps waiting for the job to complete or to time out.
        """

        process = multiprocessing.Process(target=self.func, args=self.args, kwargs=self.kwargs)
        process.start()

        started = time.time()
        while time.time() - started < self.timeout and process.is_alive():
            # Wait for 10% of the expected timeout, but no longer than 30 seconds
            time.sleep(min(self.timeout / 10.0, MAX_PROCESS_CHECK_INTERVAL))

        if process.is_alive():
            log.warning(f"Processing {self.message} has timed out, terminating it")

            started_terminating = time.time()
            process.terminate()
            while time.time() - started_terminating < 3.0 and process.is_alive():
                time.sleep(.1)

            if process.is_alive():
                log.error(f"Terminating {self.message} has timed out, killing it now")
                started_killing = time.time()
                process.kill()
                while time.time() - started_killing < 1.0 and process.is_alive():
                    time.sleep(.1)

        if process.exitcode == 0:
            log.debug(f"Completed processing {self.message}")
        else:
            log.error(f"Processing {self.message} exited with code {process.exitcode}")
            raise _JobFailed()

    def run_in_same_process(self, log: logging.Logger):
        try:
            self.func(*self.args, **self.kwargs)
        except Exception as e:
            log.error(f"Processing {self.message} failed:")
            log.exception(e)
            raise _JobFailed()


def resolve_func_call(*, func_path):
    module_path, func_name = func_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    func = getattr(module, func_name)
    assert callable(func)
    return func


class Jobsy(LogMixin, RunLoopMixin):
    """
    A primitive, single-worker job runner where jobs are coming from one or more SQS queues
    """

    # What is the longest we will wait before checking again that the process executing the function is still alive.
    _max_process_check_interval = 30

    def __init__(
        self,
        queues: Union[str, List[str], SqsQueue, List[SqsQueue]],
        *,
        same_process: bool = False,
        max_iterations: int = None,
        job_runner_path: str = None,
        default_timeout: int = None,
        delete_on_failure: bool = False,
    ):
        super().__init__()

        self.queues = []
        if isinstance(queues, SqsQueue):
            self.queues.append(queues)
        elif isinstance(queues, str):
            self.queues.append(SqsQueue(url=queues))
        else:
            for q in queues:
                if isinstance(q, str):
                    self.queues.append(SqsQueue(url=q))
                else:
                    self.queues.append(q)

        self._same_process = same_process
        self._queues_generator: Iterator[SqsQueue] = itertools.cycle(self.queues)

        self._job_runner = None
        if job_runner_path:
            self._job_runner = resolve_func_call(func_path=job_runner_path)

        if max_iterations:
            self.run_loop.max_iterations = max_iterations

        self.default_timeout = default_timeout or DEFAULT_TIMEOUT

        # If set to True, SQS messages will be deleted even when the job handling fails.
        self.delete_on_failure = delete_on_failure

    def run_single_iteration(self):

        # Hold on to the first received message and release all the others we have picked
        # as part of the same long poll before we start working on ours.
        message: SqsMessage = None

        num_queues_checked = 0
        while message is None and num_queues_checked < len(self.queues):
            queue = next(self._queues_generator)
            message = queue.receive_message()
            num_queues_checked += 1

        if message is None:
            self.log.debug("Completed iteration, no messages received")
            return

        self.log.debug(f"Received {message}: {message.raw}")
        self.handle_message(message)
        self.log.debug("Completed iteration")

    def handle_message(self, message: SqsMessage):
        with self.job_context(message=message) as job:
            self.handle_job(job=job)

    @contextlib.contextmanager
    def job_context(
        self,
        message: SqsMessage,
        *,
        delete_on_failure=None,
        timeout: int = None,
    ) -> Job:
        """
        Context manager that takes care of:
        1) changing message visibility according to the timeout
        2) releasing or deleting the message afterwards.
        """
        if delete_on_failure is None:
            delete_on_failure = self.delete_on_failure
        if timeout is None:
            timeout = self.default_timeout

        if timeout is not None:
            # Ensure that we hold on to the message for at least as long as the interval
            # between checking on progress
            message.hold(timeout=timeout + self._max_process_check_interval + 5)

        has_failed = None

        try:
            yield self.create_job_from_message(message, timeout=timeout)
        except Exception as exception:
            has_failed = True
            self.handle_failure(message=message, exception=exception)
            if delete_on_failure:
                message.delete()
            else:
                message.release()
        finally:
            if not has_failed:
                message.delete()

    def create_job_from_message(self, message: SqsMessage, timeout: int = None) -> Job:
        message_copy = message.copy()
        message_copy.queue_url = message.queue_url
        return Job(
            func=self._job_runner or self.run_job,
            args=(),
            kwargs={
                # Pass a copy based on the raw message. Queue object must not be passed as part of the message.
                "message": message_copy,
            },
            timeout=timeout or self.default_timeout,
            message=message,
        )

    def handle_failure(self, message: SqsMessage, exception: Exception, **kwargs):
        """
        Override this method as needed.
        The message will be deleted/released after this method returns.
        """
        pass

    def handle_job(self, job: Job):
        if self._same_process:
            job.run_in_same_process(log=self.log)
        else:
            job.run_in_separate_process(log=self.log)

    def run_job(self, *args, **kwargs):
        raise NotImplementedError()


def main():
    parser = argparse.ArgumentParser(prog="python -m bwrapper.jobsy", description=__doc__)
    parser.add_argument("--queue-url", action="append", dest="queue_urls")
    parser.add_argument(
        "--same-process", action="store_true",
        help="[worker] Run jobs in the same process (timeouts not supported)",
    )
    parser.add_argument("--log-level", default="info")
    parser.add_argument(
        "--max-iterations", type=int, default=None,
        help="[worker] Maximum number of iterations to run the worker before exiting",
    )
    parser.add_argument(
        "--handler-path",
        help="'module.function' path to the function that handles messages",
    )

    args = parser.parse_args()

    log_level = getattr(logging, args.log_level.upper())
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] [%(name)s] (%(funcName)s) %(message)s",
    )
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.INFO)

    queues: List[SqsQueue]
    if not args.queue_urls:
        queues = [SqsQueue(url=os.environ["SQS_QUEUE_URL"])]
    else:
        queues = [SqsQueue(url=url) for url in args.queue_urls]

    jobsy = Jobsy(
        queues,
        same_process=args.same_process,
        max_iterations=args.max_iterations,
        job_runner_path=args.handler_path,
    )
    jobsy.log.setLevel(log_level)
    jobsy.run()


if __name__ == "__main__":
    main()
