from datetime import datetime, timezone
import os

def get_effective_game_date():
    override = os.getenv('GAME_DATE_OVERRIDE')
    if override:
        return override

    return datetime.now(timezone.utc).date().isoformat()