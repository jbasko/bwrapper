"""
Jobsy is a single-process worker or job scheduler (when called with --enqueue).
"""

import argparse
import dataclasses
import importlib
import inspect
import itertools
import logging
import multiprocessing
import os
import time
from typing import Callable, Dict, Iterator, List, Union, get_type_hints
from uuid import uuid4

from bwrapper.log import LogMixin
from bwrapper.run_loop import RunLoopMixin
from bwrapper.sqs import SqsMessage, SqsQueue

log = logging.getLogger(__name__)


class _JobFailed(Exception):
    pass


MAX_PROCESS_CHECK_INTERVAL = 30


@dataclasses.dataclass
class Job:
    func: Callable
    args: List
    kwargs: Dict
    timeout: int
    message: "JobMessage"

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
            log.info(f"Completed processing {self.message}")
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


class JobMessage(SqsMessage):
    class MessageAttributes:
        id: str
        func: str
        version: str
        timeout: int

    class MessageBody:
        args: List
        kwargs: Dict

    def resolve_job(self) -> "Job":
        args = self.MessageBody.args or ()
        kwargs = self.MessageBody.kwargs or {}
        func_path = self.MessageAttributes.func
        module_path, func_name = func_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        func = getattr(module, func_name)
        timeout = getattr(func, "timeout", 10)
        if self.MessageAttributes.timeout:
            timeout = self.MessageAttributes.timeout

        type_hints = get_type_hints(func)
        func_sig = inspect.signature(func)
        discarded_kwargs = []
        for k in list(kwargs):
            if k not in func_sig.parameters:
                discarded_kwargs.append(kwargs.pop(k))
            if k in type_hints:
                kwargs[k] = self._parse_value(type_hints[k], kwargs[k])

        if discarded_kwargs:
            log.warning(f"Discarded invalid kwargs ({', '.join(discarded_kwargs)}) for function {func_path}")

        return Job(
            message=self,
            func=func,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
        )

    def __str__(self):
        return f"{self.MessageAttributes.func!r} (id={self.MessageAttributes.id!r})"


def new_job_message(
    func: str,
    args: List = None,
    kwargs: Dict = None,
    timeout: int = None,
    version="1.0",
) -> JobMessage:
    return JobMessage(
        attributes={
            "id": str(uuid4()),
            "func": func,
            "version": version,
            "timeout": timeout,
        },
        body={
            "args": args or [],
            "kwargs": kwargs or {},
        }
    )


class Jobsy(LogMixin, RunLoopMixin):
    """
    A primitive, single-worker job runner where jobs are coming from one or more SQS queues
    """

    message_cls = JobMessage

    # What is the longest we will wait before checking again that the process executing the function is still alive.
    _max_process_check_interval = 30

    def __init__(
        self,
        queue_or_queues: Union[SqsQueue, List[SqsQueue]],
        same_process: bool = False,
        max_iterations: int = None,
        job_failed_callback: Callable = None
    ):
        super().__init__()
        self._queues: List[SqsQueue] = [queue_or_queues] if isinstance(queue_or_queues, SqsQueue) else queue_or_queues
        self._same_process = same_process
        self._job_failed_callback = job_failed_callback
        self._queues_generator: Iterator[SqsQueue] = itertools.cycle(self._queues)
        if max_iterations:
            self.run_loop.max_iterations = max_iterations

    def run_single_iteration(self):

        # Hold on to the first received JobMessage and release all the others we have picked
        # as part of the same long poll before we start working on ours.
        message: JobMessage = None

        num_queues_checked = 0
        while message is None and num_queues_checked < len(self._queues):
            queue = next(self._queues_generator)

            m: JobMessage
            for m in queue.receive_messages(message_cls=self.message_cls):
                if message is None:
                    message = m
                else:
                    self.log.debug(f"Releasing {m}")
                    m.release()

            num_queues_checked += 1

        if message is None:
            self.log.debug("Completed iteration, no messages received")
            return

        self.log.info(f"Received {message}")
        job = message.resolve_job()

        # Ensure that we hold on to the message for at least as long as the interval
        # between checking on progress
        message.hold(timeout=job.timeout + self._max_process_check_interval + 5)

        try:
            if self._same_process:
                job.run_in_same_process(log=self.log)
            else:
                job.run_in_separate_process(log=self.log)
        except _JobFailed as exception:
            self._handle_job_failed(job=job, exception=exception)
            pass
        finally:
            # We delete all jobs, even those processing of which failed.
            message.delete()

        self.log.debug("Completed iteration")

    def _handle_job_failed(self, job: Job, exception: Exception):
        """
        Do not override this method. Instead, pass job_failed_callback to Jobsy initialiser.
        """
        if not self._job_failed_callback:
            return

        try:
            self._job_failed_callback(job=job, exception=exception)
        except Exception as cbe:
            self.log.warning("Job failed callback failed with an exception:")
            self.log.exception(cbe)


def main():
    parser = argparse.ArgumentParser(prog="python -m bwrapper.jobsy", description=__doc__)
    parser.add_argument("--queue-url", action="append", dest="queue_urls")
    parser.add_argument("--enqueue")
    parser.add_argument("--args", help="args in arg1,arg2,arg3 format")
    parser.add_argument("--kwargs", help="kwargs in key1:value1,key2:value2 format")
    parser.add_argument("--timeout", type=int)
    parser.add_argument(
        "--same-process", action="store_true",
        help="[worker] Run jobs in the same process (timeouts not supported)",
    )
    parser.add_argument("--log-level", default="info")
    parser.add_argument(
        "--max-iterations", type=int, default=None,
        help="[worker] Maximum number of iterations to run the worker before exiting",
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

    if args.enqueue:
        params = {}
        if args.args:
            params["args"] = args.args.split(",")
        if args.kwargs:
            params["kwargs"] = dict(x.split(":") for x in args.kwargs.split(","))
        if args.timeout:
            params["timeout"] = args.timeout
        for q in queues:
            q.send_message(new_job_message(func=args.enqueue, **params))

    else:
        jobsy = Jobsy(queues, same_process=args.same_process, max_iterations=args.max_iterations)
        jobsy.log.setLevel(log_level)
        jobsy.run()


if __name__ == "__main__":
    main()
