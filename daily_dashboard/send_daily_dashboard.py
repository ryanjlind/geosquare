#!/usr/bin/env python3
from __future__ import annotations

import html
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import requests

from app.core.db import get_conn


REPORT_HOUR_UTC = 14
ROUND_NUMBERS = (1, 2, 3, 4, 5)
RESEND_API_URL = 'https://api.resend.com/emails'
REQUEST_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class RoundMetric:
    round_number: int
    completion_count: int
    average_score: float | None


@dataclass(frozen=True)
class PeriodMetric:
    sessions: int
    completions: int


@dataclass(frozen=True)
class DashboardData:
    game_date: date
    sessions_started: int
    sessions_completed: int
    average_completed_score: float | None
    registered_users: int
    rounds: tuple[RoundMetric, ...]
    current_period: PeriodMetric
    previous_period: PeriodMetric


def _required_environment_value(name: str) -> str:
    value = os.environ[name].strip()
    if not value:
        raise ValueError(f'{name} must not be empty.')
    return value


def _target_game_date(now: datetime) -> date:
    if now.tzinfo is None:
        raise ValueError('Current time must include a timezone.')
    return now.astimezone(timezone.utc).date() - timedelta(days=1)


def _collect_dashboard_data(game_date: date) -> DashboardData:
    current_start = game_date - timedelta(days=6)
    previous_start = game_date - timedelta(days=13)
    previous_end = game_date - timedelta(days=7)

    with get_conn() as conn:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT
                COUNT(gs.SessionId) AS SessionsStarted,
                COUNT(CASE WHEN gs.CompletedAt IS NOT NULL THEN 1 END) AS SessionsCompleted,
                AVG(CASE WHEN gs.CompletedAt IS NOT NULL THEN CAST(gs.TotalScore AS float) END) AS AverageCompletedScore
            FROM dbo.Games g
            LEFT JOIN dbo.GameSessions gs
                ON gs.GameId = g.GameId
            WHERE g.GameDate = ?
            """,
            game_date,
        )
        game_row = cur.fetchone()
        if game_row is None:
            raise RuntimeError(f'No aggregate row returned for game date {game_date.isoformat()}.')

        cur.execute(
            """
            WITH RoundNumbers AS (
                SELECT RoundNumber
                FROM (VALUES (1), (2), (3), (4), (5)) AS rounds(RoundNumber)
            )
            SELECT
                rn.RoundNumber,
                COUNT(gsr.SessionRoundId) AS CompletionCount,
                AVG(CAST(gsr.Score AS float)) AS AverageScore
            FROM RoundNumbers rn
            LEFT JOIN (
                SELECT gsr.SessionRoundId, gsr.RoundNumber, gsr.Score
                FROM dbo.GameSessionRounds gsr
                INNER JOIN dbo.GameSessions gs
                    ON gs.SessionId = gsr.SessionId
                INNER JOIN dbo.Games g
                    ON g.GameId = gs.GameId
                WHERE g.GameDate = ?
                  AND gsr.RoundStatus = 'Completed'
            ) gsr
                ON gsr.RoundNumber = rn.RoundNumber
            GROUP BY rn.RoundNumber
            ORDER BY rn.RoundNumber
            """,
            game_date,
        )
        round_rows = cur.fetchall()
        if len(round_rows) != len(ROUND_NUMBERS):
            raise RuntimeError(f'Expected five round aggregates, received {len(round_rows)}.')

        cur.execute(
            """
            SELECT COUNT(*) AS RegisteredUsers
            FROM dbo.Users
            WHERE AuthProvider IS NOT NULL
            """
        )
        user_row = cur.fetchone()
        if user_row is None:
            raise RuntimeError('No registered-user aggregate row returned.')

        cur.execute(
            """
            SELECT
                COUNT(CASE WHEN g.GameDate BETWEEN ? AND ? THEN 1 END) AS CurrentSessions,
                COUNT(CASE WHEN g.GameDate BETWEEN ? AND ? AND gs.CompletedAt IS NOT NULL THEN 1 END) AS CurrentCompletions,
                COUNT(CASE WHEN g.GameDate BETWEEN ? AND ? THEN 1 END) AS PreviousSessions,
                COUNT(CASE WHEN g.GameDate BETWEEN ? AND ? AND gs.CompletedAt IS NOT NULL THEN 1 END) AS PreviousCompletions
            FROM dbo.GameSessions gs
            INNER JOIN dbo.Games g
                ON g.GameId = gs.GameId
            WHERE g.GameDate BETWEEN ? AND ?
            """,
            current_start,
            game_date,
            current_start,
            game_date,
            previous_start,
            previous_end,
            previous_start,
            previous_end,
            previous_start,
            game_date,
        )
        trend_row = cur.fetchone()
        if trend_row is None:
            raise RuntimeError('No trend aggregate row returned.')

    rounds = tuple(
        RoundMetric(
            round_number=int(row.RoundNumber),
            completion_count=int(row.CompletionCount),
            average_score=float(row.AverageScore) if row.AverageScore is not None else None,
        )
        for row in round_rows
    )

    return DashboardData(
        game_date=game_date,
        sessions_started=int(game_row.SessionsStarted),
        sessions_completed=int(game_row.SessionsCompleted),
        average_completed_score=(
            float(game_row.AverageCompletedScore)
            if game_row.AverageCompletedScore is not None
            else None
        ),
        registered_users=int(user_row.RegisteredUsers),
        rounds=rounds,
        current_period=PeriodMetric(
            sessions=int(trend_row.CurrentSessions),
            completions=int(trend_row.CurrentCompletions),
        ),
        previous_period=PeriodMetric(
            sessions=int(trend_row.PreviousSessions),
            completions=int(trend_row.PreviousCompletions),
        ),
    )


def _format_score(value: float | None) -> str:
    if value is None:
        return 'N/A'
    return f'{value:,.1f}'


def _format_rate(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return 'N/A'
    return f'{(numerator / denominator) * 100:.1f}%'


def _format_change(current: int, previous: int) -> tuple[str, str]:
    if previous == 0:
        if current == 0:
            return '0.0%', 'neutral'
        return 'New activity', 'up'

    change = ((current - previous) / previous) * 100
    if change > 0:
        return f'+{change:.1f}%', 'up'
    if change < 0:
        return f'{change:.1f}%', 'down'
    return '0.0%', 'neutral'


def _render_dashboard(data: DashboardData) -> str:
    completion_rate = _format_rate(data.sessions_completed, data.sessions_started)
    session_change, session_direction = _format_change(
        data.current_period.sessions,
        data.previous_period.sessions,
    )
    completion_change, completion_direction = _format_change(
        data.current_period.completions,
        data.previous_period.completions,
    )
    round_rows = ''.join(
        '<tr>'
        f'<td>Round {metric.round_number}</td>'
        f'<td>{metric.completion_count:,}</td>'
        f'<td>{html.escape(_format_score(metric.average_score))}</td>'
        '</tr>'
        for metric in data.rounds
    )

    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body {{ margin: 0; background: #eef2f3; color: #17312d; font-family: Georgia, "Times New Roman", serif; }}
    .shell {{ width: 100%; padding: 28px 12px; }}
    .dashboard {{ max-width: 720px; margin: 0 auto; background: #ffffff; border-top: 6px solid #e15d44; }}
    .header {{ padding: 28px 32px 20px; border-bottom: 1px solid #d9e2df; }}
    .eyebrow {{ color: #a33e2d; font-family: Arial, sans-serif; font-size: 12px; font-weight: bold; letter-spacing: 0; text-transform: uppercase; }}
    h1 {{ margin: 7px 0 3px; font-size: 30px; font-weight: normal; }}
    .date {{ color: #5f716d; font-family: Arial, sans-serif; font-size: 14px; }}
    .section {{ padding: 24px 32px; border-bottom: 1px solid #d9e2df; }}
    h2 {{ margin: 0 0 14px; font-family: Arial, sans-serif; font-size: 16px; }}
    .kpis {{ width: 100%; border-collapse: separate; border-spacing: 8px; table-layout: fixed; }}
    .kpi {{ padding: 16px; background: #f4f7f6; border-left: 4px solid #247b6b; vertical-align: top; }}
    .label {{ color: #5f716d; font-family: Arial, sans-serif; font-size: 11px; font-weight: bold; text-transform: uppercase; }}
    .value {{ margin-top: 7px; color: #17312d; font-family: Arial, sans-serif; font-size: 25px; font-weight: bold; }}
    .trend-table, .round-table {{ width: 100%; border-collapse: collapse; font-family: Arial, sans-serif; font-size: 14px; }}
    th {{ padding: 9px 10px; background: #17312d; color: #ffffff; text-align: left; }}
    td {{ padding: 10px; border-bottom: 1px solid #d9e2df; }}
    .up {{ color: #247b6b; font-weight: bold; }}
    .down {{ color: #b34432; font-weight: bold; }}
    .neutral {{ color: #5f716d; font-weight: bold; }}
    .footer {{ padding: 18px 32px 24px; color: #73827f; font-family: Arial, sans-serif; font-size: 12px; }}
    @media (max-width: 600px) {{
      .header, .section, .footer {{ padding-left: 18px; padding-right: 18px; }}
      .kpis {{ border-spacing: 4px; }}
      .kpi {{ padding: 11px 8px; }}
      .value {{ font-size: 20px; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <div class="dashboard">
      <div class="header">
        <div class="eyebrow">Daily operations</div>
        <h1>GeoSquare Dashboard</h1>
        <div class="date">Completed game: {data.game_date.strftime('%B %d, %Y')}</div>
      </div>
      <div class="section">
        <table class="kpis" role="presentation">
          <tr>
            <td class="kpi"><div class="label">Sessions</div><div class="value">{data.sessions_started:,}</div></td>
            <td class="kpi"><div class="label">Completed</div><div class="value">{data.sessions_completed:,}</div></td>
            <td class="kpi"><div class="label">Completion</div><div class="value">{completion_rate}</div></td>
          </tr>
          <tr>
            <td class="kpi"><div class="label">Avg. score</div><div class="value">{html.escape(_format_score(data.average_completed_score))}</div></td>
            <td class="kpi" colspan="2"><div class="label">Registered users</div><div class="value">{data.registered_users:,}</div></td>
          </tr>
        </table>
      </div>
      <div class="section">
        <h2>Fourteen-day trend</h2>
        <table class="trend-table">
          <thead><tr><th>Metric</th><th>Last 7 games</th><th>Previous 7</th><th>Change</th></tr></thead>
          <tbody>
            <tr><td>Sessions</td><td>{data.current_period.sessions:,}</td><td>{data.previous_period.sessions:,}</td><td class="{session_direction}">{session_change}</td></tr>
            <tr><td>Completions</td><td>{data.current_period.completions:,}</td><td>{data.previous_period.completions:,}</td><td class="{completion_direction}">{completion_change}</td></tr>
          </tbody>
        </table>
      </div>
      <div class="section">
        <h2>Round performance</h2>
        <table class="round-table">
          <thead><tr><th>Round</th><th>Completed</th><th>Average score</th></tr></thead>
          <tbody>{round_rows}</tbody>
        </table>
      </div>
      <div class="footer">Generated at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</div>
    </div>
  </div>
</body>
</html>'''


def _send_email(data: DashboardData) -> None:
    api_key = _required_environment_value('RESEND_API_KEY')
    recipient = _required_environment_value('EMAIL_RECIPIENT')
    sender = _required_environment_value('EMAIL_SENDER')
    response = requests.post(
        RESEND_API_URL,
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        },
        json={
            'from': sender,
            'to': [recipient],
            'subject': f'GeoSquare daily dashboard - {data.game_date.isoformat()}',
            'html': _render_dashboard(data),
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()


def main() -> None:
    scheduled_hour = f'{REPORT_HOUR_UTC:02d}:00 UTC'
    game_date = _target_game_date(datetime.now(timezone.utc))
    print(f'Collecting GeoSquare dashboard for {game_date.isoformat()} ({scheduled_hour} schedule)...', flush=True)
    data = _collect_dashboard_data(game_date)
    print('Dashboard metrics collected. Sending through Resend...', flush=True)
    _send_email(data)
    print('Daily dashboard sent.', flush=True)


if __name__ == '__main__':
    main()