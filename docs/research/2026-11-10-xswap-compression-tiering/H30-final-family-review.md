# H30: final independent family review

Status: **PASS for the retained C1 closeout, inactive C2 preparation and report readiness**. Confidence: high for the exact reviewed source and bound artifacts. No unresolved source/report blocker remains within this scope. Retain K1 for development; performance remains unmeasured and C2 runtime remains blocked.

## Scope and frozen review target

Authority: [H30 ticket](tickets/H30.json). Review K1 commit `7d5a3cfab2abb37b33afc03ed365d3024bd3d5ad` / tree `8b085adc109e3b5467c3de998f11b04517f052a5` against original baseline `5e84ca928deeacb4eee656806a003f27d1eca82f`; all six C1 accounting records; R5/R6 report sources, generated HTML and family routing. Final report-source pin: `aebf8ec3109b57aea2ca826e7715ec6c61930a1f`. Final reviewed integration: `5476fce37c5cbbea4667fb7ba824f57bac747734`.

The H27 closeout result is retained: R6 closed after deadline expiry with one counted unlaunched reservation; cumulative C1 is 20 counted reservations, 19 launches and nine builds. R6 runtime admission never completed. The final reconciliation below confirms these totals.

## Evidence and review boundaries

H24/H29 prepared-source commits, source-bound test receipts and final report visual receipts have been supplied and reviewed below. The inactive C2 profile and missing guest capability remain blocking. The refused H28 action will not be resumed, rephrased or reassigned; its isolated partial source is not build or runtime evidence. C3 has not run.

Only this review document may be changed. No implementation, state, tests, builds, guests, images, publication or delegation is authorized for this reviewer.

## Confirmed C1 source boundary

The exact K1 tree and all seven changed files were read, including the complete library and KUnit implementation, its ZSwap caller changes, and frontend publication, reference/RCU release, charge/uncharge and partial-folio cleanup. All six exported patches have SHA-256 `69e085f0b3703ae2929c0cc8e863b6f606fce1b15e8a4d3ab3fd378ef785f704`. No supported blocking ownership or failure-handling defect has been found.

Independent exact comparisons confirm that `zswap_entry`, `zswap_store` and the pool empty/release protocol are unchanged; `zswap_store_page` is unchanged after the object-free API substitution. CPU contexts and zsmalloc storage move behind the library; callers retain pool and handle pins. Codec failure alone reaches the frontend raw-store permission check, allocation failure cannot trigger raw retry, and loads remain non-consuming with exact-page output validation. Failed construction cleans possible-CPU contexts before freeing pool storage; published instances are removed before final context destruction.

The six K2 records bind the same commit/tree and the unchanged original review hash `81a10c87560a67169c47a69ff76ef26fe2b434a718f74c40a4836f25b89577f6`. Reuse is explicitly historical, not six independent source reviews. C1 provides a reusable implementation boundary; independent XSwap is still absent. One added pool allocation and eight requested bytes per pool are source-layout costs; allocator rounding and performance remain unmeasured.

## Confirmed runtime and report evidence

All nineteen launched result files, serial files and reservations independently match the public-observation hashes and outcome fields. The complete R5 proof hash is `f53bf3552546426a382657f4580d5b25bd25287e74fb032873da8ba8246d45cd`: eight fresh correctness rows match their raw hashes with all gates and run validity true; both disabled-build manifests match and pass. R5's next original-baseline timing attempt fails `parse_complete` while `run_valid` is true. Earlier configuration, parser, NUMA warning and clock-validity failures remain separately retained.

Native read-only extraction exactly reproduces both saved report summaries, with no review blockers or missing raw evidence. Native story validation passes. R5/R6 native evidence hashes remain `c2e24110f9c096e5175441dc91fc9b90570a226fa862442524bd13b5aabdceb3` and `a16191636484436c8a898724486547b2abb22b24e54695febae9b6d0e0305a45`.

The report renderer and index grouping source were read. The group changes presentation only; all six closed canonical routes exist, one dated R6 family card remains, and the other five links are in a closed details element. The report-source commit changes no `.agents` skill file.

## Finding resolved during review

Both initial stories and rendered reports retained a stale core-patch lead naming four infrastructure contracts and R4 functional observations. The coordinator corrected the authored `patches_lead` and regenerated both reports. Readback now states that R5 supplies complete correctness and R6 adds no runtime sample. After the final provenance/subtitle correction, generated HTML hashes are R5 `ae3f8d67e02b6b231ff806bdfcb61f0f2025a02f1b5b5736b035297395f647a1` and R6 `2cbec4007319a74788606bfc83e9b3a717dcdb0231514e967d08ea7145df061c`.

## Prepared C2 source review

H29 source commit `9192dde921b4e07bc73c7c5a8099b2d2d2bb91c9` is integrated as `ee8c28f`; production `swapin.c` remains at SHA-256 `ef22f63908aa733b6b561e4d753be4963596c9bcf62a9ec7741fbee7793615d9`. Review found no supported blocking source defect in its argc11 binding, raw probe registration/readbacks, current/future lock followed by exact target unlock, complete raw smaps validation, or matched old timing loops. Its preservation receipt confirms byte-identical target-readiness, H26 trace/loss/topology, data/selection/clock/reporting and both measured loops/shuffle sections.

The reviewer found a nonblocking H29 fixture defect: literal backslash-n counter strings failed at raw line termination before testing decimal rejection. Exact follow-up `66177c9420648afd1e5b1bc8723fde3b6991db58`, integrated as `7659c03`, now proves the successful raw read, the intended decimal rejection and canonical zero/U64_MAX controls for all three counters. The 25-test receipt and current test hash `d058c2da2a34a258f88b43a1bc1576b8322036726a873e41ed5fb32cf02c9a02` match. All five H29 retained receipt hashes match the delivery document under R6 `runs/control/c2-preparation/`. These remain source and synthetic-fixture checks.

H24 exact source `bbbce6bd6f079c606f77e240c1a6acfc05b104b2`, integrated as `5a239cb`, was read across catalog, identity/reservation, runner, parser, matrix proof, workflow, cache, planner, inactive profile and new tests. The source keeps revision 8 separate, the 12-row matrix, nine candidate configuration builds plus the typed expected-negative anchor build, explicit `executable=false`, and an explicit false noncompressed-timing adapter gate. No C2 kernel candidate, build or guest is present.

The review identified an operation/control-identity defect in H24: an overlap event could substitute the range from its actual op_begin, and opening controls could select a different key/count from the journal. Exact follow-up `2ac2ee3630b4580c87e66ba72429211dd73349cd`, integrated as `5476fce37c5cbbea4667fb7ba824f57bac747734`, resolves both parts. Later events now preserve kind/type/key/count/order; overlap uses both immutable begun ranges; spans cannot wrap; begin/arm/hold selectors are positive and bound to actual selected operations; next resolves to the first selected store; retained-write count is exactly one. Valid differing intersecting bases and subpage transitions remain accepted.

The exact follow-up source and all added tests were read. The retained before-fix tests expose 17 event and 19 control failures; all twelve new methods pass afterward. The affected isolated benchmark suite passes 179 tests with one optional missing-checkout skip, and native matrix/proof/budget checks pass 92 tests. The initial two PYTHONPATH import errors and corrected unchanged-source invocation remain preserved. Manifest SHA-256 `6cbb92607cf9296c1d47b64c64175e1669eb03c2c7b0da9f41a39c8bf0d138bb`, all six log hashes and the exact/integrated source hashes match. Final parser/test hashes are `8f5d236657284d0b0e002c208839f1ebceef44e69860e62a77f48ab0f30d5138` and `7a8fda5663f49bf5871c4edc85a4a3cf346d72d84c0d64490348fbb3197798bf`. The shared wire clarification matches SHA-256 `74ec3a6ad1e0422f1ef4e77df6075de04ed2ec1d971cccfdb223680e54d38e03`. This exact-tree finding is closed; H28 was not resumed.

## Report reproduction and visual review

Both retained `report-regeneration.json` receipts report byte-identical repeated output and match the final HTML hashes above, the shared generator hash `75c2448a0adc51b14e7990f0f6bda93ad47fde6c3ac71c5a18b49e8b32c89bfe`, helper hash `c857a00a4d57f1c7a76ae66d9b72609981df84c19920835c3e1732bde581226c`, and unchanged native evidence hashes. R5's archived replay receipt verifies all 28 archived harness files and reproduces all eight saved correctness gate/metric sets; its purpose is explicitly historical reconciliation.

All ten source-file links in each report match their declared hashes at the final source pin. The final R5/R6 visual manifests and all eight PNG hashes bind all four 1440/390 light/dark screenshots to each final HTML. Independent inspection of top, system and concrete-change crops across both reports, widths and themes confirms readable text, responsive stacking and visible ownership/cost diagrams. The family report visibly states 20 counted reservations, 19 launches and nine builds, with functional pass and unresolved performance. Visual inspection confirms presentation only.

## Integrated verification

The full integrated project receipt for `5a239cb70298c3beaad82a3939bc66113af35fb4` has SHA-256 `271c7a8932f84dbc0317f31ac8349ad2dfe1bab3afbdc9499973d9f47480e458`. All eight log hashes and actual summaries were checked: controller 169, benchmark 12, swap-standard 237, xswap 18, xswap-structure 29, hole-probe 20 and evolve 283 tests passed. The xswap and structure suites each retain one optional skip; the kernel suite ran zero tests and retained one optional skip. These suite counts include overlaps and are not independent evidence samples. All H24 retained log hashes and all 17 exact-commit source hashes independently match their manifest.

The final merged follow-up receipt for `5476fce37c5cbbea4667fb7ba824f57bac747734` has SHA-256 `01800ec9eefcd678f80a49ad2a7fb7ae136aee36ab1d03b635548be7c4945f2b`. Independent readback confirms both source hashes, both log hashes, **249 passing swap-standard tests with zero skips** and **92 passing native coverage/proof/budget tests**. The earlier broad checks remain preserved for the unchanged files. The reviewer performed read-only source/artifact inspection and changed only this review document; no test, build, guest, image or publication was executed by the reviewer.

## Limitations and reopening conditions

C1 has no accepted calibration, performance comparison or speedup. The extra allocation, lifetime boundary, retained-memory cost of the proposed observer and future error-path behavior remain relevant development risks. Source correctness and fixture success are distinct from measured runtime performance.

C2 currently contains inactive host validation and compressed-observer preparation. Its profile remains non-executable; the actual guest phase driver and noncompressed source/cap-zero timing adapter remain missing. H28's refused partial action remains isolated and blocked, with no retry, rephrasing or reassignment. There is no C2 kernel candidate/build/guest and no C3 execution. Final source or capability admission for a future runtime is a separate required review.

The coordinator still owns committing and publishing the prepared report delivery and checking the deployed commit, live pages and index. This review establishes report readiness, not an observed deployment. Reopen the applicable finding if any reviewed source, frozen protocol, evidence binding or rendered HTML changes, or if real observations contradict the reviewed ownership, source-role, isolation, decode-cardinality or resource assumptions. Nothing remains running under this review.
