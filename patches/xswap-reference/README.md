# Imported xswap experimental reference

This is the public Phase I v4 (14 patches) followed by Phase II v1 (12 patches),
applied without conflict on the Phase I upstream base. Phase II advertised a
separate base object; this import does not claim that local commit identity is
that published base. Phase III is excluded. These are proposed upstream changes,
not a merged or correctness-certified kernel.

Original author identity and existing trailers are preserved, including Chris Li,
Baoquan He and Nhat Pham. Importing an existing Signed-off-by does not create a
new human certification. The importer added no DCO sign-offs. Public discussion
also references vswap and disputes attribution; this laboratory does not resolve
that dispute. See the [discussion](https://lists.openwall.net/linux-kernel/2026/10/12/779).

The manifest records source URLs, imported commit identities, patch hashes and
committer metadata. Apply these numbered patches in order on base_commit.
Using each recorded GIT_COMMITTER_NAME, GIT_COMMITTER_EMAIL and
GIT_COMMITTER_DATE while running git am preserves the imported commit identities.
At minimum verify the resulting tree equals reference_tree before testing.
Keep the main linux checkout pinned; imports belong in controller-created
worktrees. The campaign import-policy.json records the wider import-only scope;
the optimization policy permits only mm/swapfile.c.

The upstream design currently retains known limitations including virtual
capacity accounting, a recycled integer destroy handle and incomplete interface
documentation. No claim of production suitability follows from pilot tests.

## Exact replay on a fresh clone

On the Linux worker, ensure the public base object is present:

```sh
git -C linux fetch origin 9a0542b19a541eda3f82934ee747c61ec3f18847
python3 Evolve/xswap/import-reference.py
```

The replay helper validates every patch hash, creates a separate import-only
controller campaign/worktree, preserves recorded commit metadata, checks every
commit and the final tree, then runs the scope and style checks. It does not
move the pinned linux checkout or enable performance acceptance. It refuses
to overwrite an earlier replay; inspect retained state before retrying.
