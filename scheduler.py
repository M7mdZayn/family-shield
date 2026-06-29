import subprocess
from firewall import pause_device, unpause_device

# ── Cron helpers ──────────────────────────────────────────────────────────────

def get_crontab():
    result = subprocess.run("crontab -l", shell=True, capture_output=True, text=True)
    return result.stdout if result.returncode == 0 else ""

def set_crontab(content):
    proc = subprocess.run("crontab -", input=content, shell=True, text=True, capture_output=True)

def remove_device_crons(mac):
    """Remove any existing cron entries for this device."""
    lines = get_crontab().splitlines()
    tag = f"# family-shield:{mac}"
    filtered = [l for l in lines if tag not in l]
    set_crontab('\n'.join(filtered) + '\n')

def time_to_cron(time_str):
    """Convert 'HH:MM' to cron minute/hour fields."""
    h, m = time_str.split(':')
    return f"{int(m)} {int(h)}"

# ── Public API ────────────────────────────────────────────────────────────────

def set_schedule(mac, block_from, block_until, enabled=True):
    """
    Set a daily schedule for a device.
    block_from / block_until are 'HH:MM' strings.
    """
    remove_device_crons(mac)
    if not enabled or not block_from or not block_until:
        return

    tag = f"# family-shield:{mac}"
    cron_block   = time_to_cron(block_from)
    cron_unblock = time_to_cron(block_until)

    # Build cron lines using nftables directly
    pause_cmd   = f"nft add rule inet family_shield forward ether saddr {mac} drop"
    unpause_cmd = f"nft delete rule inet family_shield forward handle $(nft -a list chain inet family_shield forward | grep {mac} | grep -o 'handle [0-9]*' | awk '{{print $2}}') 2>/dev/null; true"

    block_line   = f"{cron_block} * * * {pause_cmd}   {tag}"
    unblock_line = f"{cron_unblock} * * * {unpause_cmd} {tag}"

    current = get_crontab().rstrip('\n')
    new_crontab = current + f"\n{block_line}\n{unblock_line}\n"
    set_crontab(new_crontab)

def get_schedules():
    """Return all family-shield cron entries."""
    lines = get_crontab().splitlines()
    return [l for l in lines if '# family-shield:' in l]

def clear_schedule(mac):
    """Remove schedule for a device."""
    remove_device_crons(mac)
