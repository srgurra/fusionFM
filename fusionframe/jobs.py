from __future__ import annotations

import asyncio
import inspect
import json
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass, replace
from pathlib import Path


@dataclass
class ScheduledJob:
    func: callable
    interval: int
    name: str
    max_retries: int = 0
    retry_backoff: float = 0.0
    timeout: float | None = None
    persist: bool = True
    last_run: float | None = None


@dataclass
class JobRecord:
    id: str
    name: str
    status: str
    attempts: int = 0
    max_retries: int = 0
    retry_backoff: float = 0.0
    timeout: float | None = None
    created_at: float = 0.0
    updated_at: float = 0.0
    started_at: float | None = None
    completed_at: float | None = None
    cancelled_at: float | None = None
    error: str | None = None
    result: object | None = None


@dataclass
class DispatchedJob:
    id: str
    task_name: str
    payload: dict
    status: str
    attempts: int = 0
    max_retries: int = 0
    retry_backoff: float = 0.0
    timeout: float | None = None
    lease_until: float | None = None
    created_at: float = 0.0
    updated_at: float = 0.0
    completed_at: float | None = None
    error: str | None = None
    result: object | None = None


class JobStore:
    def save(self, record: JobRecord):
        raise NotImplementedError

    def get(self, job_id: str) -> JobRecord | None:
        raise NotImplementedError

    def list(self) -> list[JobRecord]:
        raise NotImplementedError

    def save_schedule(self, schedule: ScheduledJob):
        return None

    def get_schedule(self, name: str) -> ScheduledJob | None:
        return None

    def list_schedules(self) -> list[ScheduledJob]:
        return []


class DistributedJobBroker:
    def enqueue(self, task_name: str, payload: dict, *, max_retries: int = 0, retry_backoff: float = 0.0, timeout: float | None = None) -> str:
        raise NotImplementedError

    def claim_next(self, *, lease_seconds: float = 30.0) -> DispatchedJob | None:
        raise NotImplementedError

    def complete(self, job_id: str, result=None):
        raise NotImplementedError

    def fail(self, job_id: str, error: str):
        raise NotImplementedError

    def retry(self, job_id: str):
        raise NotImplementedError

    def get_dispatched(self, job_id: str) -> DispatchedJob | None:
        raise NotImplementedError

    def list_dispatched(self) -> list[DispatchedJob]:
        raise NotImplementedError


class InMemoryJobStore(JobStore):
    def __init__(self):
        self._records: dict[str, JobRecord] = {}
        self._schedules: dict[str, ScheduledJob] = {}

    def save(self, record: JobRecord):
        self._records[record.id] = replace(record)

    def get(self, job_id: str) -> JobRecord | None:
        record = self._records.get(job_id)
        return replace(record) if record else None

    def list(self) -> list[JobRecord]:
        return [replace(record) for record in sorted(self._records.values(), key=lambda item: item.created_at)]

    def save_schedule(self, schedule: ScheduledJob):
        self._schedules[schedule.name] = replace(schedule, func=schedule.func)

    def get_schedule(self, name: str) -> ScheduledJob | None:
        schedule = self._schedules.get(name)
        return replace(schedule, func=schedule.func) if schedule else None

    def list_schedules(self) -> list[ScheduledJob]:
        return [
            replace(schedule, func=schedule.func)
            for schedule in sorted(self._schedules.values(), key=lambda item: item.name)
        ]


class SQLiteJobStore(JobStore, DistributedJobBroker):
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def save(self, record: JobRecord):
        payload = asdict(record)
        payload["result"] = json.dumps(record.result)
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                INSERT INTO job_records (
                    id, name, status, attempts, max_retries, retry_backoff, timeout,
                    created_at, updated_at, started_at, completed_at, cancelled_at, error, result
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    status=excluded.status,
                    attempts=excluded.attempts,
                    max_retries=excluded.max_retries,
                    retry_backoff=excluded.retry_backoff,
                    timeout=excluded.timeout,
                    created_at=excluded.created_at,
                    updated_at=excluded.updated_at,
                    started_at=excluded.started_at,
                    completed_at=excluded.completed_at,
                    cancelled_at=excluded.cancelled_at,
                    error=excluded.error,
                    result=excluded.result
                """,
                (
                    payload["id"],
                    payload["name"],
                    payload["status"],
                    payload["attempts"],
                    payload["max_retries"],
                    payload["retry_backoff"],
                    payload["timeout"],
                    payload["created_at"],
                    payload["updated_at"],
                    payload["started_at"],
                    payload["completed_at"],
                    payload["cancelled_at"],
                    payload["error"],
                    payload["result"],
                ),
            )

    def get(self, job_id: str) -> JobRecord | None:
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                """
                SELECT id, name, status, attempts, max_retries, retry_backoff, timeout,
                       created_at, updated_at, started_at, completed_at, cancelled_at, error, result
                FROM job_records
                WHERE id = ?
                """,
                (job_id,),
            ).fetchone()
        return _sqlite_row_to_record(row)

    def list(self) -> list[JobRecord]:
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                """
                SELECT id, name, status, attempts, max_retries, retry_backoff, timeout,
                       created_at, updated_at, started_at, completed_at, cancelled_at, error, result
                FROM job_records
                ORDER BY created_at ASC
                """
            ).fetchall()
        return [_sqlite_row_to_record(row) for row in rows]

    def save_schedule(self, schedule: ScheduledJob):
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                INSERT INTO scheduled_jobs (
                    name, interval, max_retries, retry_backoff, timeout, last_run
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    interval=excluded.interval,
                    max_retries=excluded.max_retries,
                    retry_backoff=excluded.retry_backoff,
                    timeout=excluded.timeout,
                    last_run=excluded.last_run
                """,
                (
                    schedule.name,
                    schedule.interval,
                    schedule.max_retries,
                    schedule.retry_backoff,
                    schedule.timeout,
                    schedule.last_run,
                ),
            )

    def get_schedule(self, name: str) -> ScheduledJob | None:
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                """
                SELECT name, interval, max_retries, retry_backoff, timeout, last_run
                FROM scheduled_jobs
                WHERE name = ?
                """,
                (name,),
            ).fetchone()
        if row is None:
            return None
        return ScheduledJob(
            func=None,
            name=row[0],
            interval=row[1],
            max_retries=row[2],
            retry_backoff=row[3],
            timeout=row[4],
            last_run=row[5],
        )

    def list_schedules(self) -> list[ScheduledJob]:
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                """
                SELECT name, interval, max_retries, retry_backoff, timeout, last_run
                FROM scheduled_jobs
                ORDER BY name ASC
                """
            ).fetchall()
        return [
            ScheduledJob(
                func=None,
                name=row[0],
                interval=row[1],
                max_retries=row[2],
                retry_backoff=row[3],
                timeout=row[4],
                last_run=row[5],
            )
            for row in rows
        ]

    def enqueue(self, task_name: str, payload: dict, *, max_retries: int = 0, retry_backoff: float = 0.0, timeout: float | None = None) -> str:
        job = DispatchedJob(
            id=str(uuid.uuid4()),
            task_name=task_name,
            payload=dict(payload),
            status="queued",
            max_retries=max_retries,
            retry_backoff=retry_backoff,
            timeout=timeout,
            created_at=time.time(),
            updated_at=time.time(),
        )
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                INSERT INTO distributed_jobs (
                    id, task_name, payload, status, attempts, max_retries, retry_backoff,
                    timeout, lease_until, created_at, updated_at, completed_at, error, result
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.id,
                    job.task_name,
                    json.dumps(job.payload),
                    job.status,
                    job.attempts,
                    job.max_retries,
                    job.retry_backoff,
                    job.timeout,
                    job.lease_until,
                    job.created_at,
                    job.updated_at,
                    job.completed_at,
                    job.error,
                    json.dumps(job.result),
                ),
            )
        return job.id

    def claim_next(self, *, lease_seconds: float = 30.0) -> DispatchedJob | None:
        now = time.time()
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                """
                SELECT id, task_name, payload, status, attempts, max_retries, retry_backoff,
                       timeout, lease_until, created_at, updated_at, completed_at, error, result
                FROM distributed_jobs
                WHERE status IN ('queued', 'retrying')
                   OR (status = 'running' AND (lease_until IS NULL OR lease_until < ?))
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (now,),
            ).fetchone()
            if row is None:
                return None
            claimed = _sqlite_row_to_dispatched_job(row)
            claimed.status = "running"
            claimed.attempts += 1
            claimed.lease_until = now + lease_seconds
            claimed.updated_at = now
            connection.execute(
                """
                UPDATE distributed_jobs
                SET status = ?, attempts = ?, lease_until = ?, updated_at = ?
                WHERE id = ?
                """,
                (claimed.status, claimed.attempts, claimed.lease_until, claimed.updated_at, claimed.id),
            )
        return claimed

    def complete(self, job_id: str, result=None):
        now = time.time()
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                UPDATE distributed_jobs
                SET status = 'succeeded',
                    result = ?,
                    error = NULL,
                    completed_at = ?,
                    updated_at = ?,
                    lease_until = NULL
                WHERE id = ?
                """,
                (json.dumps(result), now, now, job_id),
            )

    def fail(self, job_id: str, error: str):
        now = time.time()
        job = self.get_dispatched(job_id)
        if job is None:
            return
        next_status = "failed"
        if job.attempts <= job.max_retries:
            next_status = "retrying"
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                UPDATE distributed_jobs
                SET status = ?,
                    error = ?,
                    updated_at = ?,
                    completed_at = CASE WHEN ? = 'failed' THEN ? ELSE completed_at END,
                    lease_until = NULL
                WHERE id = ?
                """,
                (next_status, error, now, next_status, now, job_id),
            )

    def retry(self, job_id: str):
        now = time.time()
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                UPDATE distributed_jobs
                SET status = 'retrying',
                    lease_until = NULL,
                    updated_at = ?
                WHERE id = ?
                """,
                (now, job_id),
            )

    def get_dispatched(self, job_id: str) -> DispatchedJob | None:
        with sqlite3.connect(self.path) as connection:
            row = connection.execute(
                """
                SELECT id, task_name, payload, status, attempts, max_retries, retry_backoff,
                       timeout, lease_until, created_at, updated_at, completed_at, error, result
                FROM distributed_jobs
                WHERE id = ?
                """,
                (job_id,),
            ).fetchone()
        return _sqlite_row_to_dispatched_job(row)

    def list_dispatched(self) -> list[DispatchedJob]:
        with sqlite3.connect(self.path) as connection:
            rows = connection.execute(
                """
                SELECT id, task_name, payload, status, attempts, max_retries, retry_backoff,
                       timeout, lease_until, created_at, updated_at, completed_at, error, result
                FROM distributed_jobs
                ORDER BY created_at ASC
                """
            ).fetchall()
        return [_sqlite_row_to_dispatched_job(row) for row in rows]

    def _ensure_schema(self):
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS job_records (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL,
                    max_retries INTEGER NOT NULL,
                    retry_backoff REAL NOT NULL,
                    timeout REAL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    started_at REAL,
                    completed_at REAL,
                    cancelled_at REAL,
                    error TEXT,
                    result TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduled_jobs (
                    name TEXT PRIMARY KEY,
                    interval INTEGER NOT NULL,
                    max_retries INTEGER NOT NULL,
                    retry_backoff REAL NOT NULL,
                    timeout REAL,
                    last_run REAL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS distributed_jobs (
                    id TEXT PRIMARY KEY,
                    task_name TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL,
                    max_retries INTEGER NOT NULL,
                    retry_backoff REAL NOT NULL,
                    timeout REAL,
                    lease_until REAL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    completed_at REAL,
                    error TEXT,
                    result TEXT
                )
                """
            )


class JobQueue:
    def __init__(self, *, store: JobStore | None = None, max_workers: int = 1):
        self.queue = asyncio.Queue()
        self.store = store or InMemoryJobStore()
        self.scheduled_jobs: list[ScheduledJob] = []
        self.max_workers = max(1, max_workers)
        self._worker_tasks: list[asyncio.Task] = []
        self._scheduler_task = None
        self._running = False
        self._active_tasks: dict[str, asyncio.Task] = {}

    async def start(self):
        if self._running:
            return
        self._running = True
        self._worker_tasks = [
            asyncio.create_task(self._worker(index))
            for index in range(self.max_workers)
        ]
        await self._run_due_jobs()
        self._scheduler_task = asyncio.create_task(self._scheduler())

    async def stop(self):
        if not self._running:
            return
        self._running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            await _await_cancel(self._scheduler_task)
        for job_id in list(self._active_tasks):
            await self.cancel_job(job_id)
        for _ in self._worker_tasks:
            await self.queue.put(None)
        for task in self._worker_tasks:
            await _await_cancel(task)
        self._worker_tasks = []

    async def enqueue(
        self,
        func,
        *args,
        name: str | None = None,
        max_retries: int = 0,
        retry_backoff: float = 0.0,
        timeout: float | None = None,
        **kwargs,
    ):
        record = JobRecord(
            id=str(uuid.uuid4()),
            name=name or getattr(func, "__name__", "job"),
            status="queued",
            max_retries=max_retries,
            retry_backoff=retry_backoff,
            timeout=timeout,
            created_at=time.time(),
            updated_at=time.time(),
        )
        self.store.save(record)
        await self.queue.put((record.id, func, args, kwargs))
        return record.id

    def schedule(
        self,
        interval,
        *,
        name=None,
        max_retries: int = 0,
        retry_backoff: float = 0.0,
        timeout: float | None = None,
        persist: bool = True,
    ):
        def decorator(func):
            schedule_name = name or func.__name__
            existing = self.store.get_schedule(schedule_name) if persist else None
            scheduled = ScheduledJob(
                func=func,
                interval=interval,
                name=schedule_name,
                max_retries=max_retries,
                retry_backoff=retry_backoff,
                timeout=timeout,
                persist=persist,
                last_run=existing.last_run if existing else None,
            )
            self.scheduled_jobs = [
                job for job in self.scheduled_jobs if job.name != schedule_name
            ]
            self.scheduled_jobs.append(scheduled)
            if persist:
                self.store.save_schedule(scheduled)
            return func

        return decorator

    def get_job(self, job_id: str) -> JobRecord | None:
        return self.store.get(job_id)

    def list_jobs(self) -> list[JobRecord]:
        return self.store.list()

    def list_schedules(self) -> list[ScheduledJob]:
        return [replace(schedule, func=schedule.func) for schedule in self.scheduled_jobs]

    async def cancel_job(self, job_id: str) -> bool:
        record = self.store.get(job_id)
        if record is None or record.status in {"succeeded", "failed", "cancelled"}:
            return False
        task = self._active_tasks.get(job_id)
        if task:
            task.cancel()
        record.status = "cancelled"
        record.cancelled_at = time.time()
        record.updated_at = record.cancelled_at
        self.store.save(record)
        return True

    async def _worker(self, worker_index: int):
        while True:
            item = await self.queue.get()
            if item is None:
                return
            job_id, func, args, kwargs = item
            record = self.store.get(job_id)
            if record is None or record.status == "cancelled":
                continue
            record.status = "running"
            record.attempts += 1
            record.started_at = time.time()
            record.updated_at = record.started_at
            self.store.save(record)
            task = asyncio.create_task(self._execute_job(func, args, kwargs, record.timeout))
            self._active_tasks[job_id] = task
            try:
                record.result = await task
                record.status = "succeeded"
                record.error = None
                record.completed_at = time.time()
            except asyncio.CancelledError:
                record.status = "cancelled"
                record.cancelled_at = time.time()
                record.error = "Job cancelled"
            except TimeoutError:
                record.error = f"Job exceeded timeout of {record.timeout} seconds"
                if record.attempts <= record.max_retries:
                    await self._retry_job(record, func, args, kwargs)
                    self._active_tasks.pop(job_id, None)
                    continue
                record.status = "failed"
                record.completed_at = time.time()
            except Exception as exc:
                record.error = str(exc)
                if record.attempts <= record.max_retries:
                    await self._retry_job(record, func, args, kwargs)
                    self._active_tasks.pop(job_id, None)
                    continue
                record.status = "failed"
                record.completed_at = time.time()
            finally:
                self._active_tasks.pop(job_id, None)
            record.updated_at = time.time()
            self.store.save(record)

    async def _retry_job(self, record: JobRecord, func, args, kwargs):
        record.status = "retrying"
        record.updated_at = time.time()
        self.store.save(record)
        if record.retry_backoff:
            await asyncio.sleep(record.retry_backoff)
        await self.queue.put((record.id, func, args, kwargs))

    async def _execute_job(self, func, args, kwargs, timeout):
        async def invoke():
            result = func(*args, **kwargs)
            if inspect.isawaitable(result):
                return await result
            return result

        if timeout is not None:
            return await asyncio.wait_for(invoke(), timeout=timeout)
        return await invoke()

    async def _scheduler(self):
        while self._running:
            await self._run_due_jobs()
            await asyncio.sleep(0.2)

    async def _run_due_jobs(self):
        now = time.time()
        for index, job in enumerate(list(self.scheduled_jobs)):
            if job.last_run is None or now - job.last_run >= job.interval:
                await self.enqueue(
                    job.func,
                    name=job.name,
                    max_retries=job.max_retries,
                    retry_backoff=job.retry_backoff,
                    timeout=job.timeout,
                )
                updated = replace(job, last_run=now)
                self.scheduled_jobs[index] = updated
                if updated.persist:
                    self.store.save_schedule(updated)


class DistributedJobQueue:
    def __init__(self, broker: DistributedJobBroker):
        self.broker = broker
        self.tasks: dict[str, callable] = {}

    def task(self, name: str | None = None):
        def decorator(func):
            task_name = name or func.__name__
            self.tasks[task_name] = func
            return func

        return decorator

    def enqueue(self, task_name: str, payload: dict, *, max_retries: int = 0, retry_backoff: float = 0.0, timeout: float | None = None):
        return self.broker.enqueue(
            task_name,
            payload,
            max_retries=max_retries,
            retry_backoff=retry_backoff,
            timeout=timeout,
        )


class JobWorker:
    def __init__(self, queue: DistributedJobQueue, *, lease_seconds: float = 30.0, poll_interval: float = 0.1):
        self.queue = queue
        self.lease_seconds = lease_seconds
        self.poll_interval = poll_interval

    async def run_once(self):
        job = self.queue.broker.claim_next(lease_seconds=self.lease_seconds)
        if job is None:
            return None
        handler = self.queue.tasks.get(job.task_name)
        if handler is None:
            self.queue.broker.fail(job.id, f"Unknown task '{job.task_name}'")
            return job
        try:
            result = handler(**job.payload)
            if inspect.isawaitable(result):
                if job.timeout is not None:
                    result = await asyncio.wait_for(result, timeout=job.timeout)
                else:
                    result = await result
            self.queue.broker.complete(job.id, result=result)
        except TimeoutError:
            self.queue.broker.fail(job.id, f"Job exceeded timeout of {job.timeout} seconds")
        except Exception as exc:
            self.queue.broker.fail(job.id, str(exc))
        return self.queue.broker.get_dispatched(job.id)

    async def run_until_empty(self, *, max_iterations: int = 100):
        processed = []
        for _ in range(max_iterations):
            job = await self.run_once()
            if job is None:
                break
            processed.append(job)
            if job.status == "retrying":
                continue
        return processed


def _sqlite_row_to_record(row):
    if row is None:
        return None
    result = json.loads(row[13]) if row[13] else None
    return JobRecord(
        id=row[0],
        name=row[1],
        status=row[2],
        attempts=row[3],
        max_retries=row[4],
        retry_backoff=row[5],
        timeout=row[6],
        created_at=row[7],
        updated_at=row[8],
        started_at=row[9],
        completed_at=row[10],
        cancelled_at=row[11],
        error=row[12],
        result=result,
    )


def _sqlite_row_to_dispatched_job(row):
    if row is None:
        return None
    payload = json.loads(row[2]) if row[2] else {}
    result = json.loads(row[13]) if row[13] else None
    return DispatchedJob(
        id=row[0],
        task_name=row[1],
        payload=payload,
        status=row[3],
        attempts=row[4],
        max_retries=row[5],
        retry_backoff=row[6],
        timeout=row[7],
        lease_until=row[8],
        created_at=row[9],
        updated_at=row[10],
        completed_at=row[11],
        error=row[12],
        result=result,
    )


async def _await_cancel(task):
    try:
        await task
    except asyncio.CancelledError:
        pass
