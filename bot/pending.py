"""Colas de trabajo que sobreviven a un reinicio del bot.

Cada trabajo se guarda en un JSON al entrar, al empezar y al terminar. Al arrancar,
lo que quedo pendiente (o a medias) se vuelve a encolar. Un trabajo que ha empezado
MAX_TRIES veces sin terminar (p.ej. porque tumba al bot) se descarta.
"""
import json
import queue
import threading
import time
import uuid
from pathlib import Path

MAX_TRIES = 3
MAX_AGE = 24 * 3600


class PersistentJobs:
    def __init__(self, path: Path):
        self.path = path
        self.q = queue.Queue()
        self.lock = threading.Lock()
        self.items = {}                      # _id -> trabajo (pendientes y en curso)

    def _save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(list(self.items.values()), ensure_ascii=False))
        tmp.replace(self.path)

    def put(self, job):
        job = dict(job, _id=uuid.uuid4().hex[:12], _t=int(time.time()), _tries=0)
        with self.lock:
            self.items[job["_id"]] = job
            self._save()
        self.q.put(job)

    def get(self):
        job = self.q.get()
        with self.lock:
            if job["_id"] in self.items:
                job["_tries"] += 1
                self.items[job["_id"]] = job
                self._save()
        return job

    def update(self, job, **fields):
        """Guarda datos del trabajo en curso (p.ej. el mensaje de estado)."""
        job.update(fields)
        with self.lock:
            if job["_id"] in self.items:
                self.items[job["_id"]] = job
                self._save()

    def done(self, job):
        with self.lock:
            if self.items.pop(job.get("_id"), None) is not None:
                self._save()

    def qsize(self):
        return self.q.qsize()

    def resume(self):
        """Al arrancar: (retomados, descartados). Los descartados ya no estan en la cola."""
        try:
            saved = json.loads(self.path.read_text())
        except (OSError, ValueError):
            saved = []
        now, resumed, dropped = time.time(), [], []
        with self.lock:
            for job in saved:
                if now - job.get("_t", now) > MAX_AGE or job.get("_tries", 0) >= MAX_TRIES:
                    dropped.append(job)
                    continue
                self.items[job["_id"]] = job
                resumed.append(job)
            self._save()
        for job in resumed:
            self.q.put(job)
        return resumed, dropped
