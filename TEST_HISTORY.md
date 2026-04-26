# Test History — search_catalog testbed

Ledger of evaluation runs for the `search_catalog` pipeline. Record each run with the **exact configuration** that produced it plus the **deltas** vs. the previous run so we don't repeat experiments.

All runs use `use_cases.json` (33 tests, 11 use-case groups, 1 run per test unless noted). Precision/recall are macro-averaged over the 23 tests that have a non-empty `expected_present` (the 10 "no-results" tests are excluded from P/R; they still count toward success_rate).

Artifacts live under `deployment/testbeds/search_catalog/results/<prompt_version>/all_<timestamp>.{json,log}`.

Prompt version subdirectories:
- `v1/` — strict validate + hard-constraint (Runs 1–3)
- `v2/` — softened VALIDATE + softened combined-content (Run 4)
- `v2_hybrid/` — re-hardened VALIDATE + softened combined-content (Runs 5–6 + contextual)
- `v2_soft_validate/` — softer VALIDATE + strict combined-content + bilingual expansions (Run 7)
- `v3/` — full rewrite: LANGUAGE POLICY, complementarity step, sibling-subtype rule (Runs 8–9)
- `v4/` — Gates A/B/C, strict combination trigger, Gate C anti-hedge requirement (Run 10)
- `misc/` — pre-run scratch logs

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
| 8 | 2026-04-23 18:29 | prompt v3 (lang policy + complementarity step) + expanded query expansion (4–8, 7 angles) | qwen2.5:7b | 9.1% | 0.350 / **0.850** / **0.778** | 27.3% | 0.605 / **0.814** / **0.778** | 233 s |
| 9 | 2026-04-24 12:05 | same prompt v3 + original query expansion (2–8, 5 angles — ablation) | qwen2.5:7b | 6.1% | **0.407** / 0.799 / 0.741 | 18.2% | 0.568 / 0.797 / 0.815 | 214 s |
| 10 | 2026-04-24 17:28 | prompt v4 (Gates A/B/C + strict combination trigger) + expanded query expansion (4–8, 7 angles) | qwen2.5:7b | 6.1% | 0.408 / **0.890** / **0.815** | **39.4%** | **0.641** / 0.688 / **0.815** | 213 s |

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

## Run 8 — 2026-04-23 18:29 (`all_20260423-182935`) — prompt v3 + expanded query expansion

**Changes vs. Run 7:**

- **Prompt (search_catalog_prompt.py):** full rewrite → v3.
  - Added explicit **LANGUAGE POLICY** section at the top: detect query language, entire output in that language (including translated asset descriptions), only `asset_id` and `<DONE>` kept verbatim, no mixing allowed. This directly targets the language-mixing and wrong-language status-line failures observed in Run 7.
  - **VALIDATE** (step 3): tightened wording — "exclude clearly irrelevant assets"; added "even if indirect but plausible" to contextual connection; clarified that doubt → include and step 4 handles stricter filtering.
  - **HARD-CONSTRAINT CHECK** (step 4): added explicit **sibling-subtype rule** ("an asset covering a sibling subtype MUST be dropped — belonging to the same parent category is NOT a substitute"). "Required combinations" removed from this step and promoted to a separate step 5.
  - **New step 5 — COMBINATION / COMPLEMENTARITY HANDLING**: full match vs. partial match classification; partial matches listed with explicit coverage/gap annotation; combination note added when two+ partial matches together satisfy the requirement. Addresses the partial-satisfaction failure mode from Run 7.
  - **OUTPUT FORMAT** (step 6): strict structured format — status line rules (omit when full results, "Only X" when fewer, "No matching" when zero), numbered list with `asset_id / description / connection / match_type` fields, complementarity paragraph after list, `<DONE>` on its own line.
  - **CRITICAL CONSTRAINTS**: added explicit rule forbidding list + "No matching" in the same response (spurious appended phrase from Run 7).

- **Query expansion description (search_catalog_tool.py `SearchCatalogArgs`):** rewritten.
  - Min expansions raised **2 → 4**.
  - Added **LANGUAGE RULE**: expansions in the same language as the user's query; exception for English technical terms (≥1 English expansion required when the concept is primarily used in English literature). Replaces the ad-hoc bilingual behaviour observed in Run 7 with an explicit, principled rule.
  - Coverage extended to **7 angles** (previously 5): added (6) combination-splitting (one expansion per component + one for the pair) and (7) contextual expansion (downstream use cases, related metrics, typical data products). Directly targets the contextual-query and partial-satisfaction retrieval failures.
  - Style section: explicit 3–8 word phrase guidance; updated example with 6 entries.

- **Tool constants:** unchanged (`_COSINE_GATE=0.40`, `_FALLBACK_TOP_N=20`, `_MIN_GAP_RATIO=0.30`, elbow `cut >= 2`).

**Results:**
- **Presentation:** success **27.3%** (9/33), precision 0.605, recall **0.814**, MRR **0.778**.
- **Retrieval:** success 9.1% (3/33), precision 0.350, recall **0.850**, MRR **0.778**.
- Latency: mean 233 s, max 456 s.

**Deltas vs. Run 7:**

| Metric | Run 7 | Run 8 | Δ |
|---|---|---|---|
| Pres. success | 39.4% | 27.3% | **−12.1 pp** |
| Pres. precision | 0.582 | 0.605 | +0.023 |
| Pres. recall | 0.636 | **0.814** | **+0.178** |
| Pres. MRR | 0.667 | **0.778** | **+0.111** |
| Retr. success | 3.0% | 9.1% | +6.1 pp |
| Retr. precision | 0.308 | 0.350 | +0.042 |
| Retr. recall | 0.811 | **0.850** | +0.039 |
| Retr. MRR | 0.593 | **0.778** | **+0.185** |
| Latency mean | 159 s | 233 s | **+74 s** |

**Reading:**
- **Recall and MRR improved sharply** — both are the best values recorded so far. The 7-angle expanded query expansion is picking up contextually relevant assets and combination components that the narrower 5-angle set missed.
- **Success rate regressed** again — the broader query expansions surface more FPs, which the strict `unexpected=X` testbed check penalises. This is the same structural tension observed in Runs 3–4 and 7.
- **Latency cost is high (+74 s mean)**: generating 4–8 longer, more detailed expansions plus the richer prompt v3 adds significant LLM time per query.
- **Run 9 (ablation without expanded query expansion) was run next to isolate whether the recall gains are from the prompt v3 rewrite or the expanded query expansion.**

---

## Run 9 — 2026-04-24 12:05 (`all_20260424-120530`) — prompt v3 + original query expansion (ablation)

**Purpose:** isolate the effect of the expanded query expansion. Identical to Run 8 except the `SearchCatalogArgs` description was reverted to the shorter Run 6/7 version (2–8 entries, 5 angles, no LANGUAGE RULE, no combination-splitting or contextual-expansion angles).

**Changes vs. Run 8:**
- **Query expansion description:** reverted to the original (2–8 entries, 5 semantic angles). All other conditions identical.
- **Prompt:** unchanged (v3 — same as Run 8).
- **Tool constants:** unchanged (`_COSINE_GATE=0.40`, `_FALLBACK_TOP_N=20`, `_MIN_GAP_RATIO=0.30`, elbow `cut >= 2`).

**Results:**
- **Presentation:** success **18.2%** (6/33), precision 0.568, recall 0.797, MRR **0.815**.
- **Retrieval:** success 6.1% (2/33), precision **0.407**, recall 0.799, MRR 0.741.
- Latency: mean 214 s, max 413 s.

**Deltas vs. Run 8 (expanded vs. original query expansion):**

| Metric | Run 8 (expanded) | Run 9 (original) | Δ |
|---|---|---|---|
| Pres. success | 27.3% | 18.2% | **−9.1 pp** |
| Pres. precision | 0.605 | 0.568 | −0.037 |
| Pres. recall | **0.814** | 0.797 | −0.017 |
| Pres. MRR | 0.778 | **0.815** | +0.037 |
| Retr. success | 9.1% | 6.1% | −3.0 pp |
| Retr. precision | 0.350 | **0.407** | **+0.057** |
| Retr. recall | **0.850** | 0.799 | −0.051 |
| Retr. MRR | **0.778** | 0.741 | −0.037 |
| Latency mean | 233 s | 214 s | −19 s |

**Reading:**
- **Expanded query expansion drives recall and retrieval MRR.** Removing it drops retrieval recall by −0.051 and retrieval MRR by −0.037 — the 7-angle coverage (especially combination-splitting and contextual expansions) meaningfully improves the tool's ability to retrieve the right candidates.
- **Original query expansion yields better retrieval precision (+0.057)** — fewer angles means fewer FPs surface. This also explains the slightly better presentation MRR: when the LLM sees a cleaner candidate set, its top-ranked selection is more reliable.
- **Latency savings are modest (−19 s)** — the main cost is prompt v3 itself, not the expanded query expansion text.
- **Conclusion:** the expanded query expansion is net-positive on recall (the primary objective for catalog discovery), at the cost of more FPs and slightly higher latency. Prompt v3 alone (without the expanded expansion) recovers some precision but loses recall. Both together (Run 8) represent the best recall configuration recorded so far.

**Deltas vs. Run 2 (baseline):**

| Metric | Run 2 | Run 9 | Δ |
|---|---|---|---|
| Pres. success | **51.5%** | 18.2% | **−33.3 pp** |
| Pres. precision | 0.659 | 0.568 | −0.091 |
| Pres. recall | 0.592 | **0.797** | **+0.205** |
| Pres. MRR | 0.389 | **0.815** | **+0.426** |
| Retr. success | **21.2%** | 6.1% | **−15.1 pp** |
| Retr. precision | 0.517 | 0.407 | −0.110 |
| Retr. recall | 0.692 | **0.799** | **+0.107** |
| Retr. MRR | 0.370 | **0.741** | **+0.371** |
| Latency mean | 143 s | 214 s | +71 s |

---

## Run 10 — 2026-04-24 17:28 (`all_20260424-172825`) — prompt v4 (Gates A/B/C)

**Changes vs. Run 8 (same tool config, same expanded query expansion):**

- **Prompt (search_catalog_prompt.py):** rewrite → v4.
  - Steps 3–5 replaced with a three-gate pipeline: **Gate A** (primary-subject match on domain, entity class, and subtype qualifier), **Gate B** (hard-constraint check — drop on first violation, no weighing against overlap), **Gate C** (concrete-connection requirement — the asset survives only if you can write a hedge-free declarative sentence naming a specific attribute from the description that directly satisfies a specific phrase in the query; hedge words such as "may", "could", "related to", "indirectly" cause an automatic drop).
  - **COMBINATION HANDLING** (step 4) is now gated on an explicit trigger: the query must contain a combination connector ("both X and Y", "at the same time", "combined with", etc.). A bare "and" is no longer sufficient. When not triggered, partial-match assets are evaluated as plain candidates under Gates A–C and dropped if they lack a concrete direct connection.
  - Added explicit **drop-on-doubt** rule in Gate C.
  - CRITICAL CONSTRAINTS expanded: added "It is correct and expected to return zero assets" and "thematic proximity is NOT a substitute for concrete connection".
  - Removed the v3 step numbering collision (v3 had steps 3 VALIDATE → 4 HARD-CONSTRAINT → 5 COMBINATION → 6 OUTPUT; v4 collapses these to 3 FILTER → 4 COMBINATION → 5 OUTPUT).
- **Query expansion description (search_catalog_tool.py):** same as Run 8 (4–8 entries, 7 angles, LANGUAGE RULE). Note: Run 9 had reverted this to 5 angles; Run 10 re-applies the expanded version.
- **Tool constants:** unchanged (`_COSINE_GATE=0.40`, `_FALLBACK_TOP_N=20`, `_MIN_GAP_RATIO=0.30`, elbow `cut >= 2`).

**Results:**
- **Presentation:** success **39.4%** (13/33), precision **0.641**, recall 0.688, MRR **0.815**.
- **Retrieval:** success 6.1% (2/33), precision 0.408, recall **0.890**, MRR **0.815**.
- Latency: mean 213 s, max 363 s.

**Deltas vs. Run 8 (prompt v3 + expanded query expansion):**

| Metric | Run 8 | Run 10 | Δ |
|---|---|---|---|
| Pres. success | 27.3% | **39.4%** | **+12.1 pp** |
| Pres. precision | 0.605 | **0.641** | **+0.036** |
| Pres. recall | **0.814** | 0.688 | **−0.126** |
| Pres. MRR | 0.778 | **0.815** | +0.037 |
| Retr. success | 9.1% | 6.1% | −3.0 pp |
| Retr. precision | 0.350 | **0.408** | **+0.058** |
| Retr. recall | 0.850 | **0.890** | +0.040 |
| Retr. MRR | 0.778 | **0.815** | +0.037 |
| Latency mean | 233 s | 213 s | **−20 s** |

**Deltas vs. Run 2 (baseline):**

| Metric | Run 2 | Run 10 | Δ |
|---|---|---|---|
| Pres. success | **51.5%** | 39.4% | −12.1 pp |
| Pres. precision | **0.659** | 0.641 | −0.018 |
| Pres. recall | 0.592 | **0.688** | **+0.096** |
| Pres. MRR | 0.389 | **0.815** | **+0.426** |
| Retr. success | **21.2%** | 6.1% | −15.1 pp |
| Retr. precision | 0.517 | 0.408 | −0.109 |
| Retr. recall | 0.692 | **0.890** | **+0.198** |
| Retr. MRR | 0.370 | **0.815** | **+0.445** |
| Latency mean | 143 s | 213 s | +70 s |

**Reading:**

- **Presentation success recovered sharply (+12.1 pp vs. Run 8)** — the strict three-gate filter (especially Gate C's anti-hedge requirement) significantly cuts FPs. The LLM now drops assets it cannot connect to the query with a concrete, hedge-free sentence.
- **Presentation recall dropped (−0.126 vs. Run 8)** — the stricter filter is now cutting some true positives. Gate C's no-hedge rule may be too aggressive for assets with indirect but legitimate connections; the LLM may be failing Gate C on assets it should keep.
- **Retrieval recall improved (+0.040 vs. Run 8, +0.198 vs. baseline)** — the expanded 7-angle query expansion continues to improve tool coverage; this is the highest retrieval recall recorded so far (0.890).
- **MRR at both layers improved (+0.037 vs. Run 8)** — 0.815 is the best MRR recorded at either layer. When the LLM does include an asset, it ranks it correctly.
- **Precision gap between retrieval (0.408) and presentation (0.641)** confirms that Gate C is doing real filtering work — the LLM discards ~37% of the tool's candidates. However, some of that filtering is over-aggressive (recall drop).
- **Latency slightly lower (−20 s vs. Run 8)** — modest gain; the prompt v4 is slightly shorter than v3.
- **Key tension:** the v4 prompt achieves better precision and MRR but at the cost of presentation recall. The next step is to investigate which tests regressed on recall under v4 to determine whether Gate C is mis-firing or whether the tool is retrieving assets that genuinely do not belong.

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
