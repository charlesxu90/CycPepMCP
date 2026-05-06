"""Agent execution trace logger.

Writes one JSONL event per agent action so the agent-evaluation metrics in
docs/benchmark_plan.md section 6 can be computed offline. Schema is fixed —
do NOT add fields without bumping the schema version, or the aggregator
(`benchmark/scripts/aggregate_metrics.py`) will silently drop them.

Typical usage from a workflow runner:

    from benchmark.scripts.agent_trace import AgentTracer, ErrorType

    tracer = AgentTracer.open(
        run_id="AF_MDM2_R1_CLAUDE",
        task_id="AF_MDM2",
        llm_backend="claude",
        out_path=Path("benchmark/runs/AF_MDM2_R1_CLAUDE/agent_trace.jsonl"),
    )

    tracer.log_prompt("Design 10 cyclic binders for MDM2", token_input=120, token_output=0)

    with tracer.tool_call(
        "afcycdesign_mcp.submit_binder_design",
        input_artifact="4HFZ_MDM2.pdb",
    ) as call:
        result = mcp.submit_binder_design(...)
        call.output_artifact = f"job_{result['job_id']}"
        # context exit auto-logs the matching tool_result event with wall_time_sec.

    tracer.close()

The same event_id is reused between matching `tool_call` and `tool_result`
events so the aggregator can pair them by id.
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from time import perf_counter
from typing import Any, Optional

SCHEMA_VERSION = "1.0"


class EventType(str, Enum):
    PROMPT = "prompt"
    PLANNING = "planning"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    ERROR = "error"
    RETRY = "retry"
    USER_INTERVENTION = "user_intervention"
    CANDIDATE_FILTER = "candidate_filter"
    CANDIDATE_SCORE = "candidate_score"
    CLUSTER = "cluster"
    FINAL_REPORT = "final_report"
    TARGET_QC = "target_qc"


class Status(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    RETRY = "retry"
    PENDING = "pending"


class ErrorType(str, Enum):
    """Failure-mode taxonomy from docs/benchmark_plan.md section 6.2."""
    ENVIRONMENT = "environment"
    SCHEMA = "schema"
    RUNTIME = "runtime"
    SCIENTIFIC = "scientific"
    AGENT_DECISION = "agent_decision"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _new_event_id() -> str:
    return f"evt_{uuid.uuid4().hex[:12]}"


@dataclass
class Event:
    """One row in agent_trace.jsonl. Field set is frozen at SCHEMA_VERSION 1.0."""
    event_id: str
    run_id: str
    task_id: str
    timestamp: str
    event_type: str
    llm_backend: str
    tool_name: str = ""
    input_artifact: str = ""
    output_artifact: str = ""
    status: str = Status.SUCCESS.value
    error_type: str = ""
    token_input: int = 0
    token_output: int = 0
    wall_time_sec: float = 0.0
    user_intervention: bool = False
    notes: str = ""

    def to_jsonl(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":")) + "\n"


@dataclass
class _ToolCallContext(AbstractContextManager):
    """Returned by AgentTracer.tool_call(). Auto-logs tool_result on exit."""
    tracer: "AgentTracer"
    event_id: str
    tool_name: str
    input_artifact: str
    output_artifact: str = ""
    status: str = Status.SUCCESS.value
    error_type: str = ""
    notes: str = ""
    token_input: int = 0
    token_output: int = 0
    _t0: float = field(default_factory=perf_counter, init=False)

    def __enter__(self) -> "_ToolCallContext":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        wall = perf_counter() - self._t0
        if exc is not None:
            self.status = Status.FAILURE.value
            if not self.error_type:
                self.error_type = ErrorType.RUNTIME.value
            if not self.notes:
                self.notes = f"{exc_type.__name__}: {exc}"[:400]
        self.tracer._write_event(Event(
            event_id=self.event_id,   # paired with tool_call
            run_id=self.tracer.run_id,
            task_id=self.tracer.task_id,
            timestamp=_utc_now_iso(),
            event_type=EventType.TOOL_RESULT.value,
            llm_backend=self.tracer.llm_backend,
            tool_name=self.tool_name,
            input_artifact=self.input_artifact,
            output_artifact=self.output_artifact,
            status=self.status,
            error_type=self.error_type,
            token_input=self.token_input,
            token_output=self.token_output,
            wall_time_sec=round(wall, 4),
            user_intervention=False,
            notes=self.notes,
        ))
        return False  # do not suppress


class AgentTracer:
    """Append-only JSONL event logger. Thread-safe within a process via an internal lock.

    For multi-process safety (e.g. parallel CPU/GPU workers in run_pipeline.py),
    each worker should open its own AgentTracer pointing at a different file —
    the aggregator merges per-run files post-hoc.
    """

    def __init__(self, run_id: str, task_id: str, llm_backend: str, out_path: Path):
        self.run_id = run_id
        self.task_id = task_id
        self.llm_backend = llm_backend
        self.out_path = Path(out_path)
        self._lock = threading.Lock()
        self._fh: Optional[Any] = None
        self._n_events = 0

    @classmethod
    def open(cls, run_id: str, task_id: str, llm_backend: str, out_path: Path) -> "AgentTracer":
        t = cls(run_id, task_id, llm_backend, out_path)
        t._open()
        return t

    def _open(self) -> None:
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        # Append mode so resumed runs add to the same file.
        self._fh = self.out_path.open("a", buffering=1)  # line-buffered
        # Header row: schema version + open timestamp. Always emitted.
        self._write_event(Event(
            event_id=_new_event_id(),
            run_id=self.run_id,
            task_id=self.task_id,
            timestamp=_utc_now_iso(),
            event_type="trace_open",
            llm_backend=self.llm_backend,
            notes=f"schema_version={SCHEMA_VERSION}",
        ))

    def close(self) -> None:
        if self._fh is None:
            return
        with self._lock:
            self._write_event_locked(Event(
                event_id=_new_event_id(),
                run_id=self.run_id,
                task_id=self.task_id,
                timestamp=_utc_now_iso(),
                event_type="trace_close",
                llm_backend=self.llm_backend,
                notes=f"events_written={self._n_events}",
            ))
            self._fh.close()
            self._fh = None

    def __enter__(self) -> "AgentTracer":
        if self._fh is None:
            self._open()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.close()
        return False

    # ------------------------------------------------------------------
    # Low-level write
    # ------------------------------------------------------------------
    def _write_event_locked(self, event: Event) -> None:
        if self._fh is None:
            raise RuntimeError("AgentTracer is closed")
        self._fh.write(event.to_jsonl())
        self._n_events += 1

    def _write_event(self, event: Event) -> None:
        with self._lock:
            self._write_event_locked(event)

    # ------------------------------------------------------------------
    # Public event API
    # ------------------------------------------------------------------
    def log_prompt(self, prompt_text: str, token_input: int = 0, token_output: int = 0) -> str:
        """Log the user/system prompt that initiated a turn. Returns event_id."""
        eid = _new_event_id()
        self._write_event(Event(
            event_id=eid,
            run_id=self.run_id,
            task_id=self.task_id,
            timestamp=_utc_now_iso(),
            event_type=EventType.PROMPT.value,
            llm_backend=self.llm_backend,
            token_input=token_input,
            token_output=token_output,
            notes=prompt_text[:400],
        ))
        return eid

    def log_planning(self, plan_text: str, token_input: int = 0, token_output: int = 0) -> str:
        eid = _new_event_id()
        self._write_event(Event(
            event_id=eid,
            run_id=self.run_id,
            task_id=self.task_id,
            timestamp=_utc_now_iso(),
            event_type=EventType.PLANNING.value,
            llm_backend=self.llm_backend,
            token_input=token_input,
            token_output=token_output,
            notes=plan_text[:400],
        ))
        return eid

    def tool_call(self, tool_name: str, input_artifact: str = "", notes: str = "") -> _ToolCallContext:
        """Context manager: emits tool_call on enter, tool_result on exit (with timing)."""
        eid = _new_event_id()
        # tool_call event (open)
        self._write_event(Event(
            event_id=eid,
            run_id=self.run_id,
            task_id=self.task_id,
            timestamp=_utc_now_iso(),
            event_type=EventType.TOOL_CALL.value,
            llm_backend=self.llm_backend,
            tool_name=tool_name,
            input_artifact=input_artifact,
            status=Status.PENDING.value,
            notes=notes,
        ))
        return _ToolCallContext(
            tracer=self,
            event_id=eid,
            tool_name=tool_name,
            input_artifact=input_artifact,
        )

    def log_error(self, tool_name: str, error_type: ErrorType | str, notes: str = "") -> str:
        eid = _new_event_id()
        et = error_type.value if isinstance(error_type, ErrorType) else str(error_type)
        self._write_event(Event(
            event_id=eid,
            run_id=self.run_id,
            task_id=self.task_id,
            timestamp=_utc_now_iso(),
            event_type=EventType.ERROR.value,
            llm_backend=self.llm_backend,
            tool_name=tool_name,
            status=Status.FAILURE.value,
            error_type=et,
            notes=notes[:400],
        ))
        return eid

    def log_retry(self, tool_name: str, attempt: int, notes: str = "") -> str:
        eid = _new_event_id()
        self._write_event(Event(
            event_id=eid,
            run_id=self.run_id,
            task_id=self.task_id,
            timestamp=_utc_now_iso(),
            event_type=EventType.RETRY.value,
            llm_backend=self.llm_backend,
            tool_name=tool_name,
            status=Status.RETRY.value,
            notes=f"attempt={attempt}; {notes}"[:400],
        ))
        return eid

    def log_intervention(self, notes: str) -> str:
        """Log a moment where the agent could not proceed without human input."""
        eid = _new_event_id()
        self._write_event(Event(
            event_id=eid,
            run_id=self.run_id,
            task_id=self.task_id,
            timestamp=_utc_now_iso(),
            event_type=EventType.USER_INTERVENTION.value,
            llm_backend=self.llm_backend,
            user_intervention=True,
            notes=notes[:400],
        ))
        return eid

    def log_filter(self, n_in: int, n_pass: int, n_fail: int, reason: str = "") -> str:
        eid = _new_event_id()
        self._write_event(Event(
            event_id=eid,
            run_id=self.run_id,
            task_id=self.task_id,
            timestamp=_utc_now_iso(),
            event_type=EventType.CANDIDATE_FILTER.value,
            llm_backend=self.llm_backend,
            notes=f"n_in={n_in} n_pass={n_pass} n_fail={n_fail} reason={reason}"[:400],
        ))
        return eid

    def log_target_qc(self, pdb_path: str, ok: bool, notes: str = "") -> str:
        eid = _new_event_id()
        self._write_event(Event(
            event_id=eid,
            run_id=self.run_id,
            task_id=self.task_id,
            timestamp=_utc_now_iso(),
            event_type=EventType.TARGET_QC.value,
            llm_backend=self.llm_backend,
            input_artifact=pdb_path,
            status=Status.SUCCESS.value if ok else Status.FAILURE.value,
            notes=notes[:400],
        ))
        return eid

    def log_final_report(self, report_path: str, notes: str = "") -> str:
        eid = _new_event_id()
        self._write_event(Event(
            event_id=eid,
            run_id=self.run_id,
            task_id=self.task_id,
            timestamp=_utc_now_iso(),
            event_type=EventType.FINAL_REPORT.value,
            llm_backend=self.llm_backend,
            output_artifact=report_path,
            notes=notes[:400],
        ))
        return eid


# ----------------------------------------------------------------------
# Smoke test (run as a script)
# ----------------------------------------------------------------------

def _smoke_test() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "agent_trace.jsonl"
        tracer = AgentTracer.open(
            run_id="AF_MDM2_R1_CLAUDE",
            task_id="AF_MDM2",
            llm_backend="claude",
            out_path=out,
        )
        tracer.log_target_qc(pdb_path="4HFZ_MDM2.pdb", ok=True)
        tracer.log_prompt("design cyclic binders for MDM2", token_input=120, token_output=8)
        tracer.log_planning("call afcycdesign_mcp.submit_binder_design", token_input=200, token_output=40)

        with tracer.tool_call("afcycdesign_mcp.submit_binder_design", input_artifact="4HFZ_MDM2.pdb") as call:
            call.output_artifact = "job_abc123"
            call.notes = "ok"

        # Simulate an error then retry then success
        tracer.log_error("afcycdesign_mcp.get_job_status", ErrorType.RUNTIME, "timeout after 600s")
        tracer.log_retry("afcycdesign_mcp.get_job_status", attempt=2)
        with tracer.tool_call("afcycdesign_mcp.get_job_status", input_artifact="job_abc123") as call:
            call.output_artifact = "completed"

        tracer.log_filter(n_in=10, n_pass=7, n_fail=3, reason="iPAE>0.20")
        tracer.log_final_report("benchmark/runs/AF_MDM2_R1_CLAUDE/report.md")
        tracer.close()

        events = [json.loads(l) for l in out.read_text().splitlines()]
        types = [e["event_type"] for e in events]
        print(f"events_written: {len(events)}")
        print(f"event_types: {types}")
        # Validate paired tool_call / tool_result event_ids
        call_ids = [e["event_id"] for e in events if e["event_type"] == "tool_call"]
        result_ids = [e["event_id"] for e in events if e["event_type"] == "tool_result"]
        assert len(call_ids) == len(result_ids) == 2, f"call/result count mismatch: {len(call_ids)} vs {len(result_ids)}"
        assert call_ids == result_ids, "tool_call event_ids should match tool_result event_ids"
        # Validate timing was captured
        for e in events:
            if e["event_type"] == "tool_result":
                assert e["wall_time_sec"] >= 0.0
        # Validate fields are stable
        expected_fields = {"event_id", "run_id", "task_id", "timestamp", "event_type",
                           "llm_backend", "tool_name", "input_artifact", "output_artifact",
                           "status", "error_type", "token_input", "token_output",
                           "wall_time_sec", "user_intervention", "notes"}
        for e in events:
            assert set(e.keys()) == expected_fields, f"unexpected fields: {set(e.keys()) ^ expected_fields}"
        print("OK: agent_trace smoke test passed")


if __name__ == "__main__":
    _smoke_test()
