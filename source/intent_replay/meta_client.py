import os
from pathlib import Path
from threading import Lock
from typing import Callable

from dotenv import load_dotenv
from openai import DefaultHttpxClient, OpenAI

from intent_replay.models import APICall


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_NAME = "muse-spark-1.3"
BASE_URL = "https://api.meta.ai/v1"


class MissingAPIKeyError(RuntimeError):
    pass


class HTTPAttemptLimitError(RuntimeError):
    pass


class AttemptBudget:
    def __init__(self, limit: int):
        if limit < 0:
            raise ValueError("HTTP attempt limit must be nonnegative.")
        self.limit = limit
        self.attempts = 0
        self._lock = Lock()

    def reserve(self) -> None:
        with self._lock:
            if self.attempts >= self.limit:
                raise HTTPAttemptLimitError("HTTP attempt budget exhausted; no further request was dispatched.")
            self.attempts += 1


def create_client(timeout: float = 90.0, *, api_call: APICall | None = None, request_guard: Callable[[], None] | None = None) -> OpenAI:
    load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=True)
    api_key = os.getenv("MODEL_API_KEY", "").strip()
    if not api_key:
        raise MissingAPIKeyError(
            "MODEL_API_KEY is missing. Set it in the project-root .env file."
        )
    options = {"api_key": api_key, "base_url": BASE_URL, "timeout": timeout, "max_retries": 0}
    http_client = None
    if api_call is not None:
        def attempted(request):
            if request_guard is not None:
                request_guard()
            api_call.http_attempts += 1
            api_call.status = "attempted"

        def received(response):
            api_call.http_responses += 1
            if response.is_success:
                api_call.successful_http_responses += 1
            api_call.status = "response_received" if response.is_success else "http_error"

        http_client = DefaultHttpxClient(event_hooks={"request": [attempted], "response": [received]})
        options["http_client"] = http_client
    try:
        return OpenAI(**options)
    except Exception:
        if http_client is not None:
            http_client.close()
        raise