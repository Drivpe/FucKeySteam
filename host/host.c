/*
 * host.c -- minimal native host for the Nuitka onefile business module.
 *
 * Loads `main.dll` from the payload directory, resolves the `run_code`
 * export and invokes it with THREE arguments:
 *
 *     int run_code(int argc, wchar_t **argv, wchar_t **envp)
 *
 * The common `nuitka-dll-bootloader/boot.c` two-argument form
 * `(int, wchar_t**)` appears to work only because the x64 Microsoft ABI
 * leaves r8 holding a stale stack value; the callee's `test r8, r8`
 * then happens to skip the envp branch and the envp injection is
 * silently dropped. This host always supplies r8.
 *
 * WIDE CHARACTERS: argv and envp are wchar_t** (UTF-16LE), never char**.
 *
 * ---------------------------------------------------------------------
 * BUILD
 * ---------------------------------------------------------------------
 * This file is built with mingw-w64 for Windows. It compiles cleanly as
 * a console subsystem PE32+ x86-64 executable. See build.sh for the
 * exact command line and the four -B flags that are mandatory when
 * invoking the mingw driver from WSL.
 *
 * ---------------------------------------------------------------------
 * RUN (human operator, isolated VM only)
 * ---------------------------------------------------------------------
 *     host.exe --dll "D:\path\to\payload\main.dll"
 *
 * The sample must never be executed on a machine whose Steam account
 * matters. See README.md.
 */

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>

/* ------------------------------------------------------------------ */
/* Tunables                                                            */
/* ------------------------------------------------------------------ */

/* Name of the business module inside the payload directory.
 *
 * DIAGNOSTIC ONLY -- this is no longer passed to LoadLibraryExW. It was,
 * and that was the bug: `LoadLibraryExW(PAYLOAD_DLL_NAME, NULL, 0xD00)`
 * fails with ERROR_INVALID_PARAMETER (87), because
 * LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR requires lpLibFileName to be a fully
 * qualified path. See the block comment at the load site. The load now
 * uses the resolved absolute path instead. */
#define PAYLOAD_DLL_NAME L"main.dll"

/* argv[0] handed to run_code. MUST end in ".py" (case-insensitive).
 *
 * This is the entire mechanism of the host: A .py-suffixed argv[0] is
 * load-bearing, not cosmetic. It does not need to exist on disk.
 *
 * WHERE THE SUFFIX CHECK ACTUALLY LIVES (corrected 2026-09-15):
 *
 * An earlier revision of this comment said "the module strips and
 * casefolds argv[0] ... which disables the integrity self-check",
 * implying the check is part of Nuitka's C runtime. That attribution is
 * WRONG, and it matters, because it sends a reader looking in the wrong
 * source tree.
 *
 * Measured facts:
 *   - grep -rn 'pyw\|\.py"' over Nuitka's MainProgram.c,
 *     OnefileBootstrap.c and HelpersFilesystemPaths.c returns ZERO
 *     matches. Nuitka's C runtime has no suffix branch at all.
 *   - OnefileBootstrap.c only ever assigns argv[0] from getBinaryPath()
 *     (lines 868, 1016, 1359, 1454-1455).
 *   - run_code forwards argv unchanged to Nuitka_Main
 *     (MainProgram.c:2396-2403), which overwrites argv[0] from
 *     getBinaryFilename* and otherwise ignores it.
 *   - The suffix test lives in the SAMPLE'S OWN compiled Python code,
 *     which is packed into main.dll. It was found by reading the
 *     sample's rdata: the constant tuple
 *         P\x02u.py\0u.pyw\0        (VA 0x01cd04d0)
 *     See docs/host-contract.md:143-151, which already recorded this
 *     correctly as a measurement against the sample.
 *
 * So: the suffix check is a property of the SAMPLE, not of Nuitka. The
 * mechanism works, but it is unobservable from the host side -- there is
 * no intermediate state the host can inspect to confirm the branch was
 * taken. The only evidence is the final dialog behaviour. */
#define PAYLOAD_SCRIPT_NAME L"KeySteam.py"

/* Environment variables the outer KeySteam.exe sets for the payload. */
#define ENV_DIRECTORY L"NUITKA_ONEFILE_DIRECTORY"
#define ENV_ARGV0 L"NUITKA_ORIGINAL_ARGV0"

/* ------------------------------------------------------------------ */
/* Small helpers                                                       */
/* ------------------------------------------------------------------ */

static void fail(const wchar_t *what)
{
    DWORD err = GetLastError();

    fwprintf(stderr, L"[host] FATAL: %ls failed\n", what);
    fwprintf(stderr, L"[host]   GetLastError() = %lu (0x%08lX)\n",
             (unsigned long)err, (unsigned long)err);

    /* FormatMessageW gives the human-readable text for the code. */
    LPWSTR text = NULL;
    DWORD n = FormatMessageW(
        FORMAT_MESSAGE_ALLOCATE_BUFFER | FORMAT_MESSAGE_FROM_SYSTEM |
            FORMAT_MESSAGE_IGNORE_INSERTS,
        NULL, err, MAKELANGID(LANG_NEUTRAL, SUBLANG_DEFAULT),
        (LPWSTR)&text, 0, NULL);

    if (n && text) {
        /* Collapse the trailing CRLF that the system message carries. */
        while (n > 0 && (text[n - 1] == L'\r' || text[n - 1] == L'\n'))
            text[--n] = L'\0';
        fwprintf(stderr, L"[host]   %ls\n", text);
    } else {
        fwprintf(stderr, L"[host]   (no system message text available)\n");
    }
    if (text)
        LocalFree(text);

    fflush(stderr);
}

/* Strip the trailing path separator from a directory path, in place. */
static void strip_trailing_sep(wchar_t *dir)
{
    size_t len = wcslen(dir);
    while (len > 0 && (dir[len - 1] == L'\\' || dir[len - 1] == L'/'))
        dir[--len] = L'\0';
}

/* ------------------------------------------------------------------ */
/* Direction derivation                                                */
/* ------------------------------------------------------------------ */

/* Given the full path of main.dll, derive the containing directory.
 * Returns a newly allocated string or NULL. */
static wchar_t *dir_of(const wchar_t *file_path)
{
    size_t len = wcslen(file_path);
    wchar_t *dir = (wchar_t *)malloc((len + 1) * sizeof(wchar_t));
    if (!dir)
        return NULL;
    memcpy(dir, file_path, (len + 1) * sizeof(wchar_t));

    wchar_t *last = wcsrchr(dir, L'\\');
    wchar_t *last_fwd = wcsrchr(dir, L'/');
    if (last_fwd && (!last || last_fwd > last))
        last = last_fwd;

    if (last)
        *last = L'\0';
    else
        dir[0] = L'\0';

    strip_trailing_sep(dir);
    return dir;
}

/* ------------------------------------------------------------------ */
/* main                                                                */
/* ------------------------------------------------------------------ */

int wmain(int argc, wchar_t **argv_in)
{
    int inject_env = 1;   /* default: set the two NUITKA_* variables */
    int pass_third = 1;   /* default: third argument = absolute dll path */
    const wchar_t *dll_arg = NULL;
    int status;

    /* ---- Parse our own command line -------------------------------- */

    for (int i = 1; i < argc; i++) {
        if (wcscmp(argv_in[i], L"--no-envp") == 0) {
            inject_env = 0;
        } else if (wcscmp(argv_in[i], L"--null-3rd") == 0) {
            pass_third = 0;
        } else if (wcscmp(argv_in[i], L"--dll") == 0 && i + 1 < argc) {
            dll_arg = argv_in[++i];
        } else if (wcscmp(argv_in[i], L"--help") == 0 ||
                   wcscmp(argv_in[i], L"-h") == 0) {
            fwprintf(stderr,
                     L"usage: host.exe --dll <path\\to\\main.dll> "
                     L"[--no-envp] [--null-3rd] [args...]\n"
                     L"  --no-envp   do NOT set NUITKA_ONEFILE_DIRECTORY /\n"
                     L"              NUITKA_ORIGINAL_ARGV0 in the process env\n"
                     L"  --null-3rd  pass NULL as run_code's third argument\n"
                     L"              (control run; the third argument is main.dll's\n"
                     L"               path, not an environment block)\n"
                     L"  args...     forwarded to run_code after argv[0]\n"
                     L"\n"
                     L"The two switches are INDEPENDENT. --no-envp alone no longer\n"
                     L"also nulls the third argument, so each can be varied alone.\n");
            return 0;
        } else {
            /* First non-switch token: treat as the dll path if not yet
             * set, otherwise it is a passthrough argument. */
            if (!dll_arg && wcsstr(argv_in[i], L".dll")) {
                dll_arg = argv_in[i];
            }
        }
    }

    if (!dll_arg) {
        fwprintf(stderr, L"[host] FATAL: no DLL path given\n");
        fwprintf(stderr, L"[host] usage: host.exe --dll <path\\to\\main.dll> "
                         L"[--no-envp] [--null-3rd] [args...]\n");
        return 2;
    }

    /* ---- Derive the payload directory ------------------------------ */

    wchar_t *dll_path = _wcsdup(dll_arg);
    wchar_t *dir = dir_of(dll_path);
    if (!dll_path || !dir) {
        fwprintf(stderr, L"[host] FATAL: out of memory\n");
        return 2;
    }
    strip_trailing_sep(dir);

    if (dir[0] == L'\0') {
        /* Relative DLL name with no directory component: fall back to
         * the host executable's own directory. */
        wchar_t self[MAX_PATH];
        DWORD n = GetModuleFileNameW(NULL, self, MAX_PATH);
        if (n == 0 || n >= MAX_PATH) {
            fail(L"GetModuleFileNameW");
            return 2;
        }
        free(dir);
        dir = dir_of(self);
    }

    fwprintf(stderr, L"[host] dll      = %ls\n", dll_path);
    fwprintf(stderr, L"[host] payload  = %ls\n", dir);
    fwprintf(stderr, L"[host] switches = env:%ls  third:%ls\n",
             inject_env ? L"inject" : L"skip",
             pass_third ? L"dll path" : L"NULL (control run)");

    /* ---- Load the module ------------------------------------------- *
     *
     * main.dll statically imports python312.dll plus KERNEL32,
     * VCRUNTIME140 and seven api-ms-win-crt-* stubs. Those dependencies
     * MUST resolve out of the payload directory, not from wherever the
     * host happens to live, or the load either fails or binds the wrong
     * Python runtime.
     *
     * Two steps:
     *
     *   1. AddDllDirectory(payload_dir) registers the payload directory
     *      as a user directory.
     *   2. LoadLibraryExW is called with
     *        LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR   0x00000100
     *        LOAD_LIBRARY_SEARCH_USER_DIRS      0x00000400
     *        LOAD_LIBRARY_SEARCH_SYSTEM32       0x00000800
     *      The three OR together to 0xD00.
     *
     * ---- WHY lpLibFileName IS THE FULL PATH (fixed 2026-09-15) -------
     *
     * An earlier revision passed the bare name L"main.dll" here and
     * failed at runtime with:
     *
     *     LoadLibraryExW(main.dll) failed
     *     GetLastError() = 87 (0x00000057)  == ERROR_INVALID_PARAMETER
     *
     * Error 87 is a parameter-validation failure, not a lookup failure
     * (that would be 2, ERROR_FILE_NOT_FOUND). The cause is documented:
     *
     *   LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR, 0x00000100 --
     *     "If this value is used, the directory that contains the DLL is
     *      temporarily added to the beginning of the list of directories
     *      that are searched for the DLL's dependencies. ... The
     *      lpFileName parameter must specify a fully qualified path."
     *        -- learn.microsoft.com/windows/win32/api/libloaderapi/
     *           nf-libloaderapi-loadlibraryexw
     *
     * So that flag is illegal with a bare name, and it was ALSO being
     * misunderstood: it searches for the DLL's *dependencies* in the
     * DLL's directory; it does not locate the DLL itself. With a bare
     * name the loader would have searched the current working directory
     * for main.dll -- exactly the "bind the wrong runtime" failure this
     * whole block exists to prevent.
     *
     * Passing dll_path (the fully qualified path we were given, or
     * derived) fixes both problems at once: the flag is now legal, and
     * the DLL is located by absolute path rather than by cwd.
     *
     * The AddDllDirectory call below needs no SetDefaultDllDirectories
     * first. Documented, from the AddDllDirectory page:
     *
     *   "If SetDefaultDllDirectories is first called with
     *    LOAD_LIBRARY_SEARCH_USER_DIRS, directories specified with
     *    AddDllDirectory are added to the process DLL search path.
     *    Otherwise, directories specified with the AddDllDirectory
     *    function are used only for LoadLibraryEx function calls that
     *    specify LOAD_LIBRARY_SEARCH_USER_DIRS."
     *
     * We do specify USER_DIRS, so the bare AddDllDirectory is the
     * documented, supported combination -- and it avoids changing DLL
     * resolution for every subsequent load in this process.
     *
     * LOAD_WITH_ALTERED_SEARCH_PATH (0x8) is deliberately NOT used: it
     * cannot be combined with the LOAD_LIBRARY_SEARCH_* flags.
     */
    if (!AddDllDirectory(dir)) {
        /* Non-fatal in the sense that LOAD_LIBRARY_SEARCH_USER_DIRS
         * simply has no directory to search if this failed -- the other
         * two flags may still suffice. But report it. */
        fwprintf(stderr, L"[host] WARN: AddDllDirectory failed\n");
        fail(L"AddDllDirectory");
    }

    DWORD flags = LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR |
                  LOAD_LIBRARY_SEARCH_SYSTEM32 |
                  LOAD_LIBRARY_SEARCH_USER_DIRS;

    /* dll_path, not PAYLOAD_DLL_NAME -- see the block comment above.
     * This matches Nuitka's own call site (OnefileBootstrap.c:937),
     * which passes the fully qualified dll_filename and never a bare
     * name. */
    HMODULE mod = LoadLibraryExW(dll_path, NULL, flags);
    if (!mod) {
        fail(L"LoadLibraryExW(main.dll)");
        fwprintf(stderr,
                 L"[host] hint: confirm main.dll and python312.dll both "
                 L"live in %ls\n", dir);
        return 3;
    }

    /* ---- Resolve the entry point ----------------------------------- */

    /* The third parameter is NOT an environment block. It is the
     * absolute path of main.dll, passed as a single NUL-terminated wide
     * string; the callee stores the pointer in a global
     * (_pseudo_dll_filename) and later copies it out character by
     * character.
     *
     * Evidence:
     *   - Nuitka's OnefileBootstrap.c declares the pointer as
     *     int(__stdcall *)(int, wchar_t **, wchar_t const *) and calls
     *     it as run_code(argc, argv, dll_filename).
     *   - MainProgram.c receives it as filename_char_t const * and does
     *     `if (dll_filename != NULL) setDllFilename(dll_filename);`.
     *   - The compiled setDllFilename is two instructions
     *     (mov [rip+...],rcx / ret) -- it stores the pointer, nothing more.
     *   - The consumer copies with
     *         movzx eax, WORD PTR [rcx] / mov WORD PTR [rdx],ax
     *     stepping 2 bytes at a time and stopping at a single NUL. One
     *     level of indirection only -- a pointer array would need two.
     *
     * Passing an environment array here (as an earlier revision of this
     * file did) means the callee reads the array's first slot as if it
     * were character data. That does not crash; it silently yields a
     * garbage path. Pass the DLL path. */
    typedef int (*run_code_fn)(int, wchar_t **, const wchar_t *);

    run_code_fn run_code = (run_code_fn)(void *)GetProcAddress(mod, "run_code");
    if (!run_code) {
        fwprintf(stderr,
                 L"[host] FATAL: GetProcAddress(main.dll, \"run_code\") "
                 L"returned NULL\n");
        fail(L"GetProcAddress");
        fwprintf(stderr, L"[host] hint: the export name may differ or the "
                         L"module may export only an ordinal\n");
        FreeLibrary(mod);
        return 4;
    }
    fwprintf(stderr, L"[host] run_code @ %p\n", (void *)run_code);

    /* ---- Build argv ------------------------------------------------ *
     *
     * argv[0] MUST end in ".py". The SAMPLE (not Nuitka -- see the note
     * at PAYLOAD_SCRIPT_NAME) strips and casefolds it and compares
     * against (".py", ".pyw") to conclude it is running from source,
     * which turns off the integrity self-check.
     *
     * Remaining arguments are forwarded from our own command line,
     * skipping host.exe and any host-level switches.
     *
     * NOTE ON OBSERVABILITY: because that branch lives in the sample's
     * own Python code, this host gets no feedback about whether it was
     * taken. There is no intermediate state to print. Do not expect a
     * "[host] integrity skipped" line -- it cannot exist. */
    size_t script_len = wcslen(dir) + 1 + wcslen(PAYLOAD_SCRIPT_NAME);
    wchar_t *argv0 = (wchar_t *)malloc((script_len + 1) * sizeof(wchar_t));
    if (!argv0) {
        fwprintf(stderr, L"[host] FATAL: out of memory\n");
        return 2;
    }
    swprintf(argv0, script_len + 1, L"%ls\\%ls", dir, PAYLOAD_SCRIPT_NAME);

    int fwd_count = 0;
    for (int i = 1; i < argc; i++) {
        if (wcscmp(argv_in[i], L"--no-envp") == 0)
            continue;
        if (wcscmp(argv_in[i], L"--null-3rd") == 0)
            continue;
        if (wcscmp(argv_in[i], L"--dll") == 0) {
            i++; /* also skip its value */
            continue;
        }
        fwd_count++;
    }

    /* argv0 + forwarded + NULL */
    wchar_t **child_argv =
        (wchar_t **)calloc((size_t)fwd_count + 2, sizeof(wchar_t *));
    if (!child_argv) {
        fwprintf(stderr, L"[host] FATAL: out of memory\n");
        return 2;
    }
    child_argv[0] = argv0;
    int ci = 1;
    for (int i = 1; i < argc; i++) {
        if (wcscmp(argv_in[i], L"--no-envp") == 0)
            continue;
        if (wcscmp(argv_in[i], L"--null-3rd") == 0)
            continue;
        if (wcscmp(argv_in[i], L"--dll") == 0) {
            i++;
            continue;
        }
        child_argv[ci++] = argv_in[i];
    }
    child_argv[ci] = NULL;

    fwprintf(stderr, L"[host] argc     = %d\n", ci);
    for (int i = 0; i < ci; i++)
        fwprintf(stderr, L"[host]   argv[%d] = %ls\n", i, child_argv[i]);

    /* ---- Environment variables ------------------------------------- *
     *
     * These go into the PROCESS environment, not into run_code's third
     * parameter -- that parameter carries the DLL path (see above).
     *
     *   NUITKA_ONEFILE_DIRECTORY = directory containing the HOST
     *       executable. Nuitka sets this to
     *       stripBaseFilename(getBinaryFilenameWideChars(false)), which
     *       is the binary's own directory -- not the payload directory.
     *
     *   NUITKA_ORIGINAL_ARGV0    = value for __compiled__.original_argv0.
     *       Optional: if unset, Nuitka falls back to the argv[0] we pass.
     *       Set it to make original_argv0 name the host rather than the
     *       script path we hand to argv[0].
     *
     * Both are opt-out via --no-envp, INDEPENDENTLY of the third argument
     * (which --null-3rd controls). Vary one at a time. */
    if (inject_env) {
        wchar_t self[MAX_PATH];
        DWORD n = GetModuleFileNameW(NULL, self, MAX_PATH);
        wchar_t *host_dir = (n && n < MAX_PATH) ? dir_of(self) : NULL;

        if (host_dir) {
            strip_trailing_sep(host_dir);
            if (!SetEnvironmentVariableW(ENV_DIRECTORY, host_dir))
                fail(L"SetEnvironmentVariableW(NUITKA_ONEFILE_DIRECTORY)");
            fwprintf(stderr, L"[host]   %ls=%ls\n", ENV_DIRECTORY, host_dir);
            free(host_dir);
        } else {
            fwprintf(stderr, L"[host] WARN: could not determine host "
                             L"directory; %ls unset\n", ENV_DIRECTORY);
        }

        if (!SetEnvironmentVariableW(ENV_ARGV0, child_argv[0]))
            fail(L"SetEnvironmentVariableW(NUITKA_ORIGINAL_ARGV0)");
        fwprintf(stderr, L"[host]   %ls=%ls\n", ENV_ARGV0, child_argv[0]);
    }

    /* ---- Invoke ---------------------------------------------------- *
     *
     * The third argument is the absolute path to main.dll. Passing NULL
     * instead (--null-3rd) does not crash: the callee skips
     * setDllFilename and _pseudo_dll_filename stays NULL, so
     * getBinaryFilenameWideChars falls through to
     * GetModuleFileNameW(NULL, ...) and reports main.dll's own path.
     * That is a valid control run for isolating the parameter's effect.
     *
     * --null-3rd is INDEPENDENT of --no-envp. The original host tied both
     * to one flag, so the "control run" varied two things at once and
     * neither could be attributed. Missing this is the trap: a compound
     * diff read as a single-variable result.
     */
    const wchar_t *third = pass_third ? dll_path : NULL;

    fwprintf(stderr, L"[host] calling run_code(argc=%d, argv=%p, dll=%ls)\n",
             ci, (void *)child_argv, third ? third : L"NULL");
    fflush(stderr);

    status = run_code(ci, child_argv, third);

    fwprintf(stderr, L"[host] run_code returned %d\n", status);

    /* ---- Exit with the callee's status verbatim -------------------- */

    return status;
}
