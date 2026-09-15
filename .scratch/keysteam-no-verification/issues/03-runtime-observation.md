## Parent

#1

## What to build

An observed answer to what the program does while it runs, taken while it runs.

Run the existing monitoring script and launch the host. The ordering is not a preference — the verification dialog is modal and the failure mode is a dialog whose only button exits, so a run that goes wrong leaves nothing to inspect afterwards unless observation started first.

Four things get asserted. Whether a guard process appears. Whether the guard's named pipe appears. What outbound connections the host makes. And whether a window carrying the tamper warning's title appears.

That last assertion is the one that answers the main question. The verification dialog has no close button, so its absence is only meaningful if something was looking for it. A run that simply ends is not evidence of success.

## Acceptance criteria

- [ ] Monitoring starts before the host is launched, in every recorded run.
- [ ] Absence or presence of the `keysteam-runtime-guard` process is recorded per run.
- [ ] Absence or presence of the `\\.\pipe\keysteam_guard_` pipe is recorded per run.
- [ ] The outbound connection list is captured, with the remote endpoints named.
- [ ] Window titles are captured for the host process, and the presence or absence of a window titled `倒卖可耻` is stated explicitly for each run.
- [ ] Presence or absence of the verification-code dialog is stated explicitly for each run — recorded as observed, not inferred from a clean exit.
- [ ] Each run's monitor log is retained alongside its host stdout and exit code, so the two can be read together.

## Blocked by

- #3 (ticket 02 — build host)
