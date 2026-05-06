"""LLM-agnostic invocation layer for the CycPepMCP agent benchmark.

Three production backends — Claude (Anthropic), GPT (OpenAI), Gemini (Google) —
plus a Mock backend for tests/dry-runs. Configuration is read from
`benchmark/configs/llm_backends.yaml` (single source of truth, locked W1).

Each backend exposes the same `call()` signature and returns the same
`LLMResponse`, so the workflow runner can invoke any LLM identically. Token
usage is taken from the SDK's reported usage fields whenever available — that
is what gets recorded in `agent_trace.jsonl` for the benchmark.

Conditional imports: an SDK is only imported when its backend is requested,
so a benchmark machine that has only the Anthropic SDK installed can still
run the Claude leg without OpenAI/Google packages present.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Optional

from benchmark.configs import thresholds as cfg


@dataclass
class LLMResponse:
    """Uniform response shape across backends."""
    text: str
    token_input: int
    token_output: int
    backend: str
    model_id: str
    latency_sec: float
    raw: Any = None  # backend-specific raw response, kept for debugging


# ----------------------------------------------------------------------
# Backend base class
# ----------------------------------------------------------------------

class LLMBackend:
    """Common interface. Concrete subclasses must implement `call()`."""
    name: str = ""
    model_id: str = ""
    timeout_seconds: int = 600
    max_retries: int = 3
    temperature: float = 0.2
    max_output_tokens: int = 8192

    def __init__(self, name: str, config: dict[str, Any], common: dict[str, Any]):
        self.name = name
        self.model_id = config["model_id"]
        self.api_key_env = config["api_key_env"]
        self.timeout_seconds = int(common.get("timeout_seconds", self.timeout_seconds))
        self.max_retries = int(common.get("max_retries", self.max_retries))
        self.temperature = float(common.get("temperature", self.temperature))
        self.max_output_tokens = int(common.get("max_output_tokens", self.max_output_tokens))

    def _api_key(self) -> str:
        key = os.environ.get(self.api_key_env)
        if not key:
            raise RuntimeError(
                f"missing API key: set ${self.api_key_env} for backend {self.name!r}"
            )
        return key

    def call(self, *, prompt: str, system: Optional[str] = None) -> LLMResponse:
        raise NotImplementedError


# ----------------------------------------------------------------------
# Concrete backends
# ----------------------------------------------------------------------

class ClaudeBackend(LLMBackend):
    """Anthropic Claude via the official `anthropic` SDK."""

    def __init__(self, name: str, config: dict[str, Any], common: dict[str, Any]):
        super().__init__(name, config, common)
        try:
            import anthropic  # noqa: F401
        except ImportError as e:
            raise RuntimeError(
                "ClaudeBackend requires `anthropic` SDK; install with `pip install anthropic`"
            ) from e
        from anthropic import Anthropic
        self._client = Anthropic(api_key=self._api_key(), timeout=self.timeout_seconds)

    def call(self, *, prompt: str, system: Optional[str] = None) -> LLMResponse:
        t0 = time.perf_counter()
        kwargs = dict(
            model=self.model_id,
            max_tokens=self.max_output_tokens,
            temperature=self.temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        if system:
            kwargs["system"] = system
        resp = self._client.messages.create(**kwargs)
        latency = time.perf_counter() - t0
        # Extract text from the first text content block.
        text_parts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
        text = "".join(text_parts)
        usage = getattr(resp, "usage", None)
        return LLMResponse(
            text=text,
            token_input=getattr(usage, "input_tokens", 0) if usage else 0,
            token_output=getattr(usage, "output_tokens", 0) if usage else 0,
            backend=self.name,
            model_id=self.model_id,
            latency_sec=round(latency, 4),
            raw=resp,
        )


class OpenAIBackend(LLMBackend):
    """OpenAI via the official `openai` SDK (>=1.0)."""

    def __init__(self, name: str, config: dict[str, Any], common: dict[str, Any]):
        super().__init__(name, config, common)
        try:
            import openai  # noqa: F401
        except ImportError as e:
            raise RuntimeError(
                "OpenAIBackend requires `openai` SDK; install with `pip install openai`"
            ) from e
        from openai import OpenAI
        self._client = OpenAI(api_key=self._api_key(), timeout=self.timeout_seconds, max_retries=self.max_retries)

    def call(self, *, prompt: str, system: Optional[str] = None) -> LLMResponse:
        t0 = time.perf_counter()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = self._client.chat.completions.create(
            model=self.model_id,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_output_tokens,
        )
        latency = time.perf_counter() - t0
        text = resp.choices[0].message.content or ""
        usage = getattr(resp, "usage", None)
        return LLMResponse(
            text=text,
            token_input=getattr(usage, "prompt_tokens", 0) if usage else 0,
            token_output=getattr(usage, "completion_tokens", 0) if usage else 0,
            backend=self.name,
            model_id=self.model_id,
            latency_sec=round(latency, 4),
            raw=resp,
        )


class GeminiBackend(LLMBackend):
    """Google Gemini via `google-generativeai`."""

    def __init__(self, name: str, config: dict[str, Any], common: dict[str, Any]):
        super().__init__(name, config, common)
        try:
            import google.generativeai as genai  # noqa: F401
        except ImportError as e:
            raise RuntimeError(
                "GeminiBackend requires `google-generativeai` SDK; install with "
                "`pip install google-generativeai`"
            ) from e
        import google.generativeai as genai
        genai.configure(api_key=self._api_key())
        self._genai = genai
        self._gen_config = genai.types.GenerationConfig(
            temperature=self.temperature,
            max_output_tokens=self.max_output_tokens,
        )

    def call(self, *, prompt: str, system: Optional[str] = None) -> LLMResponse:
        t0 = time.perf_counter()
        model = self._genai.GenerativeModel(
            model_name=self.model_id,
            system_instruction=system,
            generation_config=self._gen_config,
        )
        resp = model.generate_content(prompt, request_options={"timeout": self.timeout_seconds})
        latency = time.perf_counter() - t0
        text = resp.text if hasattr(resp, "text") else ""
        # Gemini reports usage on resp.usage_metadata
        meta = getattr(resp, "usage_metadata", None)
        return LLMResponse(
            text=text,
            token_input=getattr(meta, "prompt_token_count", 0) if meta else 0,
            token_output=getattr(meta, "candidates_token_count", 0) if meta else 0,
            backend=self.name,
            model_id=self.model_id,
            latency_sec=round(latency, 4),
            raw=resp,
        )


class MockBackend(LLMBackend):
    """Deterministic mock for tests/dry-runs (no API key, no network)."""

    def __init__(self, name: str = "mock", config: Optional[dict[str, Any]] = None, common: Optional[dict[str, Any]] = None):
        cfg_d = config or {"model_id": "mock-1.0", "api_key_env": "MOCK_KEY_NOT_NEEDED"}
        common_d = common or {"temperature": 0.2, "max_output_tokens": 8192}
        # Skip the env-key check in the parent __init__.
        self.name = name
        self.model_id = cfg_d["model_id"]
        self.api_key_env = cfg_d["api_key_env"]
        self.temperature = float(common_d.get("temperature", 0.2))
        self.max_output_tokens = int(common_d.get("max_output_tokens", 8192))
        self.timeout_seconds = 60
        self.max_retries = 0

    def call(self, *, prompt: str, system: Optional[str] = None) -> LLMResponse:
        # Deterministic: tokens = whitespace-split lengths.
        token_input = len((system or "").split()) + len(prompt.split())
        text = f"[mock:{self.model_id}] echo: {prompt[:200]}"
        token_output = len(text.split())
        return LLMResponse(
            text=text,
            token_input=token_input,
            token_output=token_output,
            backend=self.name,
            model_id=self.model_id,
            latency_sec=0.001,
            raw=None,
        )


# ----------------------------------------------------------------------
# Factory
# ----------------------------------------------------------------------

_BACKEND_CLASSES = {
    "anthropic": ClaudeBackend,
    "openai": OpenAIBackend,
    "google": GeminiBackend,
}


def make_backend(name: str, *, mock: bool = False) -> LLMBackend:
    """Build a backend by its name in `llm_backends.yaml`.

    Args:
        name: one of the keys under `backends:` in llm_backends.yaml
              (currently 'claude', 'gpt', 'gemini').
        mock: if True, return a MockBackend pretending to be the requested backend.
              Useful for dry-runs and CI smoke tests.
    """
    backends = cfg.llm_backends()
    if name not in backends:
        raise KeyError(f"unknown backend {name!r}; expected one of {list(backends)}")
    backend_cfg = backends[name]
    common = _load_common_params()

    if mock:
        return MockBackend(
            name=name,
            config={"model_id": backend_cfg["model_id"], "api_key_env": backend_cfg["api_key_env"]},
            common=common,
        )

    provider = backend_cfg["provider"]
    cls = _BACKEND_CLASSES.get(provider)
    if cls is None:
        raise KeyError(f"unknown provider {provider!r} for backend {name!r}")
    # Per-backend overrides (timeout, retries) live under sdk_specific_overrides.
    overrides = _load_sdk_overrides().get(name, {})
    common_for_this_backend = {**common, **overrides}
    return cls(name=name, config=backend_cfg, common=common_for_this_backend)


def _load_common_params() -> dict[str, Any]:
    raw = cfg._load_llm_backends().get("common_generation_params", {})
    # system_prompt_source is a template path, not an SDK kwarg — strip it here.
    return {k: v for k, v in raw.items() if k != "system_prompt_source"}


def _load_sdk_overrides() -> dict[str, dict[str, Any]]:
    return cfg._load_llm_backends().get("sdk_specific_overrides", {}) or {}


def list_grid_tasks() -> list[tuple[str, str]]:
    """Return [(workflow, task_id), ...] for the 9-task LLM-comparison grid."""
    grid = cfg.llm_grid()
    return [(wf, t) for wf, ts in grid.items() for t in ts]


# ----------------------------------------------------------------------
# Smoke test
# ----------------------------------------------------------------------

def _smoke_test() -> None:
    # 1. Mock backend works without any SDK or API key.
    mock_claude = make_backend("claude", mock=True)
    resp = mock_claude.call(prompt="design an MDM2 binder", system="you are a helpful assistant")
    assert resp.text.startswith("[mock:")
    assert resp.token_input > 0 and resp.token_output > 0
    assert resp.backend == "claude"
    print(f"mock claude: backend={resp.backend} model={resp.model_id} "
          f"tin={resp.token_input} tout={resp.token_output} latency={resp.latency_sec}s")

    mock_gpt = make_backend("gpt", mock=True)
    mock_gemini = make_backend("gemini", mock=True)
    for b in (mock_gpt, mock_gemini):
        r = b.call(prompt="hello", system=None)
        assert r.token_input > 0
        print(f"mock {b.name}: model={b.model_id} tin={r.token_input} tout={r.token_output}")

    # 2. Factory rejects unknown backend.
    try:
        make_backend("nonexistent")
    except KeyError as e:
        print(f"OK: unknown backend rejected: {e}")
    else:
        raise AssertionError("expected KeyError for unknown backend")

    # 3. 9-task grid is well-formed.
    grid = list_grid_tasks()
    assert len(grid) == 9, f"expected 9 grid tasks, got {len(grid)}"
    workflows = {wf for wf, _ in grid}
    assert workflows == {"afcycdesign", "rfpeptides", "helmgpt"}
    print(f"OK: llm_grid has 9 tasks across {len(workflows)} workflows")

    print("OK: llm_orchestrator smoke test passed")


if __name__ == "__main__":
    _smoke_test()
