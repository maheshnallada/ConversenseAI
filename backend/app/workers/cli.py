import argparse
import asyncio
import logging
import os
import signal
import sys
import threading
import time

from app.core.env import load_env_file

load_env_file()

from app.core.logging import configure_logging
from app.queue.broker import get_message_broker
from app.queue.limiter import get_concurrency_limiter
from app.queue.outbox_publisher import OutboxPublisher
from app.storage.db import create_session_factory, init_db
from app.workers.analytics_worker import AnalyticsWorker
from app.workers.evaluation_worker import EvaluationWorker
from app.workers.general_worker import GeneralWorker

logger = logging.getLogger("conversense.workers")


async def run_worker_loop_async(
    name: str,
    worker,
    stop_event: asyncio.Event,
    batch_size: int = 5,
    idle_sleep_s: float = 0.5,
) -> None:
    logger.info("Worker [%s] started (async loop, batch_size=%d).", name, batch_size)
    while not stop_event.is_set():
        try:
            if hasattr(worker, "run_batch_async"):
                processed = await worker.run_batch_async(count=batch_size, timeout_ms=1000)
            else:
                processed = await asyncio.to_thread(worker.run_once, timeout_ms=1000)
            if processed == 0:
                await asyncio.sleep(idle_sleep_s)
        except Exception as e:
            logger.error("Worker [%s] async loop error: %s", name, e)
            await asyncio.sleep(idle_sleep_s)
    logger.info("Worker [%s] stopped gracefully.", name)


async def run_outbox_loop_async(
    outbox: OutboxPublisher,
    stop_event: asyncio.Event,
    idle_sleep_s: float = 0.5,
) -> None:
    logger.info("Outbox relay started (async loop).")
    while not stop_event.is_set():
        try:
            count = await asyncio.to_thread(outbox.publish_pending)
            if count == 0:
                await asyncio.sleep(idle_sleep_s)
        except Exception as e:
            logger.error("Outbox relay async loop error: %s", e)
            await asyncio.sleep(idle_sleep_s)
    logger.info("Outbox relay stopped gracefully.")


async def main_async(args) -> None:
    session_factory = create_session_factory(args.db_url)
    init_db(session_factory)
    broker = get_message_broker(args.redis_url)
    limiter = get_concurrency_limiter(max_concurrency=args.concurrency)

    stop_event = asyncio.Event()

    def _sig_handler():
        logger.info("Termination signal received. Shutting down workers...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    if sys.platform != "win32":
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _sig_handler)

    tasks = []
    if args.role in ("outbox", "all"):
        outbox = OutboxPublisher(session_factory, broker=broker)
        tasks.append(run_outbox_loop_async(outbox, stop_event, args.interval))

    if args.role in ("general", "all"):
        general = GeneralWorker(session_factory, broker=broker)
        tasks.append(
            run_worker_loop_async("general", general, stop_event, args.batch_size, args.interval)
        )

    if args.role in ("evaluation", "all"):
        evaluation = EvaluationWorker(session_factory, broker=broker, limiter=limiter)
        tasks.append(
            run_worker_loop_async("evaluation", evaluation, stop_event, args.batch_size, args.interval)
        )

    if args.role in ("analytics", "all"):
        analytics = AnalyticsWorker(session_factory, broker=broker)
        tasks.append(
            run_worker_loop_async("analytics", analytics, stop_event, args.batch_size, args.interval)
        )

    logger.info(
        "Async worker engine initialized in role [%s] (batch_size=%d, concurrency=%d).",
        args.role,
        args.batch_size,
        args.concurrency,
    )
    try:
        await asyncio.gather(*tasks)
    except (asyncio.CancelledError, KeyboardInterrupt):
        stop_event.set()


def main() -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description="Conversense AI Scalable Async Worker Runner")
    parser.add_argument(
        "--role",
        choices=["general", "evaluation", "analytics", "outbox", "all"],
        default="all",
        help="Worker role to run",
    )
    parser.add_argument(
        "--db-url",
        default=os.getenv("DATABASE_URL", "sqlite:///./conversense.sqlite3"),
        help="Database connection URL",
    )
    parser.add_argument(
        "--redis-url",
        default=os.getenv("REDIS_URL"),
        help="Redis connection URL",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.5,
        help="Idle sleep interval in seconds",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=int(os.getenv("WORKER_BATCH_SIZE", "5")),
        help="Number of messages to pull and process concurrently per iteration",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=int(os.getenv("EVALUATION_MAX_CONCURRENCY", "15")),
        help="Maximum concurrent LLM evaluations across the cluster",
    )
    args = parser.parse_args()

    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        logger.info("Workers stopped via KeyboardInterrupt.")


if __name__ == "__main__":
    main()
