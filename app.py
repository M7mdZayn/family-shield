from flask import Flask, jsonify, request, send_from_directory
from devices import get_devices, update_device, sync_devices, delete_device
from firewall import pause_device, unpause_device, get_paused_devices
from scheduler import set_schedule, get_schedules, clear_schedule
from dns_filter import set_blocked_categories, get_blocked_categories, AVAILABLE_CATEGORIES, add_custom_domain, remove_custom_domain, get_all_domains, add_custom_category, remove_custom_category, get_all_categories, load_custom_categories
import os
from logger import log_event, get_log, clear_log

app = Flask(__name__, static_folder='../frontend', static_url_path='')

# ── Frontend ──────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('../frontend', 'index.html')

# ── Devices ───────────────────────────────────────────────────────────────────

@app.route('/api/devices', methods=['GET'])
def api_get_devices():
    sync_devices()
    return jsonify(get_devices())

@app.route('/api/devices/<mac>', methods=['PATCH'])
def api_update_device(mac):
    data = request.json
    update_device(mac, data)
    return jsonify({"status": "ok"})

@app.route('/api/devices/<mac>', methods=['DELETE'])
def api_delete_device(mac):
    unpause_device(mac)
    clear_schedule(mac)
    set_blocked_categories(mac, [])
    delete_device(mac)
    return jsonify({"status": "deleted"})

# ── Pause / Unpause ───────────────────────────────────────────────────────────

@app.route('/api/devices/<mac>/pause', methods=['POST'])
def api_pause(mac):
    pause_device(mac)
    update_device(mac, {"paused": True})
    devices = get_devices()
    d = next((x for x in devices if x['mac'] == mac), None)
    log_event(d['name'] if d else mac, 'paused', 'Internet access paused')
    return jsonify({"status": "paused"})

@app.route('/api/devices/<mac>/unpause', methods=['POST'])
def api_unpause(mac):
    unpause_device(mac)
    update_device(mac, {"paused": False})
    devices = get_devices()
    d = next((x for x in devices if x['mac'] == mac), None)
    log_event(d['name'] if d else mac, 'unpaused', 'Internet access restored')
    return jsonify({"status": "unpaused"})

# ── Schedules ─────────────────────────────────────────────────────────────────

@app.route('/api/devices/<mac>/schedule', methods=['POST'])
def api_set_schedule(mac):
    data = request.json
    set_schedule(mac, data.get('block_from'), data.get('block_until'), data.get('enabled', True))
    update_device(mac, {"schedule": data})
    devices = get_devices()
    d = next((x for x in devices if x['mac'] == mac), None)
    name = d['name'] if d else mac
    if data.get('enabled'):
        log_event(name, 'schedule_on', f"Schedule set: {data.get('block_from')} - {data.get('block_until')}")
    else:
        log_event(name, 'schedule_off', 'Schedule disabled')
    return jsonify({"status": "ok"})

# ── DNS Filtering ─────────────────────────────────────────────────────────────

@app.route('/api/devices/<mac>/categories', methods=['POST'])
def api_set_categories(mac):
    data = request.json
    categories = data.get('categories', [])
    set_blocked_categories(mac, categories)
    update_device(mac, {"blocked_categories": categories})
    devices = get_devices()
    d = next((x for x in devices if x['mac'] == mac), None)
    name = d['name'] if d else mac
    if categories:
        log_event(name, 'blocked', f"Categories blocked: {', '.join(categories)}")
    else:
        log_event(name, 'unblocked', 'All content filters removed')
    return jsonify({"status": "ok"})

# ── Summary stats for dashboard ───────────────────────────────────────────────

@app.route('/api/summary', methods=['GET'])
def api_summary():
    sync_devices()
    devices = get_devices()
    online    = [d for d in devices if d.get('online')]
    paused    = [d for d in devices if d.get('paused')]
    protected = [d for d in devices if d.get('paused') or d.get('blocked_categories') or d.get('schedule', {}).get('enabled')]
    return jsonify({
        "total":     len(devices),
        "online":    len(online),
        "paused":    len(paused),
        "protected": len(protected),
    })

# ── Custom Domains ────────────────────────────────────────────────────────────

@app.route('/api/domains', methods=['GET'])
def api_get_domains():
    return jsonify(get_all_domains())

@app.route('/api/domains/<category>', methods=['POST'])
def api_add_domain(category):
    data = request.json
    domain = data.get('domain', '').strip()
    if not domain:
        return jsonify({"error": "No domain provided"}), 400
    add_custom_domain(category, domain)
    return jsonify({"status": "ok"})

@app.route('/api/domains/<category>/<path:domain>', methods=['DELETE'])
def api_remove_domain(category, domain):
    remove_custom_domain(category, domain)
    return jsonify({"status": "ok"})

# ── Custom Categories ────────────────────────────────────────────────────────

@app.route('/api/categories', methods=['GET'])
def api_get_all_categories():
    return jsonify(get_all_categories())

@app.route('/api/categories', methods=['POST'])
def api_add_category():
    data = request.json
    cat_id = data.get('id', '').strip().lower().replace(' ', '_')
    label  = data.get('label', '').strip()
    icon   = data.get('icon', '📁').strip()
    if not cat_id or not label:
        return jsonify({"error": "id and label required"}), 400
    add_custom_category(cat_id, label, icon)
    return jsonify({"status": "ok"})

@app.route('/api/categories/<cat_id>', methods=['DELETE'])
def api_remove_category(cat_id):
    remove_custom_category(cat_id)
    return jsonify({"status": "ok"})

# ── Activity Log ──────────────────────────────────────────────────────────────

@app.route('/api/activity', methods=['GET'])
def api_activity():
    return jsonify(get_log())

@app.route('/api/activity/clear', methods=['POST'])
def api_clear_activity():
    clear_log()
    return jsonify({"status": "cleared"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
