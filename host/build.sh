#!/usr/bin/env bash
#
# build.sh -- build host.exe with the mingw-w64 cross toolchain from WSL.
#
# ----------------------------------------------------------------------
# WHY THIS SCRIPT IS SHAPED THIS WAY
# ----------------------------------------------------------------------
#
# The naive invocation FAILS:
#
#     "/mnt/c/Program Files/mingw64/bin/x86_64-w64-mingw32-gcc.exe" \
#         /tmp/t.c -o /tmp/t.exe
#     x86_64-w64-mingw32-gcc.exe: fatal error: cannot execute 'cc1':
#         CreateProcess: No such file or directory
#
# The usual explanation offered for this error is "the Windows-side exe
# cannot understand the WSL /tmp path". That explanation is WRONG, or at
# least incomplete. Measured facts:
#
#   1. Passing a Windows path also fails:
#        gcc.exe 'D:\...\t.c' -o 'D:\...\t.exe'   -> same cc1 error.
#      So the source path is not the root cause.
#
#   2. `gcc.exe -print-search-dirs` reveals the real cause:
#        install:  D:/03_Work/03_Develop/KeySteam v2.99/../lib/gcc/...
#        programs: D:/03_Work/03_Develop/KeySteam v2.99/../libexec/gcc/...
#      The driver derives its tool and library search roots from argv[0].
#      When WSL launches the Windows binary, argv[0] arrives as the POSIX
#      path "/mnt/c/Program Files/mingw64/bin/x86_64-w64-mingw32-gcc.exe".
#      Windows cannot interpret that, mangles it relative to the current
#      drive, and computes a libexec root that does not exist -- hence
#      cc1 is never found. The source path is irrelevant.
#
#   3. `-B <dir>` overrides those computed roots directly, so the broken
#      argv[0] derivation stops mattering. With -B pointed at libexec,
#      the error changes from "cannot execute 'cc1'" to
#      "cannot execute 'as'" -- proof that cc1 was located and the next
#      stage is now the missing one.
#
#   4. FOUR -B flags are needed, and each one is independently mandatory
#      for this toolchain layout (verified by removing them one at a
#      time):
#
#        -B .../libexec/gcc/x86_64-w64-mingw32/15.1.0/   cc1, collect2
#        -B .../bin/                                     as, ld, nm...
#        -B .../x86_64-w64-mingw32/lib/                  crt2.o, libmingw32.a,
#                                                        -lmsvcrt, -lkernel32
#        -B .../lib/gcc/x86_64-w64-mingw32/15.1.0/       crtbegin.o, crtend.o,
#                                                        -lgcc, -lgcc_eh
#
#      Dropping the fourth produces "cannot find -lgcc / -lgcc_eh";
#      dropping the third produces "cannot find crt2.o / -lmingw32".
#
#   5. The C library headers live under x86_64-w64-mingw32/include and
#      are also lost to the same argv[0] problem, so -I is required as
#      well; without it, `#include <windows.h>` is not found.
#
# A single "-B <mingw64 root>" does NOT work -- -B is a prefix, not a
# recursive search root.
#
# ----------------------------------------------------------------------
# ALTERNATIVE THAT ALSO WORKS (not used here)
# ----------------------------------------------------------------------
#
# Invoking gcc from the Windows side via powershell.exe gives the driver
# a correct argv[0], so no -B flags are needed:
#
#     powershell.exe -NoProfile -Command \
#       "& 'C:\Program Files\mingw64\bin\x86_64-w64-mingw32-gcc.exe' \
#        -municode -O2 host.c -o host.exe"
#
# This script uses the -B route instead because it keeps everything in
# bash, needs no quoting layer, and produces clean exit codes and error
# text directly on the WSL side.
#
# ----------------------------------------------------------------------
# SAFETY
# ----------------------------------------------------------------------
#
# Compiling is safe and is all this script does. It NEVER runs the
# output. Do not execute host.exe against a live Steam installation
# outside an isolated VM.

set -euo pipefail

# ---- Locate the toolchain -------------------------------------------

MINGW_WIN='C:\Program Files\mingw64'
MINGW_WSL='/mnt/c/Program Files/mingw64'

GCC_WSL="$MINGW_WSL/bin/x86_64-w64-mingw32-gcc.exe"
GCC_WIN="$MINGW_WIN\\bin\\x86_64-w64-mingw32-gcc.exe"

# Discover the versioned libexec directory rather than hardcoding 15.1.0,
# so a toolchain upgrade does not silently break the build.
GCC_VER="$(ls -1 "$MINGW_WSL/libexec/gcc/x86_64-w64-mingw32/" 2>/dev/null | sort -V | tail -1)"

if [ -z "$GCC_VER" ]; then
    echo "build.sh: cannot find libexec/gcc/x86_64-w64-mingw32/<version>/" >&2
    echo "build.sh: looked under: $MINGW_WSL/libexec/gcc/x86_64-w64-mingw32/" >&2
    exit 1
fi

if [ ! -x "$GCC_WSL" ]; then
    echo "build.sh: gcc not found at: $GCC_WSL" >&2
    exit 1
fi

echo "build.sh: gcc        = $GCC_WSL"
echo "build.sh: gcc version= $GCC_VER"

# ---- Determine our own location -------------------------------------
#
# Everything is done with Windows-style paths so the driver, its
# subprocesses (cc1, as, ld) and the filesystem all agree on how to
# find the inputs, independent of the current drive or directory.

HOST_DIR_WSL="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_WSL="$HOST_DIR_WSL/host.c"
OUT_WSL="$HOST_DIR_WSL/host.exe"

SRC_WIN="$(wslpath -w "$SRC_WSL")"
OUT_WIN="$(wslpath -w "$OUT_WSL")"

if [ ! -f "$SRC_WSL" ]; then
    echo "build.sh: source not found: $SRC_WSL" >&2
    exit 1
fi

echo "build.sh: source     = $SRC_WIN"
echo "build.sh: output     = $OUT_WIN"

# ---- Assemble the four mandatory -B flags ---------------------------

B_LIBEXEC="$MINGW_WIN\\libexec\\gcc\\x86_64-w64-mingw32\\$GCC_VER\\"
B_BIN="$MINGW_WIN\\bin\\"
B_SYSLIB="$MINGW_WIN\\x86_64-w64-mingw32\\lib\\"
B_GCCLIB="$MINGW_WIN\\lib\\gcc\\x86_64-w64-mingw32\\$GCC_VER\\"
INC_WIN="$MINGW_WIN\\x86_64-w64-mingw32\\include"

# ---- Build ----------------------------------------------------------

set -x

"$GCC_WSL" \
    -municode \
    -O2 \
    -Wall \
    -Wno-expansion-to-defined \
    -Wno-builtin-macro-redefined \
    -Wno-cpp \
    -B "$B_LIBEXEC" \
    -B "$B_BIN" \
    -B "$B_SYSLIB" \
    -B "$B_GCCLIB" \
    -I "$INC_WIN" \
    "$SRC_WIN" \
    -o "$OUT_WIN" \
    -lshell32

set +x

# ---- Report ---------------------------------------------------------

if [ -f "$OUT_WSL" ]; then
    echo
    echo "build.sh: BUILD OK"
    ls -l "$OUT_WSL"
    file "$OUT_WSL" 2>/dev/null || true
else
    echo
    echo "build.sh: BUILD FAILED -- no output produced" >&2
    exit 1
fi
