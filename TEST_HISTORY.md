# Test History — search_catalog testbed

Ledger of evaluation runs for the `search_catalog` pipeline. Record each run with the **exact configuration** that produced it plus the **deltas** vs. the previous run so we don't repeat experiments.

All runs use `use_cases.json` (33 tests, 11 use-case groups, 1 run per test unless noted). Precision/recall are macro-averaged over the 23 tests that have a non-empty `expected_present` (the 10 "no-results" tests are excluded from P/R; they still count toward success_rate).

Artifacts live under `deployment/testbeds/search_catalog/results/all_<timestamp>.{json,log}`.

---

## Run index

| # | Timestamp | Commit / state | Model | Retr. success | Retr. P / R / MRR | Pres. success | Pres. P / R / MRR | Latency (mean) |
|---|-----------|-----------------|-------|---------------|-------------------|---------------|-------------------|----------------|
| 1 | 2026-04-21 12:27 | pre-dual-layer runner | qwen2.5:7b | — | — | 36.4% | — / — / 0.556 | 120 s |
| 2 | 2026-04-21 16:58 | `4ab3eee` (baseline) | qwen2.5:7b | 21.2% | 0.517 / 0.692 / 0.370 | **51.5%** | **0.659 / 0.592** / 0.389 | 143 s |
| 3 | 2026-04-22 16:00 | retrieval-only, gate=0.35 / fallback=30 | (no LLM) | 12.1% | 0.367 / 0.899 / 0.704 | n/a | n/a | 57 s |
| 4 | 2026-04-22 18:11 | gate=0.35 / fallback=30 / hub filter removed / softened prompt | qwen2.5:7b | 3.0% | 0.299 / 0.957 / 0.670 | 33.3% | 0.612 / 0.581 / 0.667 | 180 s |
| 5 | 2026-04-22 20:51 | gate=0.40 / fallback=20 / hybrid prompt / elbow cut≥1 | qwen2.5:7b | 24.2% | 0.631 / 0.708 / 0.481 | 48.5% | 0.623 / 0.557 / 0.500 | 150 s |
| 6 | 2026-04-22 22:42 | same + elbow cut≥2 (no single-outlier cutoff) | qwen2.5:7b | 24.2% | 0.561 / 0.714 / 0.370 | **51.5%** | **0.652 / 0.562** / 0.444 | 142 s |
| 7 | 2026-04-23 15:11 | softer VALIDATE + strict combined-content + bilingual expansions | qwen2.5:7b | 3.0% | 0.308 / 0.811 / 0.593 | 39.4% | 0.582 / **0.636** / **0.667** | 159 s |

Retrieval P / R in run #2 were recomputed post-hoc using `compute_precision_recall` from the current `run_use_case.py` (the file snapshot did not contain those fields).

---

## Run 1 — 2026-04-21 12:27 (`all_20260421-122755`)

**State:** single-layer runner (no retrieval-vs-presentation split). Commit at time of run: `26c29c7` (pre-`e5339de`).

**Config:** `_COSINE_GATE=0.40`, `_FALLBACK_TOP_N=10`, z-score/hub filter **active** (`_MAX_Z_SCORE=2.0`). Strict filter prompt (validate + hard-constraint).

**Results:** success 36.4% (12/33), MRR 0.556, latency 120 s mean.

**Notes:** baseline before the dual-layer metrics landed. Not directly comparable to later runs on precision/recall.

---

## Run 2 — 2026-04-21 16:58 (`all_20260421-165856`) ⭐ baseline

**State:** commit `4ab3eee` ("Model-agnostic prompts, v0–v2 snapshots, dual-layer testbed metrics"). Hub filter had already been removed in the prior commit `e5339de`.

**Config:**
- Tool: `_COSINE_GATE=0.40`, `_FALLBACK_TOP_N=10`, `_MIN_GAP_RATIO=0.30`, **no** hub filter (z-score logged only), elbow-at-position-1 allowed.
- Prompt: v1/v2 strict filter (validate + hard-constraint, reject on any unmet qualifier).

**Results:**
- **Presentation:** success **51.5%** (17/33), precision 0.659, recall 0.592, MRR 0.389.
- **Retrieval:** success 21.2% (7/33), precision 0.517, recall 0.692, MRR 0.370.
- Latency: mean 143 s, max 198 s.

**Reading:**
- Best presentation success so far. Tool returns ~half of relevant assets, LLM adds precision but drops some recall (filters too hard on a few cases).
- Low retrieval success is driven by strict `unexpected=X` check — the tool sometimes returns correct+adjacent assets together.

**This is the reference baseline. All later runs should be compared against it.**

---

## Run 3 — 2026-04-22 16:00 (`all_20260422-160007`) — retrieval-only

**State:** first run after lowering gate and widening fallback, using `--retrieval-only` (no LLM).

**Changes vs. Run 2:**
- Tool: `_COSINE_GATE` 0.40 → **0.35**; `_FALLBACK_TOP_N` 10 → **30**; position-1 elbow now skipped.
- (No prompt change — LLM not used in this run.)

**Results (retrieval layer only):**
- Success 12.1% (4/33), precision 0.367, recall 0.899, MRR 0.704, latency 57 s.

**Deltas vs. Run 2 (retrieval layer):**
- Success: 21.2% → 12.1% (**worse** — wider fallback introduces unexpected assets that break the strict check).
- Precision: 0.517 → 0.367 (**worse** by −0.15).
- Recall: 0.692 → 0.899 (**better** by +0.21).
- MRR: 0.370 → 0.704 (**better** — relevant assets rank higher on average).

**Reading:** recall/MRR gain is real but comes at a large precision cost. Loosening the gate/fallback hurt precision and binary success, but the extra candidates admitted by the wider net do include more of the true positives.

---

## Run 4 — 2026-04-22 18:11 (`all_20260422-181133`) — full pipeline, softened prompt

**State:** same tool config as Run 3, plus prompt softening.

**Changes vs. Run 3:**
- Prompt: softened `VALIDATE` ("partial relevance is NOT a reason to discard") and loosened combined-content rule ("keep best partial matches and flag them") — active `search_catalog_prompt.py` and `versions/v2/search_catalog_prompt.py`.

**Results:**
- **Presentation:** success 33.3% (11/33), precision 0.612, recall 0.581, MRR 0.667.
- **Retrieval:** success 3.0% (1/33), precision 0.299, recall 0.957, MRR 0.670.
- Latency: mean 180 s, max 313 s.

**Deltas vs. Run 2 (baseline):**

| Metric | Run 2 | Run 4 | Δ |
|---|---|---|---|
| Pres. success | 51.5% | 33.3% | **−18.2 pp** |
| Pres. precision | 0.659 | 0.612 | −0.048 |
| Pres. recall | 0.592 | 0.581 | −0.011 |
| Pres. MRR | 0.389 | 0.667 | +0.278 |
| Retr. success | 21.2% | 3.0% | **−18.2 pp** |
| Retr. precision | 0.517 | 0.299 | **−0.218** |
| Retr. recall | 0.692 | 0.957 | **+0.265** |
| Retr. MRR | 0.370 | 0.670 | +0.300 |
| Latency mean | 143 s | 180 s | +37 s |

**Reading:**
- **Regressed:** presentation success, both precisions, retrieval success, latency.
- **Improved:** both MRRs, retrieval recall, presentation recall (marginal).
- Cause: tool became more permissive (gate lowered, fallback tripled, elbow-at-1 skipped) so it floods the LLM with candidates. Strict `unexpected=X` testbed checks penalise the extra FPs, and even with a softened prompt the LLM can't recover the lost precision. MRR improves because the right assets still rank high — they're just now accompanied by 10–20 extras.

**Conclusion:** combined changes (prompt softening **and** tool loosening) regressed against the baseline. Next step is to revert the tool constants / filter and attempt each change in isolation.

---

## Run 5 — 2026-04-22 20:51 (`all_20260422-205154`) — baseline gate + wider fallback + hybrid prompt

**Changes vs. Run 4:**
- Tool: gate 0.35 → **0.40** (reverted to baseline); fallback 30 → **20**; no hub filter (unchanged from Run 3–4).
- Prompt: VALIDATE re-hardened (strict baseline wording); only the combined-content rule softened ("each retained asset may cover partially one of them" instead of "must cover ALL"). Added partial-match output note and multi-asset aggregation line. Added language rule.
- Elbow cutoff: applied at `cut >= 1` (position-0 gap only excluded — a single-outlier at position 0 with a cut at 1 was still allowed).

**Results:**
- **Presentation:** success **48.5%** (16/33), precision 0.623, recall 0.557, MRR 0.500.
- **Retrieval:** success 24.2% (8/33), precision 0.631, recall 0.708, MRR 0.481.
- Latency: mean 150 s, max 462 s.

**Deltas vs. Run 2 (baseline):**

| Metric | Run 2 | Run 5 | Δ |
|---|---|---|---|
| Pres. success | 51.5% | 48.5% | −3.0 pp |
| Pres. precision | 0.659 | 0.623 | −0.036 |
| Pres. recall | 0.592 | 0.557 | −0.035 |
| Pres. MRR | 0.389 | 0.500 | **+0.111** |
| Retr. success | 21.2% | 24.2% | **+3.0 pp** |
| Retr. precision | 0.517 | 0.631 | **+0.114** |
| Retr. recall | 0.692 | 0.708 | +0.016 |
| Retr. MRR | 0.370 | 0.481 | **+0.111** |
| Latency mean | 143 s | 150 s | +7 s |

**Reading:**
- Retrieval layer improved significantly across all metrics vs. baseline (success +3 pp, precision +0.11, MRR +0.11). Gate revert to 0.40 recovered the precision lost in Runs 3–4.
- Presentation slightly below baseline on success/precision/recall but MRR up sharply (+0.111) — the right assets rank better when the LLM does select them.
- Presentation below baseline because the single-outlier cutoff at cut=1 (still allowed here) occasionally collapses the candidate pool to 1 asset; when that 1 asset is a FP, success/precision both suffer.

---

## Run 6 — 2026-04-22 22:42 (`all_20260422-224232`) — elbow cut≥2 (no single-outlier cutoff)

**State:** same tool config and prompt as Run 5. Only change: elbow cutoff now requires `cut >= 2` — a single-outlier gap (which would keep only 1 asset) falls through to the top-N fallback instead of triggering a hard cut.

**Changes vs. Run 5:**
- Tool: `_dynamic_cutoff` condition changed from `cut >= 1` → **`cut >= 2`**. When the maximum gap is between position 0 and 1 (one high-scoring outlier), the elbow is skipped and fallback top-20 is used instead.
- Prompt: unchanged.

**Results:**
- **Presentation:** success **51.5%** (17/33), precision 0.652, recall 0.562, MRR 0.444.
- **Retrieval:** success 24.2% (8/33), precision 0.561, recall 0.714, MRR 0.370.
- Latency: mean 142 s, max 225 s.

**Deltas vs. Run 5:**

| Metric | Run 5 | Run 6 | Δ |
|---|---|---|---|
| Pres. success | 48.5% | **51.5%** | **+3.0 pp** |
| Pres. precision | 0.623 | 0.652 | +0.029 |
| Pres. recall | 0.557 | 0.562 | +0.005 |
| Pres. MRR | 0.500 | 0.444 | −0.056 |
| Retr. success | 24.2% | 24.2% | = |
| Retr. precision | 0.631 | 0.561 | −0.070 |
| Retr. recall | 0.708 | 0.714 | +0.006 |
| Retr. MRR | 0.481 | 0.370 | −0.111 |
| Latency mean | 150 s | 142 s | −8 s |

**Deltas vs. Run 2 (baseline):**

| Metric | Run 2 | Run 6 | Δ |
|---|---|---|---|
| Pres. success | 51.5% | **51.5%** | = |
| Pres. precision | 0.659 | 0.652 | −0.007 |
| Pres. recall | 0.592 | 0.562 | −0.030 |
| Pres. MRR | 0.389 | 0.444 | **+0.055** |
| Retr. success | 21.2% | **24.2%** | **+3.0 pp** |
| Retr. precision | 0.517 | 0.561 | **+0.044** |
| Retr. recall | 0.692 | 0.714 | +0.022 |
| Retr. MRR | 0.370 | 0.370 | = |
| Latency mean | 143 s | 142 s | −1 s |

**Reading:**
- `cut >= 2` trades retrieval precision/MRR for presentation success and precision — when single-outlier cases fall through to top-20, the LLM sees more candidates but selects more accurately.
- **Vs. baseline:** presentation success tied (51.5%), retrieval better across the board (+3 pp success, +0.044 precision, +0.022 recall). Best combined result so far.
- Retrieval MRR drop from Run 5 is expected: cases that previously cut to 1 (high-ranked asset) now return 20 candidates where the relevant asset may not rank first.

---

## Run 7 — 2026-04-23 15:11 (`all_20260423-151132`) — softer VALIDATE + strict combined-content + bilingual expansions

**Changes vs. Run 6:**
- Prompt: VALIDATE softened ("Exclude only clearly irrelevant assets. **When in doubt, include the asset.**"); combined-content rule hardened back to strict ("each retained asset must cover ALL required attributes in a single dataset"); language rule kept.
- Query expansions: LLM now generates bilingual expansions for non-English queries (e.g. Portuguese query → 3–4 PT + 2 EN expansions). English queries stay English-only. Observed in logs across all tests.
- Tool: unchanged from Run 6 (`_COSINE_GATE=0.40`, `_FALLBACK_TOP_N=20`, `_MIN_GAP_RATIO=0.30`, elbow `cut >= 2`).

**Results:**
- **Presentation:** success **39.4%** (13/33), precision 0.582, recall **0.636**, MRR **0.667**.
- **Retrieval:** success 3.0% (1/33), precision 0.308, recall 0.811, MRR 0.593.
- Latency: mean 159 s, max 257 s.

**Deltas vs. Run 6:**

| Metric | Run 6 | Run 7 | Δ |
|---|---|---|---|
| Pres. success | 51.5% | 39.4% | **−12.1 pp** |
| Pres. precision | 0.652 | 0.582 | −0.070 |
| Pres. recall | 0.562 | **0.636** | **+0.074** |
| Pres. MRR | 0.444 | **0.667** | **+0.223** |
| Retr. success | 24.2% | 3.0% | **−21.2 pp** |
| Retr. precision | 0.561 | 0.308 | **−0.253** |
| Retr. recall | 0.714 | 0.811 | **+0.097** |
| Retr. MRR | 0.370 | **0.593** | **+0.223** |
| Latency mean | 142 s | 159 s | +17 s |

**Reading:**

- **Recall and MRR improved sharply** across both layers — the best MRR values recorded so far. The softer VALIDATE is letting more relevant assets through, and the bilingual expansions improve embedding coverage for Portuguese queries, boosting recall.
- **Success rate and precision regressed** — the strict `unexpected=X` testbed check penalises every extra FP the tool returns, and the softened filter lets more of them through to the LLM, which doesn't always discard them.
- **Explicit precision-recall tradeoff:** higher recall means more true positives are being shown to the user, at the cost of some false positives. This is the right trade for a catalog discovery tool — missing a relevant asset is worse than showing a marginally irrelevant one; users can discard FPs but cannot recover TPs they never saw.
- **LLM is an effective second filter for no-results cases.** In all 10 "no_results" tests, the LLM correctly returned 0 assets even when the tool passed 1–11 FPs through (presentation passed on all 10). This validates keeping a soft retrieval gate: the LLM reliably filters noise for clearly off-domain queries.
- **Retrieval success collapse (3%) is structurally expected.** The strict `expected_count=0, found_count=N` check guarantees failure whenever the tool returns any asset. This makes the retrieval success metric misleading when the tool is intentionally permissive — MRR and recall are more informative here.
- **New embedding hub concern — `tb-solar-1`.** Observed scoring 0.45–0.59 for completely unrelated queries ("CO2 aviation emissions", "EV charging infrastructure"). Previously `tb-wind-3` was the known hub; `tb-solar-1` may now exhibit the same behaviour. This is a tool-layer issue independent of the prompt changes.
- **Bilingual expansions double-edged.** For Portuguese queries, adding English expansions increases recall (English asset descriptions match better) but also inflates FPs from English "Portugal" / energy keyword overlap. The net effect on recall is positive here.

---

## Planned: Run 8 — targeted fixes for observed failure modes

**Identified problems to address (in approximate priority order):**

1. **Contextual queries — low semantic score for contextually relevant assets.** For some testbed queries, the correct asset doesn't score high enough in semantic search, because the user's phrasing doesn't map directly to the asset description. Query expansions should be generated to maximise embedding recall — broader, more diverse, and explicitly closer to how EDC assets are described — not just paraphrases of the user query.

2. **Partial-satisfaction queries — tool rejects partially matching assets.** For queries like "Preciso de um dataset que tenha ao mesmo tempo perfis verticais de vento e curvas de potência de turbinas" or "I'm looking for a single dataset with both onshore wind measurements and electricity generation", the semantic search identifies candidates but the tool (or LLM) discards them because they only partially satisfy the combined requirement. The tool should pass these candidates through, and the LLM should: (a) retain partial matches, and (b) actively surface asset combinations that together satisfy the requirement when no single dataset covers it fully.

3. **Cross-domain hallucination — LLM accepts wrong-domain assets.** For "Quero benchmarks de modelos de previsão para energia hídrica", the LLM selected a solar energy benchmark instead of a hydro benchmark, because it latched onto the "benchmark" keyword without enforcing the domain constraint. LLM filtering must be stricter about matching the asset's domain/content against the user's explicit domain qualifier.

4. **Query expansions generated in English regardless of query language.** The current tool generates query expansions in English even when the user queries in Portuguese (or another language). Expansions should be generated in the same language as the user's query (or bilingually) to improve embedding alignment.

5. **LLM response language mixing.** The LLM occasionally mixes the query language with English in its response. The response must consistently use the same language as the user's query throughout.

6. **"Only X matching asset was found" appears at the end and in the wrong language.** This phrase should appear at the beginning of the response (before the asset list) and must follow the user's query language.

7. **Spurious "No matching assets were found" appended after results.** The LLM sometimes appends this phrase even when assets were returned. This must be removed — it should only appear when the result list is genuinely empty.

---

## How to append a new run

1. Run the testbed and capture the timestamp of the output files.
2. Record in the index table above (one line).
3. Add a new `## Run N` section below with:
   - Config (tool constants, prompt version, model).
   - Full metrics (both layers).
   - Deltas vs. the previous comparable run.
   - Short "reading" of what changed and why.
4. Prefer changing **one variable at a time** so deltas are attributable.
