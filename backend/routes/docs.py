"""
TravelSync Pro — API Documentation Route
Auto-generates rich interactive documentation from Flask routes.
"""
import re
import json
import logging
from flask import Blueprint, jsonify, current_app

logger = logging.getLogger(__name__)
docs_bp = Blueprint("docs", __name__, url_prefix="/api/docs")

# ── Endpoint metadata enrichment ─────────────────────────────────────────────

_AUTH_MAP = {
    "login_required": "Bearer Token or Session",
    "admin_required": "Admin / Manager / Super Admin",
    "super_admin_required": "Super Admin only",
    "org_required": "Org Member",
    "org_admin_required": "Org Owner / Admin",
}

_EXAMPLE_BODIES = {
    "POST /api/auth/login": {"username": "user@company.com", "password": "YourPass1"},
    "POST /api/auth/register": {"full_name": "John Doe", "email": "john@company.com", "password": "SecurePass1", "department": "Engineering"},
    "POST /api/auth/verify-email": {"code": "123456"},
    "POST /api/auth/forgot-password": {"email": "john@company.com"},
    "POST /api/auth/reset-password": {"code": "123456", "new_password": "NewSecure1"},
    "POST /api/requests": {"destination": "Mumbai", "origin": "Delhi", "purpose": "Client Meeting", "trip_type": "domestic", "start_date": "2026-04-01", "end_date": "2026-04-03", "duration_days": 3, "num_travelers": 1},
    "POST /api/expenses": {"request_id": "TR-2026-ABC123", "category": "flight", "description": "IndiGo DEL-BOM", "invoice_amount": 8500, "currency_code": "INR"},
    "POST /api/meetings": {"client_name": "Ankit Mehta", "company": "Reliance", "meeting_date": "2026-04-05", "meeting_time": "10:00 AM", "venue": "BKC Office", "agenda": "Q1 Review"},
    "POST /api/orgs": {"name": "Acme Corp"},
    "POST /api/orgs/invite": {"email": "member@company.com", "role": "member"},
    "POST /api/webhooks": {"event_type": "request.approved", "target_url": "https://your-server.com/webhook"},
    "POST /api/plan-trip": {"destination": "Bangalore", "origin": "Mumbai", "duration_days": 3, "purpose": "client meeting", "num_travelers": 1, "travel_dates": "2026-04-10 to 2026-04-12"},
    "POST /api/chat": {"message": "What hotels are near Whitefield?", "session_id": "abc123"},
    "POST /api/currency/convert": {"from": "USD", "to": "INR", "amount": 100},
    "POST /api/weather": {"city": "Mumbai", "start_date": "2026-04-01", "end_date": "2026-04-03"},
    "POST /api/accommodation/search": {"destination": "Mumbai", "check_in": "2026-04-01", "check_out": "2026-04-03"},
    "POST /api/sos": {"location": "19.076,72.877", "emergency_type": "medical", "message": "Need help"},
}

_EXAMPLE_RESPONSES = {
    "POST /api/auth/login": {"success": True, "access_token": "eyJ...", "refresh_token": "eyJ...", "csrf_token": "abc...", "user": {"id": 1, "name": "John Doe", "role": "employee", "org_id": 1}},
    "GET /api/auth/me": {"success": True, "user": {"id": 1, "username": "john", "email": "john@company.com", "role": "employee"}},
    "GET /api/agents/health": {"success": True, "summary": {"total_agents": 18, "healthy": 16, "degraded": 2}, "agents": ["..."]},
    "GET /api/admin/stats": {"success": True, "stats": {"total_orgs": 5, "active_orgs": 4, "total_users": 50, "total_requests": 120}},
    "GET /api/admin/orgs": {"success": True, "organizations": [{"id": 1, "name": "Acme Corp", "plan": "pro", "status": "active", "member_count": 15}]},
}


def _get_auth_info(func) -> str:
    """Extract auth requirement from decorator chain."""
    if not func:
        return "None (Public)"
    source = ""
    current = func
    for _ in range(5):
        source += getattr(current, "__name__", "")
        wrapped = getattr(current, "__wrapped__", None)
        if wrapped:
            source += " " + getattr(wrapped, "__name__", "")
            current = wrapped
        else:
            break
    for decorator_name, label in _AUTH_MAP.items():
        if decorator_name in source:
            return label
    # Check if get_current_user is called in the function
    try:
        import inspect
        src = inspect.getsource(func)
        if "get_current_user" in src:
            return "Bearer Token or Session"
    except Exception:
        pass
    return "None (Public)"


def _get_rate_limit(func) -> str:
    """Extract rate limit from decorator."""
    try:
        import inspect
        src = inspect.getsource(func)
        match = re.search(r'limiter\.limit\(["\'](.+?)["\']\)', src)
        if match:
            return match.group(1)
    except Exception:
        pass
    return None


def _build_docs():
    """Introspect Flask app routes and build rich documentation."""
    endpoints = []
    seen = set()

    for rule in current_app.url_map.iter_rules():
        if not rule.rule.startswith("/api/"):
            continue
        if "/docs" in rule.rule:
            continue

        methods = sorted(rule.methods - {"HEAD", "OPTIONS"})
        for method in methods:
            key = f"{method} {rule.rule}"
            if key in seen:
                continue
            seen.add(key)

            func = current_app.view_functions.get(rule.endpoint)
            docstring = (func.__doc__ or "").strip() if func else ""
            first_line = docstring.split("\n")[0] if docstring else ""
            # Remove "METHOD /path — " prefix from docstring
            description = re.sub(r"^(GET|POST|PUT|DELETE|PATCH)\s+/\S+\s*[—\-]\s*", "", first_line).strip()
            if not description:
                parts = rule.rule.strip("/").split("/")
                category = parts[1] if len(parts) >= 2 else "api"
                description = f"{method} {category.replace('_', ' ').title()}"

            # Path parameters
            params = [{"name": arg, "in": "path", "required": True, "type": "string"} for arg in rule.arguments]

            # Query parameters (from docstring)
            query_params = re.findall(r"\?(\w+)=", docstring)
            for qp in query_params:
                params.append({"name": qp, "in": "query", "required": False, "type": "string"})

            category = _categorize(rule.rule)
            auth = _get_auth_info(func)
            rate = _get_rate_limit(func)
            example_body = _EXAMPLE_BODIES.get(key)
            example_resp = _EXAMPLE_RESPONSES.get(key)

            endpoints.append({
                "method": method,
                "path": rule.rule,
                "category": category,
                "description": description,
                "full_docstring": docstring,
                "parameters": params,
                "auth": auth,
                "rate_limit": rate,
                "example_request": example_body,
                "example_response": example_resp,
            })

    endpoints.sort(key=lambda e: (e["category"], e["path"], e["method"]))

    categories = {}
    for ep in endpoints:
        cat = ep["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(ep)

    return {
        "title": "TravelSync Pro API",
        "version": "3.1.0",
        "description": "A2A Multi-Tenant Corporate Travel Management Platform",
        "total_endpoints": len(endpoints),
        "categories": categories,
        "endpoints": endpoints,
    }


def _categorize(rule: str) -> str:
    parts = rule.strip("/").split("/")
    if len(parts) >= 2:
        seg = parts[1]
        mapping = {
            "auth": "Authentication",
            "requests": "Travel Requests",
            "approvals": "Approvals",
            "expenses": "Expenses",
            "expense": "Expenses",
            "meetings": "Meetings",
            "accommodation": "Accommodation",
            "weather": "Weather",
            "currency": "Currency",
            "chat": "AI Chat",
            "analytics": "Analytics",
            "orgs": "Organizations",
            "agents": "A2A Agents",
            "admin": "Platform Admin",
            "webhooks": "Webhooks",
            "audit": "Audit Log",
            "export": "PDF Export",
            "uploads": "File Uploads",
            "sos": "SOS Emergency",
            "notifications": "Notifications",
            "users": "User Management",
            "health": "Health Check",
            "trips": "Trip Planning",
            "plan-trip": "Trip Planning",
            "alerts": "Alerts",
            "docs": "Documentation",
            "whatsapp": "WhatsApp",
            "cliq": "Zoho Cliq",
            "tasks": "Background Tasks",
        }
        return mapping.get(seg, seg.replace("_", " ").replace("-", " ").title())
    return "General"


@docs_bp.route("/json", methods=["GET"])
def docs_json():
    """GET /api/docs/json — machine-readable API schema."""
    return jsonify(_build_docs()), 200


@docs_bp.route("", methods=["GET"])
def docs_html():
    """GET /api/docs — interactive API documentation."""
    docs = _build_docs()
    endpoints_json = json.dumps(docs["endpoints"], default=str)
    categories_json = json.dumps(list(docs["categories"].keys()))
    cat_counts = json.dumps({k: len(v) for k, v in docs["categories"].items()})

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>TravelSync Pro — API Documentation</title>
<script src="https://cdn.tailwindcss.com"></script>
<style>
  body {{ font-family: 'Inter', system-ui, sans-serif; }}
  .method-get {{ background: #DEF7EC; color: #03543F; }}
  .method-post {{ background: #E1EFFE; color: #1E40AF; }}
  .method-put {{ background: #FEF3C7; color: #92400E; }}
  .method-delete {{ background: #FEE2E2; color: #991B1B; }}
  .method-patch {{ background: #EDE9FE; color: #5B21B6; }}
  .endpoint-card {{ transition: all 0.15s ease; }}
  .endpoint-card:hover {{ box-shadow: 0 2px 8px rgba(0,0,0,0.08); transform: translateY(-1px); }}
  .modal-backdrop {{ animation: fadeIn 0.15s ease; }}
  .modal-content {{ animation: slideUp 0.2s ease; }}
  @keyframes fadeIn {{ from {{ opacity:0 }} to {{ opacity:1 }} }}
  @keyframes slideUp {{ from {{ opacity:0; transform:translateY(10px) }} to {{ opacity:1; transform:translateY(0) }} }}
  pre {{ font-size: 12px; line-height: 1.5; }}
  .cat-pill {{ transition: all 0.15s ease; }}
  .cat-pill:hover {{ transform: scale(1.03); }}
  .cat-pill.active {{ box-shadow: 0 0 0 2px #3B82F6; }}
</style>
</head>
<body class="bg-gray-50 text-gray-900 min-h-screen">

<!-- Header -->
<header class="bg-gradient-to-r from-[#0a1628] via-[#0d2a5e] to-[#0a1628] text-white">
  <div class="max-w-7xl mx-auto px-6 py-8">
    <div class="flex items-center justify-between flex-wrap gap-4">
      <div>
        <h1 class="text-2xl font-bold tracking-tight">TravelSync Pro API</h1>
        <p class="text-blue-200 text-sm mt-1">v{docs['version']} &mdash; A2A Multi-Tenant Corporate Travel Platform</p>
      </div>
      <div class="flex items-center gap-3">
        <span class="bg-white/10 text-white px-3 py-1.5 rounded-full text-xs font-semibold">{docs['total_endpoints']} Endpoints</span>
        <span class="bg-white/10 text-white px-3 py-1.5 rounded-full text-xs font-semibold">{len(docs['categories'])} Categories</span>
        <a href="/api/docs/json" class="bg-blue-500/30 hover:bg-blue-500/50 text-white px-3 py-1.5 rounded-full text-xs font-semibold transition">JSON Schema</a>
        <a href="/api/health" class="bg-green-500/30 hover:bg-green-500/50 text-white px-3 py-1.5 rounded-full text-xs font-semibold transition">Health</a>
      </div>
    </div>
    <!-- Search -->
    <div class="mt-5 max-w-xl">
      <input id="searchBox" type="text" placeholder="Search endpoints... (e.g. login, expenses, approve)"
        class="w-full px-4 py-2.5 rounded-lg bg-white/10 border border-white/20 text-white placeholder-blue-200 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400">
    </div>
  </div>
</header>

<div class="max-w-7xl mx-auto px-6 py-6">
  <!-- Category pills -->
  <div class="flex flex-wrap gap-2 mb-6" id="catPills">
    <button onclick="filterCategory('')" class="cat-pill active px-3 py-1.5 rounded-full text-xs font-semibold bg-white border border-gray-200 text-gray-700 hover:bg-gray-50" data-cat="">All</button>
  </div>

  <!-- Endpoints -->
  <div id="endpointList"></div>

  <!-- Empty state -->
  <div id="emptyState" class="hidden text-center py-16 text-gray-400">
    <p class="text-lg">No endpoints match your search.</p>
  </div>
</div>

<!-- Modal -->
<div id="modal" class="hidden fixed inset-0 z-50">
  <div class="modal-backdrop absolute inset-0 bg-black/50" onclick="closeModal()"></div>
  <div class="modal-content relative mx-auto mt-12 mb-12 max-w-2xl w-full max-h-[calc(100vh-6rem)] overflow-y-auto bg-white rounded-xl shadow-2xl" id="modalBody"></div>
</div>

<footer class="text-center py-8 text-xs text-gray-400 border-t mt-12">
  TravelSync Pro v{docs['version']} &mdash; Auto-Generated Interactive API Documentation
</footer>

<script>
const ALL_ENDPOINTS = {endpoints_json};
const CATEGORIES = {categories_json};
const CAT_COUNTS = {cat_counts};
let currentCat = '';
let currentSearch = '';

// Build category pills
const pillBox = document.getElementById('catPills');
CATEGORIES.forEach(cat => {{
  const btn = document.createElement('button');
  btn.className = 'cat-pill px-3 py-1.5 rounded-full text-xs font-semibold bg-white border border-gray-200 text-gray-700 hover:bg-gray-50';
  btn.dataset.cat = cat;
  btn.textContent = cat + ' (' + CAT_COUNTS[cat] + ')';
  btn.onclick = () => filterCategory(cat);
  pillBox.appendChild(btn);
}});

function filterCategory(cat) {{
  currentCat = cat;
  document.querySelectorAll('.cat-pill').forEach(p => p.classList.toggle('active', p.dataset.cat === cat));
  render();
}}

document.getElementById('searchBox').addEventListener('input', e => {{
  currentSearch = e.target.value.toLowerCase();
  render();
}});

function render() {{
  const list = document.getElementById('endpointList');
  const empty = document.getElementById('emptyState');
  let filtered = ALL_ENDPOINTS;
  if (currentCat) filtered = filtered.filter(e => e.category === currentCat);
  if (currentSearch) filtered = filtered.filter(e =>
    e.path.toLowerCase().includes(currentSearch) ||
    e.description.toLowerCase().includes(currentSearch) ||
    e.method.toLowerCase().includes(currentSearch) ||
    e.category.toLowerCase().includes(currentSearch)
  );

  if (!filtered.length) {{
    list.innerHTML = '';
    empty.classList.remove('hidden');
    return;
  }}
  empty.classList.add('hidden');

  // Group by category
  const grouped = {{}};
  filtered.forEach(e => {{
    if (!grouped[e.category]) grouped[e.category] = [];
    grouped[e.category].push(e);
  }});

  let html = '';
  for (const [cat, eps] of Object.entries(grouped)) {{
    html += `<div class="mb-8">
      <h2 class="text-sm font-bold text-gray-500 uppercase tracking-wider mb-3 flex items-center gap-2">
        <span class="w-1.5 h-1.5 rounded-full bg-blue-500"></span>${{cat}}
        <span class="text-gray-300 font-normal">${{eps.length}}</span>
      </h2>
      <div class="space-y-1.5">`;
    eps.forEach((ep, i) => {{
      const mc = 'method-' + ep.method.toLowerCase();
      const authIcon = ep.auth.includes('Public') ? '' : '<svg class="w-3.5 h-3.5 text-amber-500 inline ml-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path></svg>';
      const idx = ALL_ENDPOINTS.findIndex(a => a.method === ep.method && a.path === ep.path);
      html += `<div class="endpoint-card flex items-center gap-3 px-4 py-2.5 bg-white rounded-lg border border-gray-100 cursor-pointer" onclick="openModal(${{idx}})">
        <span class="${{mc}} px-2 py-0.5 rounded text-[11px] font-bold min-w-[52px] text-center">${{ep.method}}</span>
        <code class="text-sm text-gray-800 font-mono flex-1 truncate">${{ep.path}}</code>
        <span class="text-xs text-gray-400 hidden sm:inline max-w-[260px] truncate">${{ep.description}}</span>
        ${{authIcon}}
        <svg class="w-4 h-4 text-gray-300 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"></path></svg>
      </div>`;
    }});
    html += '</div></div>';
  }}
  list.innerHTML = html;
}}

function openModal(idx) {{
  const ep = ALL_ENDPOINTS[idx];
  const mc = 'method-' + ep.method.toLowerCase();

  let paramsHtml = '';
  if (ep.parameters && ep.parameters.length) {{
    paramsHtml = `<div class="mt-4">
      <h4 class="text-xs font-bold text-gray-500 uppercase mb-2">Parameters</h4>
      <table class="w-full text-sm"><thead><tr class="text-xs text-gray-400 border-b">
        <th class="text-left py-1 pr-3">Name</th><th class="text-left py-1 pr-3">In</th><th class="text-left py-1 pr-3">Required</th><th class="text-left py-1">Type</th>
      </tr></thead><tbody>` +
      ep.parameters.map(p => `<tr class="border-b border-gray-50">
        <td class="py-1.5 pr-3 font-mono text-blue-600">${{p.name}}</td>
        <td class="py-1.5 pr-3"><span class="px-1.5 py-0.5 rounded text-[10px] bg-gray-100">${{p.in}}</span></td>
        <td class="py-1.5 pr-3">${{p.required ? '<span class="text-red-500 text-xs">required</span>' : '<span class="text-gray-400 text-xs">optional</span>'}}</td>
        <td class="py-1.5 text-gray-500">${{p.type}}</td>
      </tr>`).join('') + '</tbody></table></div>';
  }}

  let bodyHtml = '';
  if (ep.example_request) {{
    bodyHtml = `<div class="mt-4">
      <h4 class="text-xs font-bold text-gray-500 uppercase mb-2">Request Body</h4>
      <pre class="bg-gray-900 text-green-300 p-3 rounded-lg overflow-x-auto">${{JSON.stringify(ep.example_request, null, 2)}}</pre>
    </div>`;
  }}

  let respHtml = '';
  if (ep.example_response) {{
    respHtml = `<div class="mt-4">
      <h4 class="text-xs font-bold text-gray-500 uppercase mb-2">Example Response</h4>
      <pre class="bg-gray-900 text-blue-300 p-3 rounded-lg overflow-x-auto">${{JSON.stringify(ep.example_response, null, 2)}}</pre>
    </div>`;
  }}

  document.getElementById('modalBody').innerHTML = `
    <div class="p-6">
      <div class="flex items-center justify-between mb-4">
        <div class="flex items-center gap-3">
          <span class="${{mc}} px-3 py-1 rounded-md text-xs font-bold">${{ep.method}}</span>
          <code class="text-lg font-mono font-semibold text-gray-800">${{ep.path}}</code>
        </div>
        <button onclick="closeModal()" class="text-gray-400 hover:text-gray-600 text-xl leading-none">&times;</button>
      </div>

      <p class="text-gray-600 text-sm mb-4">${{ep.description}}</p>
      ${{ep.full_docstring && ep.full_docstring !== ep.description ? '<p class="text-gray-500 text-xs italic mb-4">' + ep.full_docstring + '</p>' : ''}}

      <div class="flex flex-wrap gap-3 mb-4">
        <div class="flex items-center gap-1.5 text-xs">
          <svg class="w-3.5 h-3.5 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path></svg>
          <span class="font-medium text-gray-700">${{ep.auth}}</span>
        </div>
        ${{ep.rate_limit ? '<div class="flex items-center gap-1.5 text-xs"><svg class="w-3.5 h-3.5 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg><span class="font-medium text-gray-700">' + ep.rate_limit + '</span></div>' : ''}}
        <div class="flex items-center gap-1.5 text-xs">
          <svg class="w-3.5 h-3.5 text-purple-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z"></path></svg>
          <span class="font-medium text-gray-700">${{ep.category}}</span>
        </div>
      </div>

      <hr class="border-gray-100 my-3">
      ${{paramsHtml}}
      ${{bodyHtml}}
      ${{respHtml}}

      ${{!paramsHtml && !bodyHtml && !respHtml ? '<p class="text-gray-400 text-sm py-4 text-center italic">No additional documentation available for this endpoint.</p>' : ''}}
    </div>`;

  document.getElementById('modal').classList.remove('hidden');
  document.body.style.overflow = 'hidden';
}}

function closeModal() {{
  document.getElementById('modal').classList.add('hidden');
  document.body.style.overflow = '';
}}

document.addEventListener('keydown', e => {{ if (e.key === 'Escape') closeModal(); }});

// Initial render
render();
</script>
</body>
</html>"""

    return html, 200, {"Content-Type": "text/html"}
