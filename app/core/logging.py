import json
import logging
import os
import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import perf_counter

from app.constants import DEVELOPMENT_ENVIRONMENT, SLOW_EVENT_THRESHOLD_MILLISECONDS
from app.core.db import get_conn


_logger = logging.getLogger('geosquare')
_timing_stack: ContextVar[tuple['TimingNode', ...]] = ContextVar(
    'timing_stack',
    default=(),
)


@dataclass
class TimingNode:
    event_name: str
    duration_milliseconds: float = 0.0
    details: dict | None = None
    session_id: int | None = None
    children: list['TimingNode'] = field(default_factory=list)


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


def _timing_details(node: TimingNode) -> dict | None:
    if node.details is None:
        details = {}
    else:
        details = dict(node.details)
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


def _record_timing(node: TimingNode, level: int, *, emit_log: bool) -> None:
    stack = _timing_stack.get()
    if stack:
        if node.session_id is None:
            node.session_id = stack[-1].session_id
        stack[-1].children.append(node)
    details = _timing_details(node)
    if emit_log:
        _logger.log(
            level,
            '%s elapsed_ms=%.1f details=%s',
            node.event_name,
            node.duration_milliseconds,
            json.dumps(details, ensure_ascii=False),
        )
    _persist_slow_event(
        event_name=node.event_name,
        duration_milliseconds=node.duration_milliseconds,
        details=details,
        session_id=node.session_id,
    )


@contextmanager
def timing_scope(
    event_name: str,
    *,
    details: dict | None = None,
    level: int = logging.INFO,
    session_id: int | None = None,
):
    stack = _timing_stack.get()
    if session_id is None and stack:
        session_id = stack[-1].session_id
    node = TimingNode(
        event_name=event_name,
        details=details,
        session_id=session_id,
    )
    token = _timing_stack.set((*stack, node))
    started_at = perf_counter()
    try:
        yield node
    finally:
        node.duration_milliseconds = (perf_counter() - started_at) * 1000.0
        _timing_stack.reset(token)
        _record_timing(node, level, emit_log=True)


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
                details={'logger': self.name, 'message': rendered_message},
            ),
            level,
            emit_log=False,
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
    details: dict | None = None,
    level: int = logging.INFO,
) -> None:
    _record_timing(
        TimingNode(
            event_name=event_name,
            duration_milliseconds=duration_milliseconds,
            details=details,
        ),
        level,
        emit_log=True,
    )