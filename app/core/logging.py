import json
import logging
import os
import re
import traceback
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import perf_counter

from flask import g, has_request_context, request

from app.constants import DEVELOPMENT_ENVIRONMENT, SLOW_EVENT_THRESHOLD_MILLISECONDS
from app.core.db import get_conn


_logger = logging.getLogger('geosquare')
_timing_stack: ContextVar[tuple['TimingNode', ...]] = ContextVar(
    'timing_stack',
    default=(),
)


@dataclass
class TimingDiagnostics:
    inputs: dict = field(default_factory=dict)
    workload: dict = field(default_factory=dict)
    outcome: dict = field(default_factory=dict)
    expected: dict = field(default_factory=dict)
    actual: dict = field(default_factory=dict)
    failure: dict = field(default_factory=dict)


@dataclass
class TimingNode:
    event_name: str
    duration_milliseconds: float = 0.0
    diagnostics: TimingDiagnostics = field(default_factory=TimingDiagnostics)
    session_id: int | None = None
    children: list['TimingNode'] = field(default_factory=list)

    @property
    def inputs(self) -> dict:
        return self.diagnostics.inputs

    @property
    def workload(self) -> dict:
        return self.diagnostics.workload

    @property
    def outcome(self) -> dict:
        return self.diagnostics.outcome

    @property
    def expected(self) -> dict:
        return self.diagnostics.expected

    @property
    def actual(self) -> dict:
        return self.diagnostics.actual


def _is_local() -> bool:
    return os.getenv('FLASK_ENV') == DEVELOPMENT_ENVIRONMENT


def _write_client_event(
    *,
    event_type: str,
    details: dict | None,
    ip_address: str | None,
    user_agent: str | None,
    referer: str | None,
) -> None:
    with get_conn(for_logging=True) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO dbo.LogEvents (
                OccurredAtUtc,
                EventType,
                DetailsJson,
                IpAddress,
                UserAgent,
                Referer
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc),
                event_type,
                json.dumps(details, ensure_ascii=False),
                ip_address,
                user_agent,
                referer,
            ),
        )
        conn.commit()


def _write_backend_error(
    *,
    exception_type: str,
    message: str,
    stack_trace: str,
    request_method: str,
    request_path: str,
    endpoint: str | None,
    user_id: int | None,
    session_id: int | None,
    request_id: str,
) -> None:
    with get_conn(for_logging=True) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO dbo.BackendErrorEvents (
                OccurredAtUtc,
                ExceptionType,
                ErrorMessage,
                StackTrace,
                RequestMethod,
                RequestPath,
                Endpoint,
                UserId,
                SessionId,
                RequestId
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc),
                exception_type,
                message,
                stack_trace,
                request_method,
                request_path,
                endpoint,
                user_id,
                session_id,
                request_id,
            ),
        )
        conn.commit()


def _write_slow_event(
    *,
    event_name: str,
    duration_milliseconds: float,
    details: dict | None,
    session_id: int | None,
) -> None:
    with get_conn(for_logging=True) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO dbo.SlowEvents (
                OccurredAtUtc,
                EventName,
                DurationMilliseconds,
                DetailsJson,
                SessionId
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc),
                event_name,
                duration_milliseconds,
                json.dumps(details, ensure_ascii=False),
                session_id,
            ),
        )
        conn.commit()


def _persist_slow_event(
    *,
    event_name: str,
    duration_milliseconds: float,
    details: dict | None,
    session_id: int | None,
) -> None:
    if _is_local() or duration_milliseconds <= SLOW_EVENT_THRESHOLD_MILLISECONDS:
        return
    try:
        _write_slow_event(
            event_name=event_name,
            duration_milliseconds=duration_milliseconds,
            details=details,
            session_id=session_id,
        )
    except Exception:
        _logger.exception('Failed to write slow event to database: %s', event_name)


def _request_details() -> dict:
    if not has_request_context():
        return {}
    return {
        'request_id': g.request_id,
        'method': request.method,
        'path': request.path,
        'endpoint': request.endpoint,
        'user_id': g.user_id,
        'session_id': g.session_id,
    }


def _diagnostic_details(diagnostics: TimingDiagnostics) -> dict:
    details = {
        'inputs': diagnostics.inputs,
        'workload': diagnostics.workload,
        'outcome': diagnostics.outcome,
    }
    if diagnostics.expected:
        details['expected'] = diagnostics.expected
    if diagnostics.actual:
        details['actual'] = diagnostics.actual
    if diagnostics.failure:
        details['failure'] = diagnostics.failure
    return details


def _timing_details(node: TimingNode) -> dict | None:
    details = _diagnostic_details(node.diagnostics)
    if node.children:
        details['timings'] = [
            {
                'event_name': child.event_name,
                'duration_milliseconds': child.duration_milliseconds,
                'details': _timing_details(child),
            }
            for child in node.children
        ]
    if not details:
        return None
    return details


def _operation_timings(node: TimingNode) -> list[dict]:
    timings = [{
        'event_name': node.event_name,
        'duration_milliseconds': node.duration_milliseconds,
    }]
    for child in node.children:
        timings.extend(_operation_timings(child))
    return timings


def _persist_timing_tree(node: TimingNode, root: TimingNode) -> None:
    request_details = _request_details()
    operation_details = _diagnostic_details(root.diagnostics)
    if node is root:
        details = _timing_details(node)
        if details is None:
            details = {}
        if request_details:
            details['request'] = request_details
    else:
        details = {
            'request': request_details,
            'operation': {
                'event_name': root.event_name,
                **operation_details,
            },
            'stage': _timing_details(node),
            'operation_timings': _operation_timings(root),
        }
    session_id = node.session_id
    if session_id is None and request_details:
        session_id = request_details['session_id']
    _persist_slow_event(
        event_name=node.event_name,
        duration_milliseconds=node.duration_milliseconds,
        details=details,
        session_id=session_id,
    )
    for child in node.children:
        _persist_timing_tree(child, root)


def _record_timing(node: TimingNode) -> None:
    stack = _timing_stack.get()
    if stack:
        if node.session_id is None:
            node.session_id = stack[-1].session_id
        stack[-1].children.append(node)
    if not stack:
        _persist_timing_tree(node, node)


@contextmanager
def timing_scope(
    event_name: str,
    *,
    inputs: dict | None = None,
    workload: dict | None = None,
    expected: dict | None = None,
    actual: dict | None = None,
    level: int = logging.INFO,
    session_id: int | None = None,
):
    stack = _timing_stack.get()
    if session_id is None and stack:
        session_id = stack[-1].session_id
    diagnostics = TimingDiagnostics()
    if inputs is not None:
        diagnostics.inputs.update(inputs)
    if workload is not None:
        diagnostics.workload.update(workload)
    if expected is not None:
        diagnostics.expected.update(expected)
    if actual is not None:
        diagnostics.actual.update(actual)
    node = TimingNode(
        event_name=event_name,
        diagnostics=diagnostics,
        session_id=session_id,
    )
    token = _timing_stack.set((*stack, node))
    started_at = perf_counter()
    try:
        yield node
    except Exception as exception_value:
        node.diagnostics.failure.update({
            'exception_type': (
                f'{type(exception_value).__module__}.'
                f'{type(exception_value).__qualname__}'
            ),
            'message': str(exception_value),
        })
        raise
    finally:
        node.duration_milliseconds = (perf_counter() - started_at) * 1000.0
        _timing_stack.reset(token)
        _record_timing(node)


def _embedded_timing(message: str) -> tuple[str, float] | None:
    milliseconds_match = re.search(r'elapsed_ms=([0-9]+(?:\.[0-9]+)?)', message)
    if milliseconds_match is not None:
        return message[:milliseconds_match.start()].strip(), float(milliseconds_match.group(1))
    seconds_match = re.search(
        r'(?:took|completed in|failed after) ([0-9]+(?:\.[0-9]+)?)s',
        message,
    )
    if seconds_match is not None:
        return message[:seconds_match.start()].strip(), float(seconds_match.group(1)) * 1000.0
    return None


class UnifiedLogger:
    def __init__(self, name: str):
        self.name = name
        self._console_logger = logging.getLogger(name)

    def setLevel(self, level: int) -> None:
        self._console_logger.setLevel(level)

    def _log(self, level: int, message: str, *args, exc_info=False, **kwargs) -> None:
        self._console_logger.log(level, message, *args, exc_info=exc_info, **kwargs)
        rendered_message = message % args if args else message
        embedded_timing = _embedded_timing(rendered_message)
        if embedded_timing is None:
            return
        event_name, duration_milliseconds = embedded_timing
        _record_timing(
            TimingNode(
                event_name=event_name,
                duration_milliseconds=duration_milliseconds,
                diagnostics=TimingDiagnostics(
                    inputs={'logger': self.name},
                    outcome={'message': rendered_message},
                ),
            )
        )

    def debug(self, message: str, *args, **kwargs) -> None:
        self._log(logging.DEBUG, message, *args, **kwargs)

    def info(self, message: str, *args, **kwargs) -> None:
        self._log(logging.INFO, message, *args, **kwargs)

    def warning(self, message: str, *args, **kwargs) -> None:
        self._log(logging.WARNING, message, *args, **kwargs)

    def error(self, message: str, *args, **kwargs) -> None:
        self._log(logging.ERROR, message, *args, **kwargs)

    def exception(self, message: str, *args, **kwargs) -> None:
        self._log(logging.ERROR, message, *args, exc_info=True, **kwargs)


def get_logger(name: str) -> UnifiedLogger:
    logger = UnifiedLogger(name)
    return logger


_application_logger = get_logger('geosquare')


def debug(message: str, *args, **kwargs) -> None:
    _application_logger.debug(message, *args, **kwargs)


def info(message: str, *args, **kwargs) -> None:
    _application_logger.info(message, *args, **kwargs)


def warning(message: str, *args, **kwargs) -> None:
    _application_logger.warning(message, *args, **kwargs)


def error(message: str, *args, **kwargs) -> None:
    _application_logger.error(message, *args, **kwargs)


def exception(message: str, *args, **kwargs) -> None:
    _application_logger.exception(message, *args, **kwargs)


def backend_exception(
    exception_value: Exception,
    *,
    request_method: str,
    request_path: str,
    endpoint: str | None,
    user_id: int | None,
    session_id: int | None,
    request_id: str,
) -> None:
    exception_type = (
        f'{type(exception_value).__module__}.{type(exception_value).__qualname__}'
    )
    message = str(exception_value)
    stack_trace = ''.join(traceback.format_exception(exception_value))
    _logger.error(
        'Unhandled backend exception request_id=%s method=%s path=%s endpoint=%s '
        'user_id=%s session_id=%s',
        request_id,
        request_method,
        request_path,
        endpoint,
        user_id,
        session_id,
        exc_info=(
            type(exception_value),
            exception_value,
            exception_value.__traceback__,
        ),
    )

    if _is_local():
        return

    try:
        _write_backend_error(
            exception_type=exception_type,
            message=message,
            stack_trace=stack_trace,
            request_method=request_method,
            request_path=request_path,
            endpoint=endpoint,
            user_id=user_id,
            session_id=session_id,
            request_id=request_id,
        )
    except Exception:
        _logger.exception(
            'Failed to write backend exception to database: request_id=%s',
            request_id,
        )


def client_event(
    *,
    payload: dict,
    event_type: str,
    details: dict | None,
    ip_address: str | None,
    user_agent: str | None,
    referer: str | None,
) -> None:
    log_record = {
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'ip': ip_address,
        'user_agent': user_agent,
        'referer': referer,
        'payload': payload,
    }
    if not _is_local():
        try:
            _write_client_event(
                event_type=event_type,
                details=details,
                ip_address=ip_address,
                user_agent=user_agent,
                referer=referer,
            )
        except Exception:
            _logger.exception('Failed to write client event to database: %s', event_type)
    _logger.error(json.dumps(log_record, ensure_ascii=False))


def timing(
    event_name: str,
    duration_milliseconds: float,
    *,
    inputs: dict | None = None,
    workload: dict | None = None,
    outcome: dict | None = None,
    expected: dict | None = None,
    actual: dict | None = None,
    level: int = logging.INFO,
) -> None:
    diagnostics = TimingDiagnostics()
    if inputs is not None:
        diagnostics.inputs.update(inputs)
    if workload is not None:
        diagnostics.workload.update(workload)
    if outcome is not None:
        diagnostics.outcome.update(outcome)
    if expected is not None:
        diagnostics.expected.update(expected)
    if actual is not None:
        diagnostics.actual.update(actual)
    _record_timing(
        TimingNode(
            event_name=event_name,
            duration_milliseconds=duration_milliseconds,
            diagnostics=diagnostics,
        )
    )