#!/usr/bin/env python3
"""try_patch.py -- one-shot patch trial harness.

Per trial, exactly this sequence, no shortcuts:

    1. copy the pristine baseline  D:\\ks_debug\\main.dll.orig  ->  harness/main.dll
    2. apply the byte patches IN MEMORY, then write once
    3. run ks_probe.ps1 against the harness copy
    4. parse the probe's final JSON line
    5. print the verdict
    6. restore harness/main.dll from the baseline, always

Step 6 runs in a `finally` block, so an exception, a Ctrl-C, or a probe
timeout still leaves the harness directory in its pristine state. The
baseline and the shared D:\\ks_debug\\main.dll are opened read-only and are
never written to.

Usage
-----
    # single trial
    python3 try_patch.py --desc "patchA jne->jmp" --patch 0xBF1ACE:0x75:0xEB

    # several patches in one trial (same run, all applied)
    python3 try_patch.py --desc "combo" --patch 0xBF1ACE:0x75:0xEB --patch 0xF9923C:0x75:0xEB

    # batch matrix, one probe run per entry
    python3 try_patch.py --matrix matrix.json

Matrix file format
------------------
    {
      "wait": 20,
      "trials": [
        {"desc": "control (no patch)", "patches": []},
        {"desc": "patchA",  "patches": ["0xBF1ACE:0x75:0xEB"]},
        {"desc": "patchB",  "patches": ["0xF9923C:0x75:0xEB"]}
      ]
    }

`patches` accepts either the string form or {"off": ..., "orig": ..., "new": ...}.
An empty patch list is a valid control trial: it runs the pristine baseline
through the identical code path, which is what makes the results comparable.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HARNESS_DLL = Path("/mnt/d/ks_debug/harness/main.dll")
BASELINE = Path("/mnt/d/ks_debug/main.dll.orig")
PROBE_PS1 = Path(
    "/mnt/d/03_Work/03_Develop/KeySteam-v2.99/_re/ghidra/tools/ks_probe.ps1"
)
PWSH = "/mnt/c/Users/<user>/AppData/Local/Microsoft/WindowsApps/pwsh.exe"

PROBE_DLL_WIN = "D:\\ks_debug\\harness\\main.dll"
PROBE_PS1_WIN = (
    "D:\\03_Work\\03_Develop\\KeySteam v2.99\\_re\\ghidra\\tools\\ks_probe.ps1"
)

BASELINE_MD5 = "2948792df5b1484a426580927abb0882"

JSON_LINE = re.compile(r"^\{\"verdict\".*\}$")

# Verdicts that mean "the patch was applied and the module still came up".
# NO_WINDOW is intentionally absent: a module that never builds a window is a
# crash/incomplete-payload outcome, not a usable result.
USABLE = {"DIALOG_PRESENT", "MAIN_INTERACTIVE", "BYPASS_SUCCESS"}


class TrialError(Exception):
    pass


def md5_of(p: Path) -> str:
    import hashlib

    h = hashlib.md5()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_patch(spec) -> tuple[int, int, int]:
    """'0xOFF:0xORIG:0xNEW' or {'off','orig','new'} -> (off, orig, new)."""
    if isinstance(spec, dict):
        off, orig, new = int(spec["off"], 0), int(spec["orig"], 0), int(spec["new"], 0)
    else:
        parts = str(spec).split(":")
        if len(parts) != 3:
            raise TrialError(f"bad patch spec {spec!r}; expected OFF:ORIG:NEW")
        off, orig, new = (int(x, 0) for x in parts)
    if not 0 <= orig <= 0xFF or not 0 <= new <= 0xFF:
        raise TrialError(f"patch byte out of range in {spec!r}")
    return off, orig, new


def apply_patches(src: Path, dst: Path, patches: list, verify_only: bool) -> list[dict]:
    """Copy src -> dst and apply patches. Returns per-patch application records.

    Every original byte is checked against the baseline before anything is
    written, so a bad offset aborts the trial instead of producing a corrupted
    dll that would be misread as "the patch did nothing".
    """
    data = bytearray(src.read_bytes())
    records = []

    for spec in patches:
        off, orig, new = parse_patch(spec)
        if off >= len(data):
            raise TrialError(f"offset 0x{off:X} is past end of file (0x{len(data):X})")
        actual = data[off]
        if actual != orig:
            raise TrialError(
                f"baseline byte mismatch at file 0x{off:X}: baseline has "
                f"0x{actual:02X}, spec declares 0x{orig:02X}"
            )
        if not verify_only:
            data[off] = new
        records.append(
            {"off": off, "orig": orig, "new": new, "applied": new if not verify_only else orig}
        )

    if not verify_only:
        dst.write_bytes(bytes(data))
    return records


def run_probe(wait: int, timeout_s: int) -> dict:
    """Invoke ks_probe.ps1 -Json and return its parsed final JSON line."""
    cmd = [
        PWSH,
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", PROBE_PS1_WIN,
        "-DllPath", PROBE_DLL_WIN,
        "-WaitSec", str(wait),
        "-Json",
    ]
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired:
        raise TrialError(f"probe exceeded {timeout_s}s wall clock")

    lines = [ln.strip() for ln in cp.stdout.splitlines() if ln.strip()]
    for ln in reversed(lines):
        if JSON_LINE.match(ln):
            try:
                return json.loads(ln)
            except json.JSONDecodeError as e:
                raise TrialError(f"probe JSON line unparseable: {e}\n{ln}")
    raise TrialError(
        "probe produced no JSON verdict line\n"
        f"  rc={cp.returncode}\n"
        f"  stdout tail: {lines[-5:]}\n"
        f"  stderr tail: {cp.stderr.strip().splitlines()[-5:]}"
    )


def one_trial(desc: str, patches: list, wait: int, timeout_s: int, keep: bool) -> dict:
    """Full copy -> patch -> probe -> restore cycle for a single trial."""
    if not BASELINE.is_file():
        raise TrialError(f"baseline missing: {BASELINE}")

    base_md5 = md5_of(BASELINE)
    if base_md5 != BASELINE_MD5:
        raise TrialError(
            f"baseline {BASELINE} is not the pristine image: md5 {base_md5} != {BASELINE_MD5}"
        )

    # Verify every patch against the baseline BEFORE touching the harness dir,
    # so a bad spec cannot leave a half-patched harness behind.
    apply_patches(BASELINE, HARNESS_DLL, patches, verify_only=True)

    result = {"desc": desc, "patches": list(patches)}

    try:
        recs = apply_patches(BASELINE, HARNESS_DLL, patches, verify_only=False)
        result["applied"] = recs
        result["harness_md5"] = md5_of(HARNESS_DLL)

        if keep:
            snapshot = HARNESS_DLL.with_suffix(".dll.trial")
            shutil.copy2(HARNESS_DLL, snapshot)
            result["snapshot"] = str(snapshot)

        probe = run_probe(wait, timeout_s)
        result["probe"] = probe
        result["verdict"] = probe.get("verdict", "PARSE_ERROR")
        result["dialog"] = probe.get("dialog")
        result["main_enabled"] = probe.get("main_enabled")
        result["samples"] = probe.get("samples")
        result["ok"] = result["verdict"] in USABLE
    finally:
        # Unconditional restore. This is the whole reason the harness copy
        # exists: the shared baseline and D:\ks_debug\main.dll are never the
        # test subject.
        shutil.copy2(BASELINE, HARNESS_DLL)
        result["harness_restored_md5"] = md5_of(HARNESS_DLL)

    result["harness_restored"] = result["harness_restored_md5"] == BASELINE_MD5
    return result


def print_table(rows: list[dict], wait: int) -> None:
    print()
    print("=" * 108)
    print(f"RESULT TABLE   wait={wait}s   baseline_md5={BASELINE_MD5}")
    print("=" * 108)
    print(f"{'#':<3} {'verdict':<17} {'dlg':<5} {'main_en':<8} {'n':<4} {'md5(patched)':<34} desc")
    print("-" * 108)
    for i, r in enumerate(rows):
        dll_md5 = (r.get("probe") or {}).get("dll_md5", r.get("harness_md5", ""))[:32]
        dlg = str(r.get("dialog"))
        me = str(r.get("main_enabled"))
        n = str(r.get("samples", ""))
        print(f"{i:<3} {str(r.get('verdict','-')):<17} {dlg:<5} {me:<8} {n:<4} {dll_md5:<34} {r['desc']}")
        for spec in r["patches"]:
            print(f"      patch {spec}")
    print("-" * 108)

    bad = [r for r in rows if not r.get("harness_restored")]
    if bad:
        print(f"WARNING {len(bad)} trial(s) failed to restore the harness copy:")
        for r in bad:
            print(f"  {r['desc']}: {r.get('harness_restored_md5')}")
    else:
        print("harness restored to baseline after every trial: OK")

    crashed = [r for r in rows if r.get("verdict") == "NO_WINDOW"]
    if crashed:
        print(f"NOTE {len(crashed)} trial(s) produced NO_WINDOW (module did not come up): "
              + ", ".join(r["desc"] for r in crashed))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="patch trial harness for main.dll")
    ap.add_argument("--desc", help="description for a single trial")
    ap.add_argument("--patch", action="append", default=[], metavar="OFF:ORIG:NEW",
                    help="byte patch on the BASELINE file offsets (repeatable)")
    ap.add_argument("--matrix", metavar="JSON", help="batch file with multiple trials")
    ap.add_argument("--wait", type=int, default=25, help="probe observation seconds (default 25)")
    ap.add_argument("--timeout", type=int, default=0,
                    help="hard wall-clock cap per probe run (default: wait + 60)")
    ap.add_argument("--keep", action="store_true", help="keep a .trial snapshot of each patched dll")
    ap.add_argument("--json", action="store_true", help="emit the full result set as JSON")
    args = ap.parse_args(argv)

    timeout_s = args.timeout if args.timeout > 0 else args.wait + 60

    trials: list[tuple[str, list]] = []
    try:
        if args.matrix:
            mpath = Path(args.matrix)
            if not mpath.is_file():
                print(f"ERROR matrix file not found: {mpath}", file=sys.stderr)
                return 2
            m = json.loads(mpath.read_text(encoding="utf-8"))
            if "wait" in m:
                args.wait = int(m["wait"])
                timeout_s = args.timeout if args.timeout > 0 else args.wait + 60
            for t in m["trials"]:
                trials.append((t.get("desc", "trial"), t.get("patches", [])))
        else:
            if not args.desc and not args.patch:
                print("ERROR pass --desc/--patch, or --matrix", file=sys.stderr)
                return 2
            trials.append((args.desc or "trial", args.patch))
    except (json.JSONDecodeError, KeyError) as e:
        print(f"ERROR matrix file malformed: {e}", file=sys.stderr)
        return 2

    rows: list[dict] = []
    for i, (desc, patches) in enumerate(trials):
        print(f"[{i+1}/{len(trials)}] {desc}  patches={len(patches)}", file=sys.stderr, flush=True)
        try:
            rows.append(one_trial(desc, patches, args.wait, timeout_s, args.keep))
        except TrialError as e:
            print(f"  FAILED: {e}", file=sys.stderr)
            # Even a failed trial must leave the harness pristine.
            try:
                shutil.copy2(BASELINE, HARNESS_DLL)
            except OSError:
                pass
            rows.append({"desc": desc, "patches": list(patches), "verdict": "TRIAL_ERROR",
                         "error": str(e), "harness_restored": True})

    if args.json:
        print(json.dumps({"baseline_md5": BASELINE_MD5, "wait": args.wait, "trials": rows}, indent=2))
    else:
        print_table(rows, args.wait)

    if any(r.get("verdict") in ("TRIAL_ERROR", "PARSE_ERROR") for r in rows):
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
