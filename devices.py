import json
import os
import subprocess
from datetime import datetime

DB_PATH = '/etc/family-shield/devices.json'

# ── JSON helpers ──────────────────────────────────────────────────────────────

def load_db():
    if not os.path.exists(DB_PATH):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        save_db({})
    with open(DB_PATH) as f:
        return json.load(f)

def save_db(data):
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with open(DB_PATH, 'w') as f:
        json.dump(data, f, indent=2)

# ── Live device detection ─────────────────────────────────────────────────────

def read_dhcp_leases():
    """Read currently leased devices from dnsmasq."""
    devices = {}
    try:
        with open('/tmp/dhcp.leases') as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 4:
                    mac = parts[1].lower()
                    ip  = parts[2]
                    name = parts[3] if parts[3] != '*' else None
                    devices[mac] = {'ip': ip, 'hostname': name}
    except FileNotFoundError:
        pass
    return devices

def read_arp_table():
    """Read ARP table to catch devices not in DHCP leases."""
    devices = {}
    try:
        with open('/proc/net/arp') as f:
            next(f)  # skip header
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 4 and parts[3] != '00:00:00:00:00:00':
                    ip  = parts[0]
                    mac = parts[3].lower()
                    devices[mac] = {'ip': ip, 'hostname': None}
    except FileNotFoundError:
        pass
    return devices

def get_live_devices():
    """Merge DHCP leases + ARP into one dict keyed by MAC."""
    live = read_arp_table()
    live.update(read_dhcp_leases())  # DHCP takes priority (has hostnames)
    return live

# ── Sync live → JSON db ───────────────────────────────────────────────────────

def sync_devices():
    """Auto-register any new devices seen on the network, skipping hidden ones."""
    live = get_live_devices()
    db   = load_db()
    changed = False
    for mac, info in live.items():
        if mac not in db:
            db[mac] = {
                "name": info.get('hostname') or 'Unknown Device',
                "profile": "Unassigned",
                "paused": False,
                "hidden": False,
                "blocked_categories": [],
                "schedule": {
                    "enabled": False,
                    "block_from": None,
                    "block_until": None
                }
            }
            changed = True
        if mac in db and not db[mac].get("hidden", False):
            db[mac]["last_seen"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            changed = True
    # Update last_seen for all currently online devices
    for mac in live:
        if mac in db and not db[mac].get("hidden", False):
            db[mac]["last_seen"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            changed = True
    if changed:
        save_db(db)

# ── Public API ────────────────────────────────────────────────────────────────

def get_devices():
    """Return merged list of live + stored device data for the frontend, skipping hidden."""
    live = get_live_devices()
    db   = load_db()

    all_macs = set(db.keys()) | set(live.keys())
    result = []
    for mac in all_macs:
        stored = db.get(mac, {
            "name": live.get(mac, {}).get('hostname') or 'Unknown Device',
            "profile": "Unassigned",
            "paused": False,
            "hidden": False,
            "blocked_categories": [],
            "schedule": {"enabled": False, "block_from": None, "block_until": None}
        })
        # Skip hidden devices
        if stored.get('hidden', False):
            continue
        entry = {
            "mac": mac,
            "ip": live.get(mac, {}).get('ip', '—'),
            "online": mac in live,
            **stored
        }
        result.append(entry)

    # Sort: online first, then by name
    result.sort(key=lambda d: (not d['online'], d['name'].lower()))
    return result

def update_device(mac, fields):
    """Update stored fields for a device."""
    db = load_db()
    if mac not in db:
        db[mac] = {
            "name": "Unknown Device",
            "profile": "Unassigned",
            "paused": False,
            "blocked_categories": [],
            "schedule": {"enabled": False, "block_from": None, "block_until": None}
        }
    db[mac].update(fields)
    save_db(db)

def delete_device(mac):
    """Hide a device from the dashboard. Keeps it in JSON so it stays hidden if it reconnects."""
    db = load_db()
    if mac in db:
        db[mac]['hidden'] = True
    else:
        # Device only seen live, not yet in db — add it as hidden
        db[mac] = {
            "name": "Unknown Device",
            "profile": "Unassigned",
            "paused": False,
            "hidden": True,
            "blocked_categories": [],
            "schedule": {"enabled": False, "block_from": None, "block_until": None}
        }
    save_db(db)
