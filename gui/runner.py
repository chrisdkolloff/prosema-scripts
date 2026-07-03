"""Background job execution with stdout capture."""

from __future__ import annotations

import contextlib
import io
import threading
from collections.abc import Callable
from typing import Any

from gui.job_spec import JobSpec, RunResult, coerce_params, validate_params


class JobRunner:
    """Runs a job on a background thread and reports results via callbacks."""

    def __init__(
        self,
        on_log: Callable[[str], None],
        on_success: Callable[[RunResult, str], None],
        on_error: Callable[[str], None],
        on_finished: Callable[[], None],
    ):
        self._on_log = on_log
        self._on_success = on_success
        self._on_error = on_error
        self._on_finished = on_finished
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def run(self, job: JobSpec, raw_params: dict[str, Any]) -> None:
        if self._running:
            return
        self._running = True
        thread = threading.Thread(
            target=self._execute,
            args=(job, raw_params),
            daemon=True,
        )
        thread.start()

    def _execute(self, job: JobSpec, raw_params: dict[str, Any]) -> None:
        try:
            params = coerce_params(job, raw_params)
            validate_params(job, params)
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                result = job.run(params)
            captured = buffer.getvalue().strip()
            self._on_success(result, captured)
        except FileNotFoundError as e:
            self._on_error(str(e))
        except PermissionError as e:
            self._on_error(str(e))
        except (ValueError, OverflowError) as e:
            self._on_error(f"Abbruch: {e}")
        except Exception as e:
            self._on_error(f"Unerwarteter Fehler: {e}")
        finally:
            self._running = False
            self._on_finished()
