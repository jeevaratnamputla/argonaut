# review_argocd_command.py
"""
Argo CD command reviewer (robust global-flag value consumption).
- Reviews only the argocd segment before any '|', '||', '&', '&&', ':'
- Consumes GLOBAL flags before/between subcommands
  * If a global flag takes a value (e.g., --server), the next token is ALWAYS
    consumed as the flag's value (unless provided inline), so hostnames like
    'argocd.sandbox.opsmx.net' are never mistaken for subcommands.
- Parses exact Usage to detect required/optional positionals
- Lists non-global flags for the final subcommand with help text
"""

import os
import re
import shlex
import difflib
import subprocess
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Set, Tuple

# ---------------- Local runner ----------------
def execute_run_command(cmd: str, logger=None, timeout: float = 15.0, cwd: Optional[str] = None) -> Dict[str, object]:
    if logger:
        logger.debug("execute_run_command: %s", cmd)
    try:
        argv = shlex.split(cmd)
    except ValueError as e:
        return {"exit_code": 127, "stdout": "", "stderr": f"shlex error: {e}"}
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
        creationflags = 0x08000000 if os.name == "nt" else 0
        proc = subprocess.Popen(
            argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=cwd, env=env, shell=False, creationflags=creationflags
        )
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try: proc.kill()
            except Exception: pass
            out, err = proc.communicate()
            return {"exit_code": 124, "stdout": out.decode(errors="replace") if out else "",
                    "stderr": (err.decode(errors="replace") if err else "") + "\n[timeout]"}
        return {"exit_code": proc.returncode,
                "stdout": out.decode(errors="replace") if out else "",
                "stderr": err.decode(errors="replace") if err else ""}
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

# ---------------- Data ----------------
@dataclass
class FlagInfo:
    names: Set[str]
    takes_value: bool
    canonical: str
    desc: str

@dataclass
class HelpInfo:
    subcommands: Set[str]
    flags: Dict[str, 'FlagInfo']
    global_flags: Dict[str, 'FlagInfo']
    required_positionals: List[str]
    optional_positionals: List[str]

@dataclass
class ReviewResult:
    valid: bool
    available_flags: List[str]
    available_flags_with_help: List[Dict[str, object]]
    errors: List[str]
    warnings: List[str]
    corrected_command: Optional[str]
    parsed_path: List[str]
    unknown_flags: List[str]
    missing_flag_values: List[str]
    suggestions: List[str]
    def to_dict(self): return asdict(self)

# ---------------- Public API ----------------
def review_command(command: str, logger=None) -> Dict:
    if logger: logger.debug("Reviewing command: %s", command)
    # Only review up to first pipe/amp/colon
    command = re.split(r"\s*(\|\||\||&&|&|:)\s*", command, maxsplit=1)[0].strip()

    tokens = shlex.split(command)
    result = ReviewResult(False, [], [], [], [], None, [], [], [], [])
    if not tokens:
        result.errors.append("Empty command.")
        return result.to_dict()
    if tokens[0] != "argocd":
        result.errors.append("Command must start with 'argocd'.")
        return result.to_dict()

    path = ["argocd"]
    help_cache: Dict[Tuple[str, ...], HelpInfo] = {}
    root_info = _get_help_info(path, help_cache, logger)
    if root_info is None:
        result.errors.append("Failed to run 'argocd --help' or parse its output.")
        return result.to_dict()

    idx = 1
    info = root_info

    def _collect_global_flag_lookup(cache: Dict[Tuple[str, ...], HelpInfo]) -> Dict[str, FlagInfo]:
        g: Dict[str, FlagInfo] = {}
        for hi in cache.values():
            for finfo in hi.global_flags.values():
                for n in finfo.names:
                    g[n] = finfo
        return g

    # --- Walk subcommands, but consume GLOBAL flags anywhere before/between them ---
    while idx < len(tokens):
        t = tokens[idx]

        # Consume global flags (e.g., --server) even before subcommands
        if t.startswith("-"):
            glookup = _collect_global_flag_lookup(help_cache)
            fname, val_inline = _split_flag_value(t)
            finfo = glookup.get(fname)

            if finfo:
                # ALWAYS consume the value for global flags that take a value
                if finfo.takes_value:
                    if val_inline is not None:
                        idx += 1  # consumed inline form --flag=value
                    else:
                        idx += 1  # consume the flag token
                        if idx < len(tokens):
                            idx += 1  # unconditionally consume the next token as the value
                        else:
                            result.missing_flag_values.append(fname)
                else:
                    idx += 1  # boolean/count style
                continue
            break  # Non-global flag encountered; subcommand walk ends

        # If no subcommands at this level, treat next non-flag as positional
        if not info.subcommands:
            break
        # If Usage shows positionals at this level, stop descent and treat next as positional
        if (info.required_positionals or info.optional_positionals) and t not in info.subcommands:
            break

        if t in info.subcommands:
            path.append(t)
            info = _get_help_info(path, help_cache, logger)
            if info is None:
                result.errors.append(f"Failed to parse help for: {' '.join(path)}")
                return result.to_dict()
            idx += 1
            continue

        # Unknown subcommand token
        close = difflib.get_close_matches(t, sorted(info.subcommands), n=3, cutoff=0.6)
        result.errors.append(f"Unknown subcommand '{t}' under '{' '.join(path)}'.")
        if close:
            result.suggestions.append(f"Did you mean: {', '.join(close)} ?")
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

    # Build merged flag lookup: current-level non-global + all seen global flags
    merged_flags: Dict[str, FlagInfo] = {}
    # include all globals from cache
    for hi in help_cache.values():
        for finfo in hi.global_flags.values():
            for n in finfo.names:
                merged_flags[n] = finfo
    # include current level non-global & global
    for finfo in list(info.flags.values()) + list(info.global_flags.values()):
        for n in finfo.names:
            merged_flags[n] = finfo

    # Validate flags & values starting where we stopped walking subcommands
    consumed = idx
    while consumed < len(tokens):
        tok = tokens[consumed]
        if tok.startswith("-"):
            flag_name, value_inline = _split_flag_value(tok)
            finfo = merged_flags.get(flag_name)
            if not finfo:
                close = difflib.get_close_matches(flag_name, sorted(merged_flags.keys()), n=3, cutoff=0.65)
                result.unknown_flags.append(flag_name)
                if close:
                    result.suggestions.append(f"Unknown flag '{flag_name}'. Did you mean: {', '.join(close)} ?")
                consumed += 1
                continue
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

    # Required positionals check (best-effort)
    first_positional_idx = None
    scan_idx = idx
    while scan_idx < len(tokens):
        if not tokens[scan_idx].startswith("-"):
            first_positional_idx = scan_idx
            break
        if "=" in tokens[scan_idx] or scan_idx + 1 >= len(tokens) or tokens[scan_idx + 1].startswith("-"):
            scan_idx += 1
        else:
            scan_idx += 2

    if info.required_positionals:
        if first_positional_idx is None:
            # Try salvaging '--app NAME'
            app_name = None
            for j in range(idx, len(tokens)):
                if tokens[j] == "--app" and j + 1 < len(tokens) and not tokens[j+1].startswith("-"):
                    app_name = tokens[j+1]; break
                if tokens[j].startswith("--app="):
                    app_name = tokens[j].split("=", 1)[1]; break
            if app_name:
                cleaned = tokens[:]
                if "--app" in cleaned:
                    k = cleaned.index("--app"); del cleaned[k:k+2]
                else:
                    cleaned = [t for t in cleaned if not t.startswith("--app=")]
                cleaned = cleaned[:idx] + [app_name] + cleaned[idx:]
                cleaned = _apply_corrected_path(cleaned, path)
                cleaned = _strip_kubectl_ns(cleaned)
                result.suggestions.append("Move the application name to a positional argument (no --app).")
                result.corrected_command = " ".join(cleaned)
            else:
                result.errors.append(f"Missing required positional: {info.required_positionals[0]}")
        else:
            for j in range(idx, len(tokens)):
                if tokens[j] == "--app" or tokens[j].startswith("--app="):
                    result.warnings.append("Use positional APPNAME instead of --app for this subcommand.")
                    break

    # kubectl-style '-n <ns>' hint
    for j in range(idx, len(tokens)):
        if tokens[j] == "-n" and j + 1 < len(tokens) and not tokens[j+1].startswith("-"):
            ns = tokens[j+1]
            result.warnings.append(f"'-n {ns}' is not an Argo CD CLI flag.")
            result.unknown_flags.append("-n")
            break

    # Valid?
    if not result.errors and not result.unknown_flags and not result.missing_flag_values:
        result.valid = True
    else:
        suggested_tokens = _maybe_build_correction(tokens, path, help_cache, logger)
        if suggested_tokens and suggested_tokens != tokens:
            suggested_tokens = _strip_kubectl_ns(suggested_tokens)
            if not result.corrected_command:
                result.corrected_command = " ".join(suggested_tokens)

    # Only non-global flags for this subcommand (with help)
    seen_keys = set()
    available_flags = []
    available_flags_with_help = []
    for finfo in info.flags.values():
        key = (tuple(sorted(finfo.names)), bool(finfo.takes_value), finfo.desc)
        if key in seen_keys: continue
        seen_keys.add(key)
        names_sorted = sorted(finfo.names, key=lambda n: (0 if n.startswith('--') else 1, n))
        label = ", ".join(names_sorted) + (" (value)" if finfo.takes_value else "")
        available_flags.append(label)
        available_flags_with_help.append({"names": names_sorted, "takes_value": finfo.takes_value, "desc": finfo.desc})
    result.available_flags = sorted(available_flags)
    result.available_flags_with_help = sorted(
        available_flags_with_help, key=lambda d: (0 if d["names"][0].startswith("--") else 1, d["names"][0])
    )

    return result.to_dict()

# ---------------- Parsing helpers ----------------
_SECTION_CMD = re.compile(r"^\s*Available Commands:\s*$", re.IGNORECASE)
_SECTION_FLAGS = re.compile(r"^\s*Flags:\s*$", re.IGNORECASE)
_SECTION_GLOBAL = re.compile(r"^\s*Global Flags:\s*$", re.IGNORECASE)

# Robust to "--output, -o" OR "-o, --output"
_FLAG_LINE = re.compile(
    r"^\s*(?P<names>(?:-\w|--[A-Za-z0-9\-]+)(?:,\s*(?:-\w|--[A-Za-z0-9\-]+))*)\s*"
    r"(?P<type>string|int|bool|duration|float|file|count|time|path|values|[A-Za-z]+)?\s{2,}(?P<desc>.+)$"
)

def _get_help_info(path: List[str], cache: Dict[Tuple[str, ...], HelpInfo], logger=None) -> Optional[HelpInfo]:
    key = tuple(path)
    if key in cache: return cache[key]
    help_cmd = " ".join(path + ["--help"])
    raw = execute_run_command(help_cmd, logger=logger)
    if raw.get("exit_code", 1) != 0:
        if logger: logger.error("Help command failed: %s\nstderr: %s", help_cmd, raw.get("stderr"))
        return None
    text = raw.get("stdout", "") or ""
    info = _parse_help_text(text, path)
    cache[key] = info
    return info

def _parse_usage_positionals(lines: List[str], path_tokens: List[str]) -> Tuple[List[str], List[str]]:
    required, optional = [], []
    path_str = " ".join(path_tokens)
    i = 0
    while i < len(lines):
        if lines[i].strip().lower().startswith("usage:"):
            i += 1
            while i < len(lines) and lines[i].strip():
                line = lines[i].strip()
                if line.startswith(path_str + " ") or line == path_str:
                    tail = line[len(path_str):].strip()
                    toks = tail.split()
                    for t in toks:
                        if t.lower().strip("[]") == "flags": continue
                        is_opt = t.startswith("[") and t.endswith("]")
                        token = t.strip("[]")
                        if token.isupper():
                            (optional if is_opt else required).append(token)
                    break
                i += 1
            break
        i += 1
    return required, optional

def _parse_help_text(text: str, path_tokens: List[str]) -> HelpInfo:
    lines = text.splitlines()
    subcommands: Set[str] = set()
    flags: Dict[str, FlagInfo] = {}
    global_flags: Dict[str, FlagInfo] = {}

    section = None
    i = 0
    while i < len(lines):
        line = lines[i]

        if _SECTION_CMD.match(line):
            section = "commands"; i += 1; continue
        if _SECTION_FLAGS.match(line):
            section = "flags"; i += 1; continue
        if _SECTION_GLOBAL.match(line):
            section = "global"; i += 1; continue

        if section == "commands":
            m = re.match(r"^\s*([A-Za-z0-9\-_]+)\s{2,}.+$", line)
            if m: subcommands.add(m.group(1))

        elif section in ("flags", "global"):
            m = _FLAG_LINE.match(line)
            if m:
                names_raw = (m.group("names") or "").strip()
                ftype = (m.group("type") or "").strip().lower()
                takes_value = ftype not in ("", "bool", "count")
                desc = (m.group("desc") or "").strip()
                names = [n.strip() for n in names_raw.split(",") if n.strip()]
                name_set = set(names)
                canonical = next((n for n in names if n.startswith("--")), names[0]) if names else ""
                finfo = FlagInfo(names=name_set, takes_value=takes_value, canonical=canonical, desc=desc)
                target = flags if section == "flags" else global_flags
                for n in name_set: target[n] = finfo
        i += 1

    req_pos, opt_pos = _parse_usage_positionals(lines, path_tokens)
    return HelpInfo(subcommands=subcommands, flags=flags, global_flags=global_flags,
                    required_positionals=req_pos, optional_positionals=opt_pos)

def _split_flag_value(flag_token: str) -> Tuple[str, Optional[str]]:
    if "=" in flag_token and not flag_token.startswith(("'", "\"")):
        name, val = flag_token.split("=", 1); return name, val
    return flag_token, None

def _apply_corrected_path(tokens: List[str], path: List[str]) -> List[str]:
    rebuilt = ["argocd"] + path[1:]
    j = 1; i = 1
    while i < len(tokens) and j < len(path):
        if tokens[i].startswith("-"): break
        if tokens[i] == path[j]: i += 1; j += 1
        else: i += 1
    rebuilt.extend(tokens[i:]); return rebuilt

def _strip_kubectl_ns(tokens: List[str]) -> List[str]:
    out: List[str] = []; i = 0
    while i < len(tokens):
        if tokens[i] == "-n":
            if i + 1 < len(tokens) and not tokens[i+1].startswith("-"):
                i += 2; continue
        out.append(tokens[i]); i += 1
    return out

def _maybe_build_correction(tokens: List[str], path: List[str],
                            cache: Dict[Tuple[str, ...], HelpInfo], logger=None) -> Optional[List[str]]:
    if len(path) <= 1: return None
    rebuilt = ["argocd"] + path[1:]
    j = 1; i = 1
    while i < len(tokens) and j < len(path):
        if tokens[i].startswith("-"): break
        if tokens[i] == path[j]: i += 1; j += 1
        else: i += 1
    rebuilt.extend(tokens[i:]); return rebuilt
