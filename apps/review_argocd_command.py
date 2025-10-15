# review_argocd_command.py
"""
Argocd command reviewer: validates subcommands and flags by walking `--help` trees
and parsing "Available Commands", "Flags", "Global Flags", plus "Usage:" to infer
required/optional positionals.

Usage from your code:
    from review_argocd_command import review_command
    res = review_command("argocd app manifest --app myapp -n argocd", logger=logger)
    # res is a dict with keys: valid, errors, warnings, suggestions, corrected_command, ...

This file includes a built-in `execute_run_command()` to avoid external imports.
"""

import re
import os
import shlex
import difflib
import subprocess
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Set, Tuple

# =========================================
# Local runner (replaces execute_run_command)
# =========================================
def execute_run_command(cmd: str, logger=None, timeout: float = 15.0, cwd: Optional[str] = None) -> Dict[str, object]:
    """
    Execute a shell command safely and return {exit_code, stdout, stderr}.
    - No TTY / paging (PAGER=cat, GIT_PAGER=cat) to avoid hangs in MSYS/Git Bash.
    - Closes stdin; enforces timeout.
    - On Windows, if command starts with 'argocd ' and lookup fails, tries 'argocd.exe'.
    """
    if logger:
        logger.debug("execute_run_command: %s", cmd)

    try:
        argv = shlex.split(cmd)
    except ValueError as e:
        return {"exit_code": 127, "stdout": "", "stderr": f"shlex error: {e}"}

    # Windows convenience: try argocd.exe if "argocd" isn't directly on PATH
    if os.name == "nt" and argv and argv[0].lower() == "argocd":
        if not _is_executable_on_path(argv[0]):
            exe = "argocd.exe"
            if _is_executable_on_path(exe):
                argv[0] = exe
                if logger:
                    logger.debug("execute_run_command: using %s", exe)

    env = os.environ.copy()
    env.setdefault("PAGER", "cat")
    env.setdefault("GIT_PAGER", "cat")
    env.setdefault("CI", "true")

    try:
        creationflags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=env,
            shell=False,
            creationflags=creationflags
        )
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except Exception:
                pass
            out, err = proc.communicate()
            return {
                "exit_code": 124,
                "stdout": out.decode(errors="replace") if out else "",
                "stderr": (err.decode(errors="replace") if err else "") + "\n[timeout]",
            }

        return {
            "exit_code": proc.returncode,
            "stdout": out.decode(errors="replace") if out else "",
            "stderr": err.decode(errors="replace") if err else "",
        }
    except FileNotFoundError as e:
        return {"exit_code": 127, "stdout": "", "stderr": str(e)}
    except Exception as e:
        return {"exit_code": 1, "stdout": "", "stderr": f"{type(e).__name__}: {e}"}

def _is_executable_on_path(prog: str) -> bool:
    paths = os.environ.get("PATH", "").split(os.pathsep)
    exts = [""] if os.name != "nt" else os.environ.get("PATHEXT", ".EXE;.BAT;.CMD").split(";")
    for p in paths:
        candidate = os.path.join(p, prog)
        for ext in exts:
            path = candidate + ext
            if os.path.isfile(path) and os.access(path, os.X_OK):
                return True
    return False

# =========================================
# Command review
# =========================================

@dataclass
class FlagInfo:
    names: Set[str]           # e.g. {"-h", "--help"}
    takes_value: bool         # True if flag expects a value
    canonical: str            # choose a stable canonical form (long if available)

@dataclass
class HelpInfo:
    subcommands: Set[str]
    flags: Dict[str, 'FlagInfo']
    global_flags: Dict[str, 'FlagInfo']
    required_positionals: List[str]       # from Usage: unbracketed ALLCAPS tokens
    optional_positionals: List[str]       # from Usage: bracketed ALLCAPS tokens

@dataclass
class ReviewResult:
    valid: bool
    errors: List[str]
    warnings: List[str]
    corrected_command: Optional[str]
    parsed_path: List[str]            # e.g. ["argocd", "app", "manifests"]
    unknown_flags: List[str]
    missing_flag_values: List[str]
    suggestions: List[str]

    def to_dict(self):
        return asdict(self)

def review_command(command: str, logger=None) -> Dict:
    if logger:
        logger.debug("Reviewing command: %s", command)

    tokens = shlex.split(command)
    result = ReviewResult(
        valid=False,
        errors=[],
        warnings=[],
        corrected_command=None,
        parsed_path=[],
        unknown_flags=[],
        missing_flag_values=[],
        suggestions=[],
    )

    if not tokens:
        result.errors.append("Empty command.")
        return result.to_dict()

    if tokens[0] != "argocd":
        result.errors.append("Command must start with 'argocd'.")
        return result.to_dict()

    # progressive descent through help trees
    path = ["argocd"]
    help_cache: Dict[Tuple[str, ...], HelpInfo] = {}
    root_info = _get_help_info(path, help_cache, logger)
    if root_info is None:
        result.errors.append("Failed to run 'argocd --help' or parse its output.")
        return result.to_dict()

    # Identify subcommand path (stop at first token that isn't a known subcommand)
    idx = 1
    info = root_info
    while idx < len(tokens):
        t = tokens[idx]
        if t.startswith("-"):
            break  # flags/args begin
        if t in info.subcommands:
            path.append(t)
            info = _get_help_info(path, help_cache, logger)
            if info is None:
                result.errors.append(f"Failed to parse help for: {' '.join(path)}")
                return result.to_dict()
            idx += 1
            continue

        # Unknown subcommand at this level → suggest closest matches
        close = difflib.get_close_matches(t, sorted(info.subcommands), n=3, cutoff=0.6)
        result.errors.append(f"Unknown subcommand '{t}' under '{' '.join(path)}'.")
        if close:
            result.suggestions.append(f"Did you mean: {', '.join(close)} ?")
            # Try a best-effort single correction to continue deeper validation
            t_best = close[0]
            result.warnings.append(f"Auto-trying suggested subcommand '{t_best}' for deeper checks.")
            path.append(t_best)
            info = _get_help_info(path, help_cache, logger)
            if info is None:
                return result.to_dict()
            idx += 1
            continue
        else:
            break

    result.parsed_path = path[:]

    # Merge flags from all cached global flags + current level flags
    merged_flags: Dict[str, FlagInfo] = {}
    for _, hi in help_cache.items():
        for name, finfo in hi.global_flags.items():
            merged_flags[name] = finfo
    for name, finfo in info.flags.items():
        merged_flags[name] = finfo
    for name, finfo in info.global_flags.items():
        merged_flags[name] = finfo

    # name lookup
    name_to_flag: Dict[str, FlagInfo] = {}
    for finfo in merged_flags.values():
        for n in finfo.names:
            name_to_flag[n] = finfo

    # Validate flags & values
    consumed = idx
    while consumed < len(tokens):
        tok = tokens[consumed]

        if tok.startswith("-"):
            flag_name, value_inline = _split_flag_value(tok)

            if flag_name not in name_to_flag:
                close = difflib.get_close_matches(flag_name, sorted(name_to_flag.keys()), n=3, cutoff=0.65)
                result.unknown_flags.append(flag_name)
                if close:
                    result.suggestions.append(
                     f"Unknown flag '{flag_name}'. Did you mean: {', '.join(close)} ?"
                )
                consumed += 1
                continue

            finfo = name_to_flag[flag_name]

            if finfo.takes_value:
                if value_inline is not None:
                    consumed += 1
                else:
                    if consumed + 1 >= len(tokens) or tokens[consumed + 1].startswith("-"):
                        result.missing_flag_values.append(flag_name)
                        consumed += 1
                    else:
                        consumed += 2
            else:
                if value_inline is not None:
                    result.warnings.append(f"Flag '{flag_name}' doesn't take a value; ignoring '{value_inline}'.")
                consumed += 1
        else:
            consumed += 1

    # --- Positional validation from Usage ---
    # info.required_positionals contains placeholders like ["APPNAME"]
    # We enforce presence of at least the first positional where required.
    first_positional_idx = None
    scan_idx = idx
    while scan_idx < len(tokens):
        if not tokens[scan_idx].startswith("-"):
            first_positional_idx = scan_idx
            break
        # skip flag + value when needed
        if "=" in tokens[scan_idx] or scan_idx + 1 >= len(tokens) or tokens[scan_idx + 1].startswith("-"):
            scan_idx += 1
        else:
            scan_idx += 2

    if info.required_positionals:
        if first_positional_idx is None:
            # salvage from '--app NAME' misuse
            app_name = None
            for j in range(idx, len(tokens)):
                if tokens[j] == "--app" and j + 1 < len(tokens) and not tokens[j+1].startswith("-"):
                    app_name = tokens[j+1]
                    break
                if tokens[j].startswith("--app="):
                    app_name = tokens[j].split("=", 1)[1]
                    break
            if app_name:
                cleaned = tokens[:]
                if "--app" in cleaned:
                    k = cleaned.index("--app")
                    del cleaned[k:k+2]
                else:
                    cleaned = [t for t in cleaned if not t.startswith("--app=")]
                cleaned = cleaned[:idx] + [app_name] + cleaned[idx:]
                result.suggestions.append("Move the application name to a positional argument (no --app).")
                result.corrected_command = " ".join(cleaned)
            else:
                need = info.required_positionals[0]
                result.errors.append(f"Missing required positional: {need}")
        else:
            for j in range(idx, len(tokens)):
                if tokens[j] == "--app" or tokens[j].startswith("--app="):
                    result.warnings.append("Use positional APPNAME instead of --app for this subcommand.")
                    break

    # --- Specific guidance for '-n' (kubectl-style) ---
    for j in range(idx, len(tokens)):
        if tokens[j] == "-n" and j + 1 < len(tokens) and not tokens[j+1].startswith("-"):
            ns = tokens[j+1]
            result.suggestions.append(
                f"'-n {ns}' is not an Argo CD CLI flag. Remove '-n {ns}' or switch to a proper Argo CD CLI flag."
            )
            break

    # Valid?
    if not result.errors and not result.unknown_flags and not result.missing_flag_values:
        result.valid = True
    else:
        suggested_tokens = _maybe_build_correction(tokens, path, help_cache, logger)
        if suggested_tokens and suggested_tokens != tokens:
            # prefer any earlier positional fix if present; otherwise use generic path correction
            if not result.corrected_command:
                result.corrected_command = " ".join(suggested_tokens)

    return result.to_dict()

# ---------------------------
# Helpers
# ---------------------------
_SECTION_CMD = re.compile(r"^\s*Available Commands:\s*$", re.IGNORECASE)
_SECTION_FLAGS = re.compile(r"^\s*Flags:\s*$", re.IGNORECASE)
_SECTION_GLOBAL = re.compile(r"^\s*Global Flags:\s*$", re.IGNORECASE)

_FLAG_LINE = re.compile(
    r"^\s*(?P<names>(?:-\w(?:,\s*)?)?(?:--[A-Za-z0-9\-]+)?)\s*(?P<type>string|int|bool|duration|float|file|count|time|path|values|[A-Za-z]+)?\s{2,}(?P<desc>.+)$"
)

def _get_help_info(path: List[str], cache: Dict[Tuple[str, ...], HelpInfo], logger=None) -> Optional[HelpInfo]:
    key = tuple(path)
    if key in cache:
        return cache[key]

    help_cmd = " ".join(path + ["--help"])
    raw = execute_run_command(help_cmd, logger=logger)
    if raw.get("exit_code", 1) != 0:
        if logger:
            logger.error("Help command failed: %s\nstderr: %s", help_cmd, raw.get("stderr"))
        return None

    text = raw.get("stdout", "") or ""
    info = _parse_help_text(text)
    cache[key] = info
    return info

def _parse_usage_positionals(lines: List[str], path_tokens: List[str]) -> Tuple[List[str], List[str]]:
    """
    From 'Usage:' section, find the line for the current path, e.g.:
      Usage:
        argocd app manifests APPNAME [flags]
    Return (required_positionals, optional_positionals) based on tokens after the path.
    Uppercase tokens are treated as placeholders. Bracketed tokens are optional.
    """
    required, optional = [], []
    path_str = " ".join(path_tokens)

    i = 0
    while i < len(lines):
        if lines[i].strip().lower().startswith("usage:"):
            i += 1
            while i < len(lines) and lines[i].strip():
                line = lines[i].strip()
                if line.startswith(path_str + " "):
                    tail = line[len(path_str):].strip()
                    toks = tail.split()
                    for t in toks:
                        if t.lower().strip("[]") == "flags":
                            continue
                        is_opt = t.startswith("[") and t.endswith("]")
                        token = t.strip("[]")
                        if token.isupper():
                            (optional if is_opt else required).append(token)
                    break
                i += 1
            break
        i += 1
    return required, optional

def _parse_help_text(text: str) -> HelpInfo:
    lines = text.splitlines()

    subcommands: Set[str] = set()
    flags: Dict[str, FlagInfo] = {}
    global_flags: Dict[str, FlagInfo] = {}

    # ---- Scan sections: Available Commands / Flags / Global Flags ----
    section = None
    i = 0
    while i < len(lines):
        line = lines[i]

        if _SECTION_CMD.match(line):
            section = "commands"
            i += 1
            continue
        if _SECTION_FLAGS.match(line):
            section = "flags"
            i += 1
            continue
        if _SECTION_GLOBAL.match(line):
            section = "global"
            i += 1
            continue

        if section == "commands":
            m = re.match(r"^\s*([A-Za-z0-9\-_]+)\s{2,}.+$", line)
            if m:
                subcommands.add(m.group(1))

        elif section in ("flags", "global"):
            m = _FLAG_LINE.match(line)
            if m:
                names_raw = (m.group("names") or "").strip()
                ftype = (m.group("type") or "").strip().lower()
                takes_value = ftype not in ("", "bool", "count")

                names = [n.strip() for n in names_raw.split(",") if n.strip()]
                name_set = set(names)
                canonical = next((n for n in names if n.startswith("--")), names[0]) if names else ""

                finfo = FlagInfo(names=name_set, takes_value=takes_value, canonical=canonical)
                target = flags if section == "flags" else global_flags
                for n in name_set:
                    target[n] = finfo

        i += 1

    # ---- Extract positionals from Usage: ----
    path_tokens: List[str] = []
    for ln in lines:
        s = ln.strip()
        if s.startswith("argocd "):
            parts = s.split()
            path_tokens = []
            for p in parts:
                if p.startswith("-"):
                    break
                if p.isupper():
                    break
                path_tokens.append(p)
            if path_tokens and path_tokens[0] == "argocd":
                break

    req_pos, opt_pos = _parse_usage_positionals(lines, path_tokens or ["argocd"])

    return HelpInfo(
        subcommands=subcommands,
        flags=flags,
        global_flags=global_flags,
        required_positionals=req_pos,
        optional_positionals=opt_pos,
    )

def _split_flag_value(flag_token: str) -> Tuple[str, Optional[str]]:
    if "=" in flag_token and not flag_token.startswith(("'", "\"")):
        name, val = flag_token.split("=", 1)
        return name, val
    return flag_token, None

def _maybe_build_correction(tokens: List[str], path: List[str],
                            cache: Dict[Tuple[str, ...], HelpInfo], logger=None) -> Optional[List[str]]:
    """
    Rebuild a corrected command using the 'path' we've derived (which may include
    an auto-corrected subcommand). We align the corrected subcommand sequence
    against the original tokens and SKIP any unmatched/incorrect subcommand tokens
    from the original before appending flags/args.
    """
    if len(path) <= 1:
        return None

    rebuilt = ["argocd"] + path[1:]
    j = 1
    i = 1
    while i < len(tokens) and j < len(path):
        if tokens[i].startswith("-"):
            break
        if tokens[i] == path[j]:
            i += 1
            j += 1
        else:
            i += 1

    rebuilt.extend(tokens[i:])
    return rebuilt
