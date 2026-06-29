import json
import os
from datetime import datetime

LOG_PATH = '/etc/family-shield/activity.json'
MAX_ENTRIES = 100  # Keep last 100 events to avoid filling storage

def load_log():
    if not os.path.exists(LOG_PATH):
        return []
    with open(LOG_PATH) as f:
        return json.load(f)

def save_log(entries):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, 'w') as f:
        json.dump(entries, f, indent=2)

def log_event(device_name, action, detail=''):
    """
    Log a parental control event.
    action: 'paused', 'unpaused', 'blocked', 'unblocked', 'schedule_on', 'schedule_off'
    """
    entries = load_log()
    entries.insert(0, {
        "time":        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "device":      device_name,
        "action":      action,
        "detail":      detail
    })
    # Keep only the most recent MAX_ENTRIES
    entries = entries[:MAX_ENTRIES]
    save_log(entries)

def get_log():
    return load_log()

def clear_log():
    save_log([])
