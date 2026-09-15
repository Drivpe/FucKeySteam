## Parent

#1

## What to build

A native C host that starts the sample and completes a full `run_code` call, built with the mingw64 toolchain already present on this machine.

The host does four things: point module resolution at the payload directory, load `main.dll` from it, resolve the single export `run_code`, and invoke it with a caller-constructed argument vector and environment vector. It returns the program's own exit code.

Two things previously carried the label "known blocker". Both were reproduced inside an existing Python process, and neither has been tested under a native host — which is exactly the variable that changes. `main.dll` imports `python312.dll` statically, so in a process that has already loaded a module by that name, the loader satisfies the dependency from the already-loaded one and the program is linked against a runtime Nuitka never initialised. A native host without a pre-existing interpreter breaks that condition. The task is to find out whether the blockers survive, not to build a workaround for them pre-emptively.

Environment injection needs the same care. The shipped launcher sets two variables before calling through, and it passes an environment block as the third argument. A host that omits the third argument will start, and may even appear to work, while running without that injection. Build both variants.

Watch that the load flags do more work here than in a typical case. The dependency on `python312.dll` is the reason: the search must be forced to resolve it from the payload directory rather than from anywhere already loaded.

## Acceptance criteria

- [ ] Host builds with the existing mingw64 GCC 15.1.0 and produces a runnable executable. No new toolchain installed.
- [ ] `LoadLibraryExW` succeeds on the payload copy of `main.dll`, or fails with a recorded error code that names the missing dependency.
- [ ] `GetProcAddress(h, "run_code")` returns a non-null address under the native host. The previously observed null return is either reproduced with a stated cause or shown to be an artefact of the Python-process context.
- [ ] `run_code` is invoked with all three arguments populated: count, argument vector, environment vector.
- [ ] A second variant passes a null environment vector, so the two behaviours can be compared rather than assumed.
- [ ] Both documented blockers are recorded as settled facts: reproduced with a cause, or shown not to occur.
- [ ] The host's exit code is the value `run_code` returned.
- [ ] Original files untouched. The payload copy is the only tree the host points at.

## Blocked by

- #2 (ticket 01 — host contract)
