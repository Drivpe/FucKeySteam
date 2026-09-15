## Parent

#1

## What to build

**This ticket's body is deliberately incomplete. It is filled in after its blockers report, not before.**

The parent spec excluded one question from scope and named it as the most consequential remaining unknown: whether the remote manifest result participates in the gate's decision to release. The gate function body contains ticket verification, an asynchronous remote-manifest check, and a result-application call within one scope. Whether the manifest outcome can block release is not settled by static reading.

That question cannot be made concrete yet. Its framing depends on what the three observation tickets find — in particular on whether the verification-code dialog is still present once the integrity path changes. If the dialog is gone, this question changes shape entirely. Writing acceptance criteria now would be inventing them.

The blocking edges below are the mechanism: when all three have reported, whoever picks this up writes the body from their findings and relabels it. Until then it is parked, and the label says so.

## Acceptance criteria

- [ ] The body is rewritten from the actual results of the three observation tickets, not from the assumptions in the parent spec.
- [ ] The specific question asked is one whose answer would change what gets built next.
- [ ] The label is changed to mark it as ready for work once the body is complete.

## Blocked by

- #3 (ticket 02 — build host)
- #4 (ticket 03 — runtime observation)
- #5 (ticket 04 — disk state)
