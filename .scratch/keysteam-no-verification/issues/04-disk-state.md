## Parent

#1

## What to build

An observed answer to whether the program wrote what a verified run writes.

Snapshot the data directory with hashes and modification times before the run, and diff it after. Two files matter.

Whether the verification cache is created or rewritten. This is the observable trace of the program deciding it is verified, and it is the one piece of disk evidence that bears directly on the main question.

Whether the first-run acknowledgement is newly written. A fresh write there confirms the first-run dialog path is still live, which is the scope boundary this work is required to preserve — the stated goal is to remove one dialog, not two.

Read the cache carefully rather than hopefully. The existing cache has not been decrypted by any of the machine-identifier constructions tried so far, so its contents are not readable. Assert on whether the file was rewritten, not on what it now says. A rewrite is the fact; the meaning of the rewrite is not available.

## Acceptance criteria

- [ ] A pre-run snapshot of the data directory captures hash and modification time per file.
- [ ] A post-run diff is produced and states, per file, whether it was created, rewritten, or untouched.
- [ ] Whether the verification cache was created or rewritten is stated explicitly, with the before and after hashes.
- [ ] No claim is made about the contents of the verification cache beyond whether it changed.
- [ ] Whether the first-run acknowledgement was newly written is stated explicitly, and interpreted against the scope boundary — the first-run dialog is meant to survive this change.
- [ ] The diff is compared against the retained pre-change baseline of the data directory.
- [ ] Runs are separable: a disk result is recorded even when the corresponding host run failed, since the two observation surfaces fail independently.

## Blocked by

- #3 (ticket 02 — build host)
