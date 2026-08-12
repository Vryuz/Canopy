"""Render an attestation as a standalone, shareable HTML page in the Canopy style.

This is the product surface: a URL a counterparty (a lender's underwriter, a VVB, a county
reviewer) can open and re-verify. It re-hashes the body in the page itself and shows a
PASS/FAIL integrity check, so the page proves its own tamper-evidence rather than asserting it.
"""

from __future__ import annotations

import json
from html import escape

from src.output.attestation import Attestation, _canonical

_VERDICT_CLASS = {
    "verified": "verified",
    "disputed": "disputed",
    "flagged": "flagged",
    "inconclusive": "inconclusive",
}


def render_page(att: Attestation, att_id: str) -> str:
    body = att.body
    verdict = body.get("verdict", {})
    kind = str(verdict.get("kind", "")).lower()
    vclass = _VERDICT_CLASS.get(kind, "inconclusive")

    discrepancies = body.get("discrepancies") or []
    signals = body.get("signals") or []
    evidence = body.get("evidence") or []
    gaps = body.get("data_gaps") or []
    scores = body.get("scores") or []
    p2y = body.get("path_to_yes")

    parts: list[str] = []
    parts.append(f"""<header class="topbar">
  <div class="brand">
    <a href="/" style="display:flex;align-items:center;gap:.5rem;color:inherit;text-decoration:none;border:0">
      <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2.5 14.6 7.9 7.2l3.8 4.9 3.5-3.6 6.3 7.2"/><path d="M2.5 20.6 8.7 15l3.7 3.4 4.2-3.7 4.9 5.2"/></svg>
      <b>Canopy</b>
    </a>
  </div>
  <div class="label">Attestation · {escape(att_id)}</div>
</header>
<div class="wrap att">""")

    kind_label = "Flood verification" if att.kind == "flood_verification" else "Data-center screen"
    parts.append(f"""<div class="att-head">
    <span class="label">{escape(kind_label)}</span>
    <h1 class="display">{escape(att.subject)}</h1>
    <div class="verdict"><span class="badge {vclass}">{escape(kind.upper())}</span>
      <span class="conf">confidence · {escape(str(verdict.get('confidence','')))}</span></div>
    <p class="reason">{escape(str(verdict.get('reasoning','')))}</p>
  </div>""")

    # Integrity panel — re-hashed client-side below.
    parts.append(f"""<div class="integrity" id="integrity">
    <div class="label">Tamper-evident record</div>
    <div class="hashrow"><span>sha256</span><code id="claimed-hash">{escape(att.content_hash)}</code></div>
    <div class="hashrow"><span>recomputed</span><code id="recomputed-hash">checking…</code></div>
    <div id="integrity-verdict" class="integrity-verdict">Verifying…</div>
    <div class="dim">Issued {escape(att.issued_at.isoformat())} · {escape(att.issuer)} v{escape(att.version)}</div>
  </div>""")

    if discrepancies:
        parts.append('<h3>Discrepancies</h3>')
        for d in discrepancies:
            sev = str(d.get("severity", "")).lower()
            parts.append(f"""<div class="disc sev-{escape(sev)}">
      <div class="disc-head"><span class="sev">{escape(sev.upper())}</span> <span class="mono">{escape(str(d.get('field','')))}</span></div>
      <div class="disc-vals">claimed <b>{escape(str(d.get('claimed','')))}</b> · observed <b>{escape(str(d.get('observed','')))}</b></div>
      <div>{escape(str(d.get('explanation','')))}</div>
    </div>""")

    if scores:
        parts.append('<h3>Scored dimensions</h3><div class="scores">')
        for s in scores:
            val = float(s.get("score", 0))
            cls = "good" if val >= 0.7 else "warn" if val >= 0.4 else "bad"
            parts.append(f"""<div class="score">
        <div class="score-head"><b>{escape(str(s.get('dimension','')))}</b><span class="val {cls}">{val:.2f}</span></div>
        <div class="bar"><i class="{cls}" style="width:{round(val*100)}%"></i></div>
        <div class="dim">{escape(str(s.get('rationale','')))}</div></div>""")
        parts.append("</div>")

    if p2y:
        parts.append('<h3>Path to yes</h3>')
        parts.append(f'<p class="p2y-summary">{escape(str(p2y.get("summary","")))}</p><ul class="levers">')
        for lever in sorted(p2y.get("levers", []), key=lambda x: -x.get("strength", 0)):
            val = float(lever.get("strength", 0))
            cls = "good" if val >= 0.7 else "warn" if val >= 0.4 else "bad"
            parts.append(f"""<li><div class="lever-head"><b>{escape(str(lever.get('name','')))}</b>
        <span class="val {cls}">{val:.2f}</span></div>
        <div>{escape(str(lever.get('headline','')))}</div></li>""")
        parts.append("</ul>")

    if signals:
        parts.append('<h3>Corroborating signals</h3><ul class="signals">')
        for s in signals:
            parts.append(f"""<li class="w-{escape(str(s.get('weight','')))}"><b>{escape(str(s.get('label','')))}</b> — {escape(str(s.get('detail','')))}
        <div class="dim">{escape(str(s.get('source','')))} · fetched {escape(str(s.get('fetched_at',''))[:10])}</div></li>""")
        parts.append("</ul>")

    if evidence:
        parts.append('<h3>Evidence <span class="dim">— every value carries its source</span></h3>')
        parts.append('<table><thead><tr><th>Field</th><th>Value</th><th>Source</th><th>Fetched</th><th>Conf</th></tr></thead><tbody>')
        for e in evidence:
            unit = e.get("unit")
            val = f"{e.get('value')} {unit}" if unit else str(e.get("value"))
            url = e.get("source_url")
            src = (f'<a href="{escape(str(url))}" target="_blank" rel="noopener">{escape(str(e.get("source","")))}</a>'
                   if url else f'<span class="mono">{escape(str(e.get("source","")))}</span>')
            parts.append(f'<tr><td class="mono">{escape(str(e.get("field","")))}</td><td><b>{escape(val)}</b></td>'
                         f'<td>{src}</td><td class="dim mono">{escape(str(e.get("fetched_at",""))[:10])}</td>'
                         f'<td class="dim mono">{escape(str(e.get("confidence","")))}</td></tr>')
        parts.append("</tbody></table>")

    if gaps:
        parts.append('<h3>Declared data gaps <span class="dim">— asked for, not returned</span></h3><ul class="gaps">')
        for g in gaps:
            retry = " <span class='dim'>(retryable)</span>" if g.get("retryable") else ""
            parts.append(f'<li><span class="mono">{escape(str(g.get("field","")))}</span> — {escape(str(g.get("reason","")))}{retry}</li>')
        parts.append("</ul>")

    parts.append(f"""<p class="foot-note dim">This record is self-verifying: the page recomputes the
    hash of the attestation body below and compares it to the one issued. Fetch the raw JSON at
    <a href="/a/{escape(att_id)}.json">/a/{escape(att_id)}.json</a> to re-check it yourself.</p>
  </div>""")

    # Client-side integrity check. We embed the *exact* canonical string the server hashed
    # (sorted keys, ensure_ascii, no whitespace) and sha256 it in the browser. Re-serialising
    # the body in JS instead would diverge from Python on two counts — non-ASCII escaping and
    # float formatting (1.0 vs 1) — and falsely report a mismatch. Hashing identical bytes
    # can't drift, yet still catches real tampering: edit the body and the stored hash no
    # longer matches this string.
    canonical_literal = json.dumps(_canonical(att.body))  # a JS-safe string literal
    parts.append(f"""<script>
(async () => {{
  const CANON = {canonical_literal};
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(CANON));
  const hex = [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2,'0')).join('');
  document.getElementById('recomputed-hash').textContent = hex;
  const ok = hex === document.getElementById('claimed-hash').textContent;
  const v = document.getElementById('integrity-verdict');
  v.textContent = ok ? '✓ Intact — recomputed hash matches the issued hash' : '✗ TAMPERED — hash mismatch';
  v.className = 'integrity-verdict ' + (ok ? 'intact' : 'tampered');
  document.getElementById('integrity').classList.add(ok ? 'ok' : 'bad');
}})();
</script>""")
    return "\n".join(parts)
