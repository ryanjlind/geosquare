import base64
import os

import requests


REQUEST_TIMEOUT_SECONDS = 30
RESEND_API_URL = 'https://api.resend.com/emails'


def send_feedback_email(data, screenshots) -> None:
    diagnostics = data.get('diagnostics')
    body = f"""
Type: {data.get('type')}
Platform: {data.get('platform')}
Include Diagnostics: {data.get('includeDiagnostics')}
Allow Email: {data.get('allowEmail')}
User Email: {data.get('email')}

Description:
{data.get('description')}
"""

    if data.get('includeDiagnostics') == 'true' and diagnostics:
        body += f"""

Diagnostics:
{diagnostics}
"""

    attachments = [
        {
            'filename': screenshot.filename,
            'content': base64.b64encode(screenshot.read()).decode('ascii'),
        }
        for screenshot in screenshots
    ]

    response = requests.post(
        RESEND_API_URL,
        headers={
            'Authorization': f"Bearer {os.environ['RESEND_API_KEY']}",
            'Content-Type': 'application/json',
        },
        json={
            'from': os.environ['EMAIL_SENDER'],
            'to': [os.environ['FEEDBACK_EMAIL']],
            'subject': f"GeoSquare Feedback ({data.get('type')})",
            'text': body,
            'attachments': attachments,
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()