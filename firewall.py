import subprocess

# ── nftables helpers ──────────────────────────────────────────────────────────

def run(cmd):
    subprocess.run(cmd, shell=True, capture_output=True)

def ensure_chain():
    """Make sure our family-shield chain exists in nftables."""
    # Create table and chain if they don't exist
    run("nft add table inet family_shield 2>/dev/null")
    run("nft add chain inet family_shield forward { type filter hook forward priority 0 \\; } 2>/dev/null")

def rule_exists(mac):
    result = subprocess.run(
        "nft list chain inet family_shield forward",
        shell=True, capture_output=True, text=True
    )
    return mac.lower() in result.stdout.lower()

# ── Public API ────────────────────────────────────────────────────────────────

def pause_device(mac):
    """Block all forwarded traffic from this MAC address."""
    ensure_chain()
    if not rule_exists(mac):
        run(f'nft add rule inet family_shield forward ether saddr {mac} drop')

def unpause_device(mac):
    """Remove the block rule for this MAC address."""
    ensure_chain()
    # Get the handle of the rule and delete it
    result = subprocess.run(
        "nft -a list chain inet family_shield forward",
        shell=True, capture_output=True, text=True
    )
    for line in result.stdout.splitlines():
        if mac.lower() in line.lower() and 'handle' in line:
            handle = line.strip().split('handle')[-1].strip()
            run(f"nft delete rule inet family_shield forward handle {handle}")
            break

def get_paused_devices():
    """Return list of currently blocked MACs."""
    result = subprocess.run(
        "nft list chain inet family_shield forward",
        shell=True, capture_output=True, text=True
    )
    paused = []
    for line in result.stdout.splitlines():
        if 'ether saddr' in line and 'drop' in line:
            parts = line.strip().split()
            for i, p in enumerate(parts):
                if p == 'saddr' and i + 1 < len(parts):
                    paused.append(parts[i + 1].lower())
    return paused
