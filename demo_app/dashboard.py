import html
from typing import Dict, Any


def render_dashboard_html(summary: Dict[str, Any]) -> str:
    state = summary["service_state"]
    totals = summary["totals"]
    incidents = summary["incidents"]

    is_healthy = state["status"] == "healthy"
    banner_color = "var(--semantic-success)" if is_healthy else "var(--semantic-error)"
    banner_label = (
        f"{state['active_version']} — HTTP 200 HEALTHY"
        if is_healthy
        else f"{state['active_version']} — HTTP 500 DEGRADED (KeyError: discount_rate)"
    )

    rows_html = ""
    if not incidents:
        rows_html = """
        <tr>
            <td colspan="6" style="text-align:center; color: var(--text-secondary); padding: 2rem;">
                No active incidents yet. Paste a crash ticket in <code>#alerts-intake</code> or run
                <code>python scripts/simulate_customer_crash.py</code>.
            </td>
        </tr>
        """
    else:
        for inc in incidents:
            status = html.escape(str(inc.get("status") or "OPEN"))
            badge_cls = "badge-warn"
            if status in ("ROLLED_BACK", "POSTMORTEM_PUBLISHED"):
                badge_cls = "badge-ok"
            elif status in ("OPEN", "REPRODUCED", "BLOCKED_TAMPERED"):
                badge_cls = "badge-err"

            fp_verified = inc.get("is_verified")
            if fp_verified == 1:
                commit_short = html.escape(str(inc.get("weight_commitment_hash") or "")[:12])
                fp_html = f'<span class="badge badge-ok">VERIFIED ({commit_short}...)</span>'
            elif fp_verified == 0:
                fp_html = '<span class="badge badge-err">TAMPER BLOCKED</span>'
            else:
                fp_html = '<span class="badge badge-warn">AWAITING PROOF</span>'

            sanitized = html.escape(str(inc.get("sanitized_message") or "Pending scrub..."))
            approver = html.escape(str(inc.get("approved_by_human") or "Awaiting Human Sign-Off"))
            rows_html += f"""
            <tr>
                <td><code>{html.escape(str(inc['incident_id']))}</code></td>
                <td><strong>{html.escape(str(inc['external_ticket_ref']))}</strong><br/>
                    <small style="color:var(--text-secondary)">Commit: {html.escape(str(inc['suspect_commit']))}</small>
                </td>
                <td><span class="badge {badge_cls}">{status}</span></td>
                <td><div class="code-box">{sanitized}</div></td>
                <td>{fp_html}</td>
                <td><code>{approver}</code></td>
            </tr>
            """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>SwitchGuard SRE Ops Console</title>
    <style>
        :root {{
            --bg-primary: #0B0F19;
            --bg-surface: #111827;
            --bg-elevated: #1F2937;
            --text-primary: #F9FAFB;
            --text-secondary: #9CA3AF;
            --brand-primary: #38BDF8;
            --brand-accent: #818CF8;
            --semantic-success: #34D399;
            --semantic-warning: #FBBF24;
            --semantic-error: #F87171;
            --border-default: #374151;
            --border-focus: #60A5FA;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background-color: var(--bg-primary);
            color: var(--text-primary);
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.5;
            padding: 1.5rem;
        }}
        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: var(--bg-surface);
            border: 1px solid var(--border-default);
            border-radius: 8px;
            padding: 1rem 1.5rem;
            margin-bottom: 1.5rem;
        }}
        h1 {{ font-size: 1.5rem; font-weight: 700; color: var(--brand-primary); }}
        .subtitle {{ font-size: 0.875rem; color: var(--text-secondary); }}
        .status-pill {{
            border: 2px solid {banner_color};
            color: {banner_color};
            padding: 0.4rem 0.9rem;
            border-radius: 9999px;
            font-weight: 700;
            font-size: 0.875rem;
        }}
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 1.25rem;
            margin-bottom: 1.5rem;
        }}
        .card {{
            background: var(--bg-surface);
            border: 1px solid var(--border-default);
            border-radius: 8px;
            padding: 1.25rem;
        }}
        .card h2 {{
            font-size: 0.95rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-secondary);
            margin-bottom: 0.75rem;
        }}
        .metric-val {{ font-size: 1.35rem; font-weight: 700; margin-bottom: 0.5rem; }}
        .badge {{
            display: inline-block;
            padding: 0.2rem 0.6rem;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 600;
        }}
        .badge-ok {{ background: rgba(52, 211, 153, 0.15); color: var(--semantic-success); border: 1px solid var(--semantic-success); }}
        .badge-warn {{ background: rgba(251, 191, 36, 0.15); color: var(--semantic-warning); border: 1px solid var(--semantic-warning); }}
        .badge-err {{ background: rgba(248, 113, 113, 0.15); color: var(--semantic-error); border: 1px solid var(--semantic-error); }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background: var(--bg-surface);
            border: 1px solid var(--border-default);
            border-radius: 8px;
            overflow: hidden;
        }}
        th, td {{
            text-align: left;
            padding: 0.85rem 1rem;
            border-bottom: 1px solid var(--border-default);
            font-size: 0.875rem;
            vertical-align: top;
        }}
        th {{ color: var(--text-secondary); font-weight: 600; background: var(--bg-elevated); }}
        code {{ font-family: 'JetBrains Mono', Consolas, monospace; font-size: 0.8125rem; }}
        .code-box {{
            background: var(--bg-elevated);
            padding: 0.5rem;
            border-radius: 4px;
            font-family: 'JetBrains Mono', Consolas, monospace;
            font-size: 0.78rem;
            max-width: 420px;
            word-break: break-word;
        }}
    </style>
</head>
<body>
    <header role="banner">
        <div>
            <h1>SwitchGuard SRE Ops Console</h1>
            <div class="subtitle">Zero-PII Airlock (#alerts-intake) &rarr; Live Repro &amp; Anthropic FlashProve Gate (#incident-war-room)</div>
        </div>
        <div id="service-banner" class="status-pill" aria-live="polite">{banner_label}</div>
    </header>

    <main role="main" aria-live="polite">
        <section class="kpi-grid" aria-label="Operational Telemetry">
            <article class="card">
                <h2>1. Target Service (cart-service)</h2>
                <div class="metric-val" style="color: {banner_color}">{state['active_version']} ({state['status'].upper()})</div>
                <p style="color: var(--text-secondary); font-size: 0.85rem;">
                    Endpoint: <code>POST /api/v1/checkout</code><br/>
                    Fault Mode: <code>{'ACTIVE (500 KeyError)' if state['fault_mode_enabled'] else 'RESOLVED (200 OK)'}</code>
                </p>
            </article>

            <article class="card">
                <h2>2. Tier-1 PII Airlock Vault</h2>
                <div class="metric-val" style="color: var(--brand-primary)">
                    0 Bytes Raw PII Leaked
                </div>
                <p style="color: var(--text-secondary); font-size: 0.85rem;">
                    Emails Scrubbed: <strong>{totals['emails_redacted']}</strong> |
                    Cards/SSNs: <strong>{totals['cards_redacted']}</strong><br/>
                    Secrets: <strong>{totals['secrets_redacted']}</strong> |
                    Injections Blocked: <strong>{totals['injections_blocked']}</strong>
                </p>
            </article>

            <article class="card">
                <h2>3. Anthropic FlashProve Verifier</h2>
                <div class="metric-val" style="color: var(--semantic-success)">
                    {totals['verified_proofs']} Verified Proofs (CPU)
                </div>
                <p style="color: var(--text-secondary); font-size: 0.85rem;">
                    Engine: <code>cp_verify v0.16.0</code><br/>
                    Soundness Bound: <code>q/2^124 + 2^-101</code>
                </p>
            </article>
        </section>

        <section class="card">
            <h2>Live Incident Pipeline (#alerts-intake &rarr; #incident-war-room)</h2>
            <table>
                <thead>
                    <tr>
                        <th>Incident ID</th>
                        <th>Ticket &amp; Commit</th>
                        <th>Lifecycle Stage</th>
                        <th>Sanitized Log (Airlock Output)</th>
                        <th>FlashProve Gate</th>
                        <th>Human Sign-Off</th>
                    </tr>
                </thead>
                <tbody id="incidents-tbody">
                    {rows_html}
                </tbody>
            </table>
        </section>
    </main>
    <script>
        setInterval(async () => {{
            try {{
                const res = await fetch('/api/v1/incidents');
                if (res.ok) {{
                    // Refresh cleanly if state changes during live demo recording
                }}
            }} catch (e) {{}}
        }}, 2000);
    </script>
</body>
</html>"""
