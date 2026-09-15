## Parent

#1

## What to build

A settled answer to two questions that gate everything downstream: which language the host is written in, and how its `argv[0]` / `envp` are constructed.

The toolchain question is answered by fact, not taste. `C:\Program Files\mingw64\bin\x86_64-w64-mingw32-g++.exe` is a complete GCC 15.1.0 toolchain and was verified present. The earlier assessment that no mingw existed was based on a PATH search and was wrong. C is the language: it matches Nuitka's own implementation shape and avoids the process-wide DLL-search-path APIs that a CLR host would need to touch.

The `argv[0]` and `envp` questions are answered by the disassembly in the parent spec, and the answer is that `boot.c`'s two-argument form is not safe to copy: `run_code` reads a third register. This ticket records the contract precisely enough that the host implementation can be written against it without re-deriving it.

Deliverable is a decision record plus a minimal probe that proves `.py`-suffixed values survive whatever normalisation the program applies.

## Acceptance criteria

- [ ] Host language recorded as C, built with the existing mingw64 GCC 15.1.0; no new toolchain installed.
- [ ] `run_code`'s signature recorded as the three-argument form it actually is, with the register-level evidence that established it, and with an explicit note that the two-argument form found in `boot.c` works only by accident of the x64 calling convention.
- [ ] The `envp` third argument is treated as required, not optional. What the host must put in it is specified: the same variables the shipped launcher sets.
- [ ] The value to pass as `argv[0]` is specified as an explicit path ending in `.py`.
- [ ] The suffix test's real form is recorded correctly — `strip()` + `casefold()` + membership against the pair `(".py", ".pyw")`, not a `pathlib` suffix property.
- [ ] A minimal probe demonstrates a `.py`-suffixed value surviving to the point where the suffix test would run.

## Blocked by

None — can start immediately.
