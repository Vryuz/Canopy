# Canopy — live demo runbook

The submission demo, scripted. Follow this exactly and it takes ~2 minutes to run through the
full arc: **macro finding → live verification → verifiable trust → batch product**.

The demo is designed so nothing hits a slow network on stage — the two-command warm-up below
makes every canned coordinate serve from disk.

---

## Setup (once, before you present)

```bash
python scripts/warm_demo.py
```

That pre-runs every canned example in the UI against Mireye + OpenFEMA + OSM Overpass and
stashes the responses in `.cache/`. Takes ~2 minutes and burns ~200 credits, once.

Then start the server in **cache-only replay** mode:

```bash
CANOPY_CACHE_ONLY=1 python -m uvicorn api.server:app --port 8000
```

In this mode any missed cache raises loudly — so you'll find out **before** the audience
does. Open <http://localhost:8000> and confirm the hero renders. You're ready.

**If you want to run some coordinates live** (e.g. an audience-suggested address), start the
server without `CANOPY_CACHE_ONLY`. The canned coordinates still serve from the warm cache;
new ones hit the network with the usual latencies (5–15s Mireye; 20s max Overpass).

---

## The demo — four beats, ~2 min

### Beat 1 · Macro finding (~30s)

Open **`/map`**. The stranded-half map is on screen.

**Talk track:**
> "We ran Canopy against every OSM-mapped US data center — 1,824 buildings, 1,154 campuses.
> The red dots are physically excellent sites now inside an active local moratorium's blast
> radius. **500 of them, 43%.** That's Google, AWS, QTS, Flexential, Digital Realty — not
> fringe. Hover any dot for the site, verdict, coordinates."

*(hover a Virginia dot → tooltip shows Google Lockbourne / DISPUTED / stranded 0.95)*

> "Two commercial sources fused for this map: Mireye for the physical ground truth,
> Moratorium Nation for the enacted local bans. Neither alone catches what the pair does."

### Beat 2 · Live verification (~40s)

Click **"Verification demo →"** in the top-right, then the **Carbon project** tab.
The example is prefilled: *avoided deforestation, protecting intact forest* at 47.8, -123.5.

Click **Verify claim**. (Serves from cache; ~200ms.)

**Talk track:**
> "A carbon credit is a claim. This one says: I'm protecting intact forest, pay me for it.
> Canopy checks the parcel against Mireye's vegetation ground truth and OSM's protected-area
> status. Watch the verdict."

*(page renders DISPUTED, critical, protected_areas)*

> "That parcel sits inside **Olympic National Park and a designated Wilderness**. Land under
> legal protection would have been conserved regardless — you cannot be paid to prevent a
> loss the law already prevents. Six sources fused; the discrepancy is unmissable."

### Beat 3 · Verifiable trust (~30s)

Click the **Attestation /a/…** link under the result. New tab opens.

**Talk track:**
> "Every verdict is a shareable, self-verifying attestation. The URL is the first 12 hex of
> the content hash, so the address itself is a commitment. See ✓ Intact — the browser just
> recomputed the sha256 and matched it to the issued hash."

*(open the JSON link, edit one character in `reasoning`, save, refresh)*

> "Tamper with anything…"

*(page now shows ✗ TAMPERED, red)*

> "…and any counterparty sees it. This is the product: not our verdict, but a re-checkable
> record they can trust without trusting us."

### Beat 4 · The batch product (~20s)

Back to the demo. Click the **Portfolio** tab. Click **Load Ashburn hedge-fund sample**,
then **Verify portfolio**.

**Talk track:**
> "That was one address. This is what a lender's underwriting desk actually does — screen
> the whole book. Four workers in parallel; results stream as they land. Every row lands
> with its own attestation link they can forward to counsel."

*(watch the meter climb; ten rows land in ~8 seconds from the warm cache)*

> "That's Canopy. Three domains — flood, carbon, data centers — one verification engine,
> one shareable trust surface."

---

## Contingencies (what if X breaks live)

| Symptom | Fix |
|---|---|
| **A canned query hangs** | `CANOPY_CACHE_ONLY` wasn't set, or the cache wasn't warmed. Stop, run the two setup commands, restart. |
| **`/map` shows "No scan data yet"** | `findings/campuses.json` missing. Run `python -m src.cli scan --limit 20` for a fast partial (or the full scan takes ~20 min). |
| **Attestation link 404s** | `data/attestations/` was cleared. Just run the verification again — the new attestation lands and its link works. |
| **Overpass 502/timeout in the carbon tab** | Overpass mirrors are flaky; a warm cache dodges it. If live, the carbon page will show a declared data gap on `protected_areas` and still return a verdict — that's designed behaviour, not a crash. |
| **A commercial source (Mireye) errors** | Server returns a `502` with the Mireye error. The tab shows a red error block. Rerun after 10s or switch to a different coordinate. |

---

## What you don't need to say (unless asked)

- **Costs.** A full site screen is ~27 credits (~2.5¢). A verify is ~10 credits. The full
  national scan was ~49k credits, one-shot.
- **Freshness.** The cache TTL is 30 days by default; moratoria shift quarterly, which is
  the natural re-screen cadence.
- **The engine.** `agent.py` holds zero domain knowledge; a vertical supplies (which fields
  to pull, how to read a claim, what counts as a contradiction). Adding a vertical is one file.
- **The Wave-3 thesis.** Data centers as verifiable good neighbors, not just consumers. The
  path-to-yes lever on every DC verdict (grid flexibility / district heat / water offset) is
  the community-benefit reframe.
