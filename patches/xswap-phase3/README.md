# Imported xswap Phase III

The public Phase III series "[PATCH 0/6] mm, swap: charge xswap for physical
backing (xswap phase III)" (Baoquan He, Nhat Pham; 2026-10-03), applied with
`git am` on the Phase I v4 + Phase II v1 reference `37de636c`
([patches/xswap-reference](../xswap-reference/README.md)). All six patches apply
cleanly. The result is `b2beda7f`, tree `187cfe49`.

| # | Subject |
|---|---|
| 01 | mm, swap: split the swap memcg charge helpers |
| 02 | mm, swap: do not charge zswap-backed xswap entries |
| 03 | mm, swap: charge an xswap entry when it gets physical backing |
| 04 | mm, swap: don't gate xswap on the physical swap free count |
| 05 | mm, swap: do not retake the cluster lock when uncharging an xswap slot |
| 06 | mm, swap: drop a refused xswap backend run directly |

The series moves swap memcg charging from slot allocation to the point where
an xswap entry gains a physical backend, and touches `mm/memcontrol*.c`, so the
import-only campaign `xswap-phase3-import` widens the import scope to those
files. Candidate optimization scope is set separately by each campaign.

The manifest records the source URL, patch hashes, commit identities and
committer metadata. Original authorship and trailers are preserved; the importer
added no Signed-off-by. Import evidence: controller `check` returned SCOPE_PASS
with clean diff-check and checkpatch (379 changed lines, 6 files).

The descriptor-lifetime finding in
[results/xswap-structure-2026-10-22](../../results/xswap-structure-2026-10-22/descriptor-lifetime-review.md)
is in the Phase I shrink path and still applies to this reference.
