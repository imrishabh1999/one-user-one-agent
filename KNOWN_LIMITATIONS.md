# Known limitations

Left incomplete on purpose, roughly in the order I would fix them.

1. **Synthetic world, synthetic effects.** No pack came with the brief, so `datagen.py` builds one and
   `simulate.py` decides how viewers respond. The treatment effects are numbers we chose. The replay shows the
   pipeline measures an effect honestly; it says nothing about real viewers. If the real pack arrives, only
   the loader (`store.load_pack`) and the field mapping should need to change.
2. **Latency is simulated.** Every call has a fixed simulated cost and faults are injected by the replay
   harness. Real p95s would come from real dependencies. Wall-clock compute per decision is milliseconds.
3. **One worker process.** The worker pool is a discrete-event simulation. A production version needs a real
   queue partitioned by `viewer_id` and a per-viewer lock.
4. **No follow-up nudge.** When a goal's deadline nears without progress, the agent only acts at the next app
   open or new data. A per-goal "check before deadline" timer (still event-driven, per viewer) is designed but
   not built; this is why PUSH/WhatsApp are rarely used in the sample run.
5. **Rule interpretations.** G06 "near expiry" is interpreted as ≤ 3 days (recorded as an assumption on every
   decision using it). G12 "active viewers" and G09 (needs content outside the app dialect) are disabled
   rather than guessed. G11 is disabled because its signal does not exist. All need a product decision.
6. **Renewals are not simulated**, so G10 (renew before expiry) always fails in both arms. It does not bias
   the ITT comparison but makes G10's numbers meaningless.
7. **Clock-skew detection needs history.** With fewer than 3 events the median offset is not trusted, so a
   brand-new viewer's wrong clock can make a fresh open look stale (safe: it leads to no action).
8. **Injection detection is a pattern list.** It catches the instruction-like text in this pack; a real system
   needs a classifier and, more importantly, keeps the structural defences (catalogue text never becomes an
   action; model output cannot widen scope), which do not depend on detection.
9. **Measurement power.** One evening and a 10% holdout give wide intervals. Production should pre-register a
   primary metric and minimum detectable effect, and stratify the holdout by dialect.
10. **The hosted-model provider is untested** in this repo (no key used). The mock is the supported path.
11. **No UI** beyond the CLI and the markdown audits; the brief puts the loop ahead of interface polish.
