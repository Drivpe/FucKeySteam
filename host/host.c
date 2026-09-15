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

/* Name of the business module inside the payload directory. */
#define PAYLOAD_DLL_NAME L"main.dll"

/* argv[0] handed to run_code. MUST end in ".py" (case-insensitive).
 *
 * This is the entire mechanism of the host: the module strips and
 * casefolds argv[0] and compares it against (".py", ".pyw") to decide
 * that it is running "from source", which disables the integrity
 * self-check. A .py-suffixed argv[0] is therefore load-bearing, not
 * cosmetic. It does not need to exist on disk. */
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
/* Environment block -> wchar_t** array                                */
/* ------------------------------------------------------------------ */

/* Duplicate the current process environment into a heap wchar_t** array
 * so we can append/override entries.
 *
 * The block returned by GetEnvironmentStringsW is a run of
 * NAME=VALUE\0 strings terminated by one extra \0. Callers must release
 * it with FreeEnvironmentStringsW, *not* free().
 *
 * On success *out_count receives the number of non-NULL entries (the
 * array itself is NULL-terminated, so its allocation is count+1 slots).
 * Returns NULL on failure with the array left unallocated. */
static wchar_t **dup_env_block(size_t *out_count)
{
    LPWCH block = GetEnvironmentStringsW();
    if (!block) {
        *out_count = 0;
        return NULL;
    }

    /* Pass 1: count entries. Skip the odd "=C:=C:\..." pseudo-variables,
     * which are legal to carry through but carry no useful meaning for
     * a Python child; dropping them avoids surprises in os.environ. */
    size_t count = 0;
    for (LPWCH p = block; *p; p += wcslen(p) + 1) {
        if (*p != L'=')
            count++;
    }

    /* count entries + trailing NULL. */
    wchar_t **env = (wchar_t **)calloc(count + 1, sizeof(wchar_t *));
    if (!env) {
        FreeEnvironmentStringsW(block);
        *out_count = 0;
        return NULL;
    }

    /* Pass 2: copy each string. */
    size_t i = 0;
    for (LPWCH p = block; *p; p += wcslen(p) + 1) {
        if (*p == L'=')
            continue;
        size_t len = wcslen(p);
        wchar_t *s = (wchar_t *)malloc((len + 1) * sizeof(wchar_t));
        if (!s) {
            for (size_t k = 0; k < i; k++)
                free(env[k]);
            free(env);
            FreeEnvironmentStringsW(block);
            *out_count = 0;
            return NULL;
        }
        memcpy(s, p, (len + 1) * sizeof(wchar_t));
        env[i++] = s;
    }
    env[i] = NULL;

    FreeEnvironmentStringsW(block);
    *out_count = i;
    return env;
}

/* Append (or override) NAME=VALUE in a NULL-terminated wchar_t** array.
 * Returns a newly allocated array; the caller frees the array and the
 * strings. On failure returns NULL and leaves *array untouched. */
static wchar_t **env_set(wchar_t **array, size_t count,
                         const wchar_t *name, const wchar_t *value)
{
    size_t name_len = wcslen(name);
    size_t value_len = wcslen(value);

    wchar_t **out = (wchar_t **)calloc(count + 2, sizeof(wchar_t *));
    if (!out)
        return NULL;

    size_t out_n = 0;
    for (size_t i = 0; i < count; i++) {
        const wchar_t *e = array[i];
        /* Override: drop any existing entry with this name. */
        if (wcsncmp(e, name, name_len) == 0 && e[name_len] == L'=')
            continue;
        out[out_n++] = _wcsdup(e);
    }

    /* Build NAME=VALUE. */
    size_t total = name_len + 1 + value_len;
    wchar_t *pair = (wchar_t *)malloc((total + 1) * sizeof(wchar_t));
    if (!pair) {
        for (size_t k = 0; k < out_n; k++)
            free(out[k]);
        free(out);
        return NULL;
    }
    memcpy(pair, name, name_len * sizeof(wchar_t));
    pair[name_len] = L'=';
    memcpy(pair + name_len + 1, value, (value_len + 1) * sizeof(wchar_t));

    out[out_n++] = pair;
    out[out_n] = NULL;
    return out;
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
    int use_envp = 1;          /* default: full envp */
    const wchar_t *dll_arg = NULL;
    int status;

    /* ---- Parse our own command line -------------------------------- */

    for (int i = 1; i < argc; i++) {
        if (wcscmp(argv_in[i], L"--no-envp") == 0) {
            use_envp = 0;
        } else if (wcscmp(argv_in[i], L"--dll") == 0 && i + 1 < argc) {
            dll_arg = argv_in[++i];
        } else if (wcscmp(argv_in[i], L"--help") == 0 ||
                   wcscmp(argv_in[i], L"-h") == 0) {
            fwprintf(stderr,
                     L"usage: host.exe --dll <path\\to\\main.dll> "
                     L"[--no-envp] [args...]\n"
                     L"  --no-envp   pass NULL as run_code's third argument\n"
                     L"  args...     forwarded to run_code after argv[0]\n");
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
                         L"[--no-envp] [args...]\n");
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
    fwprintf(stderr, L"[host] payloadd = %ls\n", dir);
    fwprintf(stderr, L"[host] envp     = %ls\n",
             use_envp ? L"full (3 args)" : L"NULL (2 args, --no-envp)");

    /* ---- Load the module ------------------------------------------- *
     *
     * main.dll statically imports python312.dll plus KERNEL32,
     * VCRUNTIME140 and seven api-ms-win-crt-* stubs. Those dependencies
     * MUST resolve out of the payload directory, not from wherever the
     * host happens to live, or the load either fails or binds the wrong
     * Python runtime.
     *
     * Two steps, mirroring Nuitka's own OnefileBootstrap.c:
     *
     *   1. AddDllDirectory(payload_dir) registers the payload directory
     *      as a user directory.
     *   2. LoadLibraryExW is called with
     *        LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR   0x00000100
     *          -- also search the directory the DLL itself came from
     *        LOAD_LIBRARY_SEARCH_USER_DIRS      0x00000400
     *          -- search directories added via AddDllDirectory
     *        LOAD_LIBRARY_SEARCH_SYSTEM32       0x00000800
     *          -- always allow system32 for the OS itself
     *      The three OR together to 0xD00.
     *
     * AddDllDirectory normally requires SetDefaultDllDirectories, but
     * passing LOAD_LIBRARY_SEARCH_USER_DIRS explicitly satisfies the
     * precondition per-process for this one call. We deliberately take
     * that route: SetDefaultDllDirectories would change DLL resolution
     * for every subsequent load in this process, a side effect we do
     * not need here.
     *
     * LOAD_WITH_ALTERED_SEARCH_PATH (0x8) is deliberately NOT used: it
     * cannot be combined with the LOAD_LIBRARY_SEARCH_* flags.
     */
    if (!AddDllDirectory(dir)) {
        /* Non-fatal in the sense that LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR
         * alone often suffices -- but report it. */
        fwprintf(stderr, L"[host] WARN: AddDllDirectory failed\n");
        fail(L"AddDllDirectory");
    }

    DWORD flags = LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR |
                  LOAD_LIBRARY_SEARCH_SYSTEM32 |
                  LOAD_LIBRARY_SEARCH_USER_DIRS;

    HMODULE mod = LoadLibraryExW(PAYLOAD_DLL_NAME, NULL, flags);
    if (!mod) {
        fail(L"LoadLibraryExW(main.dll)");
        fwprintf(stderr,
                 L"[host] hint: confirm main.dll and python312.dll both "
                 L"live in %ls\n", dir);
        return 3;
    }

    /* ---- Resolve the entry point ----------------------------------- */

    typedef int (*run_code_fn)(int, wchar_t **, wchar_t **);

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
     * argv[0] MUST end in ".py". The payload strips and casefolds it
     * and compares against (".py", ".pyw") to conclude it is running
     * from source, which turns off the integrity self-check.
     *
     * Remaining arguments are forwarded from our own command line,
     * skipping host.exe and any host-level switches.
     */
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

    /* ---- Build envp ------------------------------------------------ *
     *
     * Two variables, matching the outer KeySteam.exe:
     *
     *   NUITKA_ONEFILE_DIRECTORY = fully qualified payload directory
     *   NUITKA_ORIGINAL_ARGV0    = the original argv[0]
     */
    wchar_t **child_env = NULL;

    if (use_envp) {
        size_t env_count = 0;
        wchar_t **base = dup_env_block(&env_count);
        if (!base) {
            fail(L"GetEnvironmentStringsW");
            return 5;
        }

        wchar_t **e1 = env_set(base, env_count, ENV_DIRECTORY, dir);
        if (!e1) {
            fwprintf(stderr, L"[host] FATAL: out of memory (envp)\n");
            return 5;
        }

        wchar_t **e2 = env_set(e1, env_count + 1, ENV_ARGV0, argv0);
        if (!e2) {
            fwprintf(stderr, L"[host] FATAL: out of memory (envp)\n");
            return 5;
        }

        child_env = e2;
        fwprintf(stderr, L"[host]   %ls=%ls\n", ENV_DIRECTORY, dir);
        fwprintf(stderr, L"[host]   %ls=%ls\n", ENV_ARGV0, argv0);
    }

    /* ---- Invoke ---------------------------------------------------- *
     *
     * Do NOT run this against a real target outside an isolated VM.
     */
    fwprintf(stderr, L"[host] calling run_code(argc=%d, argv=%p, envp=%ls)\n",
             ci, (void *)child_argv, use_envp ? L"<array>" : L"NULL");
    fflush(stderr);

    status = run_code(ci, child_argv, child_env);

    fwprintf(stderr, L"[host] run_code returned %d\n", status);

    /* ---- Exit with the callee's status verbatim -------------------- */

    return status;
}
