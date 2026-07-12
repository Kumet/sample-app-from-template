from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Job:
    feature: str
    status: str = "queued"
    priority: int = 100


class Queue:
    def __init__(self, path: Path):
        self.path = path
        self.lock = path.with_suffix(".lock")

    def read(self) -> list[Job]:
        if not self.path.exists():
            return []
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return [Job(**item) for item in raw.get("jobs", [])]

    def add(self, feature: str, priority: int = 100) -> list[Job]:
        jobs = self.read()
        if any(job.feature == feature and job.status not in {"cancelled", "completed"} for job in jobs):
            raise ValueError("Feature is already queued")
        jobs.append(Job(feature, "queued", priority))
        self._write(sorted(jobs, key=lambda job: job.priority))
        return jobs

    def update(self, feature: str, status: str) -> list[Job]:
        jobs = self.read()
        if status not in {"queued", "running", "parked", "cancelled", "failed", "completed"}:
            raise ValueError("Invalid queue status")
        found = False
        updated = []
        for job in jobs:
            if job.feature == feature:
                job, found = Job(job.feature, status, job.priority), True
            updated.append(job)
        if not found:
            raise ValueError("Feature is not queued")
        self._write(updated)
        return updated

    def acquire(self) -> None:
        self.lock.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(self.lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as error:
            raise ValueError("Queue is locked") from error
        os.write(descriptor, str(os.getpid()).encode())
        os.close(descriptor)

    def release(self) -> None:
        if self.lock.exists():
            self.lock.unlink()

    def _write(self, jobs: list[Job]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"version": 1, "jobs": [job.__dict__ for job in jobs]}, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, self.path)
