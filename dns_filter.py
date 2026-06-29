import os
import json
import subprocess

BLOCKLIST_DIR  = '/etc/family-shield/blocklists'
DNSMASQ_CONF   = '/etc/dnsmasq.d/family-shield.conf'
DEVICE_DNS_MAP = '/etc/family-shield/dns_rules.json'
CUSTOM_DOMAINS_PATH = '/etc/family-shield/custom_domains.json'
CUSTOM_CATEGORIES_PATH = '/etc/family-shield/custom_categories.json'

# Categories with their blocklist source URLs
AVAILABLE_CATEGORIES = [
    {"id": "social",   "label": "Social Media",    "icon": "📱"},
    {"id": "gaming",   "label": "Online Gaming",   "icon": "🎮"},
]

# Simple built-in domain lists (no download needed)
BUILTIN_DOMAINS = {
    "social": [
        "facebook.com", "instagram.com", "tiktok.com", "snapchat.com",
        "twitter.com", "x.com", "reddit.com", "discord.com",
    ],
    "gaming": [
        "roblox.com", "fortnite.com", "steampowered.com", "epicgames.com",
        "minecraft.net", "leagueoflegends.com", "valorant.com",
    ],
    "ads": [
        "doubleclick.net", "googleadservices.com", "googlesyndication.com",
        "adnxs.com", "adsrvr.org", "moatads.com", "scorecardresearch.com",
    ],
}

# ── Custom domains helpers ────────────────────────────────────────────────────

def load_custom_domains():
    if not os.path.exists(CUSTOM_DOMAINS_PATH):
        return {}
    with open(CUSTOM_DOMAINS_PATH) as f:
        return json.load(f)

def save_custom_domains(data):
    os.makedirs(os.path.dirname(CUSTOM_DOMAINS_PATH), exist_ok=True)
    with open(CUSTOM_DOMAINS_PATH, 'w') as f:
        json.dump(data, f, indent=2)

def load_custom_categories():
    if not os.path.exists(CUSTOM_CATEGORIES_PATH):
        return []
    with open(CUSTOM_CATEGORIES_PATH) as f:
        return json.load(f)

def save_custom_categories(data):
    os.makedirs(os.path.dirname(CUSTOM_CATEGORIES_PATH), exist_ok=True)
    with open(CUSTOM_CATEGORIES_PATH, 'w') as f:
        json.dump(data, f, indent=2)

def add_custom_category(cat_id, label, icon):
    cats = load_custom_categories()
    if not any(c['id'] == cat_id for c in cats):
        cats.append({"id": cat_id, "label": label, "icon": icon})
        save_custom_categories(cats)

def remove_custom_category(cat_id):
    cats = load_custom_categories()
    cats = [c for c in cats if c['id'] != cat_id]
    save_custom_categories(cats)
    # Also remove its domains
    data = load_custom_domains()
    if cat_id in data:
        del data[cat_id]
        save_custom_domains(data)
    rebuild_dnsmasq_conf()

def get_all_categories():
    """Return builtin + custom categories."""
    custom = load_custom_categories()
    return AVAILABLE_CATEGORIES + custom

def add_custom_domain(category, domain):
    data = load_custom_domains()
    if category not in data:
        data[category] = []
    domain = domain.lower().strip().replace('https://', '').replace('http://', '').replace('www.', '').split('/')[0]
    if domain not in data[category]:
        data[category].append(domain)
    save_custom_domains(data)
    rebuild_dnsmasq_conf()

def remove_custom_domain(category, domain):
    data = load_custom_domains()
    # Track removed builtin domains in a special key
    removed_key = f"__removed_{category}"
    if domain in BUILTIN_DOMAINS.get(category, []):
        if removed_key not in data:
            data[removed_key] = []
        if domain not in data[removed_key]:
            data[removed_key].append(domain)
    elif category in data and domain in data[category]:
        data[category].remove(domain)
    save_custom_domains(data)
    rebuild_dnsmasq_conf()

def get_all_domains():
    """Return builtin + custom domains per category, respecting removals."""
    custom = load_custom_domains()
    all_cats = get_all_categories()
    result = {}
    for cat in all_cats:
        cid = cat['id']
        removed_key = f"__removed_{cid}"
        removed = custom.get(removed_key, [])
        builtin = [d for d in BUILTIN_DOMAINS.get(cid, []) if d not in removed]
        extra   = custom.get(cid, [])
        result[cid] = {'builtin': builtin, 'custom': extra}
    return result

# ── DNS rules helpers ─────────────────────────────────────────────────────────

def load_dns_rules():
    if not os.path.exists(DEVICE_DNS_MAP):
        return {}
    with open(DEVICE_DNS_MAP) as f:
        return json.load(f)

def save_dns_rules(rules):
    os.makedirs(os.path.dirname(DEVICE_DNS_MAP), exist_ok=True)
    with open(DEVICE_DNS_MAP, 'w') as f:
        json.dump(rules, f, indent=2)

# ── Build dnsmasq config from all device rules ────────────────────────────────

def rebuild_dnsmasq_conf():
    """
    dnsmasq can't block per-device natively, so we block a domain globally
    if ANY device has it blocked. For per-device blocking, iptables DNS
    redirection would be needed — keeping it simple for now.
    """
    rules = load_dns_rules()

    # Collect all blocked categories across all devices
    all_blocked = set()
    for mac, categories in rules.items():
        for cat in categories:
            all_blocked.add(cat)

    os.makedirs(os.path.dirname(DNSMASQ_CONF), exist_ok=True)
    lines = ["# Generated by Family Shield — do not edit manually\n"]

    custom = load_custom_domains()
    for cat in all_blocked:
        removed_key = f'__removed_{cat}'
        removed = custom.get(removed_key, [])
        builtin_domains = [d for d in BUILTIN_DOMAINS.get(cat, []) if d not in removed]
        custom_domains  = custom.get(cat, [])
        all_domains     = list(dict.fromkeys(builtin_domains + custom_domains))  # merge, no duplicates
        lines.append(f"# Category: {cat}")
        for domain in all_domains:
            lines.append(f"address=/{domain}/0.0.0.0")  # block IPv4
            lines.append(f"address=/{domain}/::")         # block IPv6

    with open(DNSMASQ_CONF, 'w') as f:
        f.write('\n'.join(lines) + '\n')

    # Reload dnsmasq
    subprocess.Popen("/etc/init.d/dnsmasq stop && sleep 1 && /etc/init.d/dnsmasq start", shell=True)

# ── Public API ────────────────────────────────────────────────────────────────

def set_blocked_categories(mac, categories):
    rules = load_dns_rules()
    rules[mac] = categories
    save_dns_rules(rules)
    rebuild_dnsmasq_conf()

def get_blocked_categories(mac):
    rules = load_dns_rules()
    return rules.get(mac, [])
