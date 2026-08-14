# Canopy — end-to-end demo script

Full narration, start to finish, against the live deployment:
**https://canopy-rkm5.onrender.com**

Written to be read (or paraphrased) as a presenter would explain the product to someone
seeing it cold — not just a click list. Total run time ~4–5 minutes at a natural pace,
including the real network waits.

**One thing to know going in:** every number and every verdict below is what the agent
computed live against real federal data — no scripted responses, no canned answers. When a
step says "wait ~15 seconds," that's an honest live call to Mireye, OpenFEMA, or OpenStreetMap,
not a loading animation. Say so on camera; it's a feature of the product, not a delay to hide.

---

## 0 · Before you record

Open the URL once yourself, about a minute before you start. Render's free tier sleeps after
15 minutes idle, so this wakes it and means your recording starts from a warm server, not a
30-second cold spinner.

```
https://canopy-rkm5.onrender.com/healthz
```
Should return `{"ok":true,"mireye_mode":"live"}` almost instantly. If it takes ~30s, that's the
cold start — wait it out before you hit record.

---

## 1 · Open on the hook (10–15s)

Land on `https://canopy-rkm5.onrender.com/`.

> "Mireye gives you cited facts about any US location — terrain, hazards, utilities, land
> cover. This is Canopy, an agent built on top of it that answers a harder question: someone
> *told* you something about a place — a seller, a developer, a carbon registry. Is it true?
> Canopy checks the claim against Mireye plus an independent second source, and tells you
> where they disagree."

---

## 2 · Why this is an agent, not a website (15–20s)

Stay on the homepage; point at the three tabs (Flood, Carbon, Data center) and the Portfolio
tab.

> "This isn't a lookup tool. It reasons — it diffs a claim against multiple sources and weighs
> the contradictions by severity. It decides — every check ends in VERIFIED, DISPUTED, FLAGGED,
> or INCONCLUSIVE, with a confidence score that's capped by how much evidence it actually got
> back, not just asserted. And it acts — it mints a cited, tamper-evident record of its own
> decision. Reason, decide, act. That's the whole rubric this had to satisfy, and you're about
> to watch all three happen live."

---

## 3 · The macro finding — `/map` (~40s)

Navigate to `/map`.

> "Before we run a single check, here's what happens when you point this agent at an entire
> industry. Mireye's own blog talks about screening thousands of meat-processing plants in an
> afternoon — so we did the same thing to data centers. Every OpenStreetMap-tagged data center
> in the US: 1,824 buildings, rolled up to 1,154 real campuses."

Let the stats settle — you'll see live: **500 disputed (43%) · 541 verified · 113 flagged.**

> "Red is a physically excellent site now sitting inside an active local permitting
> moratorium — the community said no, even though the land itself is perfect. Forty-three
> percent. And this isn't fringe operators — the reddest dots are Google, Amazon, QTS,
> Flexential."

Click **"▶ Guided tour"**. It opens on Ashburn, Virginia.

> "Ashburn — the data-center capital of the world, and Mireye's own example coordinate.
> Flawless on every engineering axis Mireye measures, and disputed on the two things that never
> show up on a site plan: an air-quality nonattainment zone, and five active county moratoria
> within 80 kilometers."

Press `2` then `3` on the keyboard to step through Columbus (worst permitting score in the
sample — the market Mireye's own blog recommends *fleeing to*) and Phoenix (clean on
moratoria, but the weakest externalities score — water and heat risk instead of politics).
Press `Escape` to close the tour.

---

## 4 · The mechanism — one live verification (~45–60s)

Click **"Verification demo →"** top right. You land back on `/`, Flood tab active.

> "That map is the *what*. Now the *how* — watching the agent actually reason, live, against
> one address."

Switch to the **Carbon project** tab. The example is prefilled: `47.8, -123.5`, claim
*"avoided deforestation, protecting intact forest."*

> "A carbon credit is a claim: I'm protecting this forest, pay me for it. That's exactly the
> shape of claim this engine is built to check."

Click **Verify claim**. It's a real call — say so, and let it run.

> "This is live — it's fetching vegetation ground truth from Mireye and cross-referencing
> protected-area status from OpenStreetMap. Give it about fifteen seconds."

When it resolves: **DISPUTED**, critical severity, citing that the parcel sits inside Olympic
National Park and a designated Wilderness area.

> "The claim fails — not because the forest isn't there, but because it's already protected by
> law. You can't be paid to prevent a loss that's already prevented. Two independent sources —
> Mireye's vegetation data and OpenStreetMap's protected-area boundaries — combined to catch
> something neither alone would have."

*(Optional, if you want to show breadth rather than just depth: switch to the Flood tab, click
the "Galveston coastal" example, run it, and let a second DISPUTED verdict land — Zone AE,
mandatory flood insurance, cited against FEMA. Two verticals, thirty extra seconds, reinforces
that this generalizes rather than being a one-trick check.)*

---

## 5 · The trust layer — attestations (~30–40s)

On the result you just produced, scroll to the **Attestation `/a/…`** link and click it. Opens
in the same tab or a new one.

> "Every verdict this agent reaches gets minted as its own page — a permanent, shareable
> record. And it doesn't ask you to trust us on that."

Point at the integrity panel — it should read **✓ Intact — recomputed hash matches the issued
hash.**

> "The page just recomputed the sha-256 hash of this record, in your browser, right now, and
> compared it to the one that was issued. If a single character of this verdict had been
> altered, that check fails and says so — visibly, in red. Nobody has to take our word for it."

Point at the **Copy link** and **Share on X** buttons.

> "And it's portable — this is a URL a lender's underwriter, a carbon verifier, or a county
> reviewer can open and re-check independently."

---

## 6 · Scale — the Portfolio tab (~30s)

Back on `/`, click the **Portfolio** tab. Click **"Load Ashburn hedge-fund sample,"** then
**Verify portfolio**.

> "One address is a lookup. This is the actual use case — an underwriting desk with a stack of
> addresses to clear this week. Same engine, run in parallel across a whole book."

Let rows stream in — expect this to take longer than a demo video usually would, since it's
live network calls per row, not a canned animation. Narrate over the wait if needed.

> "Every row that lands gets its own verdict and its own attestation link, same as the single
> check we just watched. This is the agent doing the underwriter's afternoon in a few minutes."

---

## 7 · Optional close — the resumable execution (~25s)

If you have time, navigate to `/scan/resume-ui` (linked from the `/map` nav).

> "One more thing worth showing, because it's the part that's easy to miss: that 1,824-site
> national scan is credit-metered and takes a while, so it checkpoints every completed site to
> disk as it goes. Kill it halfway through, and it resumes exactly where it stopped — nothing
> re-billed, nothing re-screened."

Click **"Resume 5 sites →"**. Watch it genuinely screen five more real sites and append them.

> "That's not a UI trick — it just called the same scan function again, and it picked up
> exactly where the checkpoint left off. The state lives in the file, not in any one running
> process."

---

## 8 · Close (10–15s)

> "Three verticals, one engine, real federal data, a verdict you don't have to trust blindly.
> Flood disclosures for lenders, data-center siting for developers, carbon credits for
> verification bodies — all built on the same primitive: check the claim, cite the evidence,
> attest to the result. That's Canopy."

---

## Contingencies

| Symptom | What to do |
|---|---|
| A step is taking longer than the estimate above | Normal — these are real live calls. Keep narrating; don't panic-refresh. |
| `/map` shows "No scan data yet" | The committed `findings/campuses.json` should always ship with the repo; if this happens the deploy is stale — redeploy from Render's dashboard. |
| An attestation link 404s | Render's free tier has no persistent disk — if the service slept and cold-started between minting the link and clicking it, the record is gone. Just re-run the verify; a fresh link will work within the same session. |
| A live call errors (502) | Upstream (Mireye/OpenFEMA/Overpass) hiccup. Wait ~10s, retry the same example. |
| The whole site feels sluggish on first load | Cold start — see step 0. Always warm it before recording. |

## What you don't need to explain unless asked

- **Cost**: a single verify is roughly 10–30 Mireye credits; the full national scan was a
  one-time ~49k-credit run, already banked in `findings/`.
- **Why Render, why it sleeps**: free-tier tradeoff, documented in `render.yaml`'s comments.
- **The 10-year thesis**: this demo is the Mireye-challenge submission, not the pitch for the
  company beyond it — that lives in the local-only `COMPANY_THESIS.md` if it comes up in Q&A.
