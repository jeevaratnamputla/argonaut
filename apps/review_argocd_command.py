# review_argocd_command.py
import re
import shlex
import difflib
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Set, Tuple
from execute_run_command import execute_run_command

# Expect this to be provided by you:
# def execute_run_command(cmd: str, logger=None) -> Dict[str, str | int]:
#     return {"exit_code": 0, "stdout": "...", "stderr": "..."}

@dataclass
class FlagInfo:
    names: Set[str]           # e.g. {"-h", "--help"}
    takes_value: bool         # True if flag expects a value
    canonical: str            # choose a stable canonical form (long if available)

@dataclass
class HelpInfo:
    subcommands: Set[str]     # available subcommands at this level
    flags: Dict[str, FlagInfo]  # by each name ("-n" or "--name") -> FlagInfo
    global_flags: Dict[str, FlagInfo]  # union-able set of global flags seen at this level

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

# ---------------------------
# Core public entrypoint
# ---------------------------
def review_command(command: str, logger=None) -> Dict:
    """
    Validate an argocd command by checking subcommands and flags against `--help` outputs.
    Returns a dict (serialize-friendly) with validity, errors, and correction hints.
    """
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
        result.errors.append(
            f"Unknown subcommand '{t}' under '{' '.join(path)}'."
        )
        if close:
            result.suggestions.append(
                f"Did you mean: {', '.join(close)} ?"
            )
            # Try a best-effort single correction to continue deeper validation
            t_best = close[0]
            result.warnings.append(
                f"Auto-trying suggested subcommand '{t_best}' for deeper checks."
            )
            path.append(t_best)
            info = _get_help_info(path, help_cache, logger)
            if info is None:
                return result.to_dict()
            idx += 1
            continue
        else:
            # Can't continue subcommand walk; stop here
            break

    result.parsed_path = path[:]

    # Collect flags available at this level: local + global (root and current)
    # Merge strategy: current level flags + all global flags we have (prefer canonical long forms)
    merged_flags = {}
    # include all ancestor global flags too
    for key, hi in help_cache.items():
        for name, finfo in hi.global_flags.items():
            merged_flags[name] = finfo
    # include current level
    for name, finfo in info.flags.items():
        merged_flags[name] = finfo
    for name, finfo in info.global_flags.items():
        merged_flags[name] = finfo

    # Build a quick lookup from canonical -> FlagInfo and name -> FlagInfo
    name_to_flag: Dict[str, FlagInfo] = {}
    for finfo in merged_flags.values():
        for n in finfo.names:
            name_to_flag[n] = finfo

    # Validate flags & values
    consumed = idx
    used_flags: List[str] = []
    while consumed < len(tokens):
        tok = tokens[consumed]

        if tok.startswith("-"):
            # split --flag=value form
            flag_name, value_inline = _split_flag_value(tok)

            if flag_name not in name_to_flag:
                # suggest closest flag
                close = difflib.get_close_matches(
                    flag_name,
                    sorted(name_to_flag.keys()),
                    n=3,
                    cutoff=0.65,
                )
                result.unknown_flags.append(flag_name)
                if close:
                    result.suggestions.append(
                        f"Unknown flag '{flag_name}'. Did you mean: {', '.join(close)} ?"
                    )
                consumed += 1
                continue

            finfo = name_to_flag[flag_name]
            used_flags.append(finfo.canonical)

            if finfo.takes_value:
                if value_inline is not None:
                    # ok, value provided as --flag=value
                    consumed += 1
                else:
                    # value should be next token
                    if consumed + 1 >= len(tokens) or tokens[consumed + 1].startswith("-"):
                        result.missing_flag_values.append(flag_name)
                        consumed += 1
                    else:
                        consumed += 2  # consume flag + value
            else:
                if value_inline is not None:
                    result.warnings.append(
                        f"Flag '{flag_name}' doesn't take a value; ignoring '{value_inline}'."
                    )
                consumed += 1
        else:
            # positional arg; we won't deeply validate positional arity here (Cobra help varies)
            consumed += 1

    # Determine validity & correction guess
    if not result.errors and not result.unknown_flags and not result.missing_flag_values:
        result.valid = True
    else:
        # Try building a corrected command if we had exactly one subcommand correction
        suggested_tokens = _maybe_build_correction(tokens, path, help_cache, logger)
        if suggested_tokens and suggested_tokens != tokens:
            result.corrected_command = " ".join(suggested_tokens)

    return result.to_dict()

# ---------------------------
# Helpers
# ---------------------------
_SECTION_CMD = re.compile(r"^\s*Available Commands:\s*$", re.IGNORECASE)
_SECTION_FLAGS = re.compile(r"^\s*Flags:\s*$", re.IGNORECASE)
_SECTION_GLOBAL = re.compile(r"^\s*Global Flags:\s*$", re.IGNORECASE)

# Cobra-ish flag patterns
#  e.g. "  -h, --help               help for app"
#       "      --server string      Argo CD server address"
#       "  -n, --namespace string   Kubernetes namespace"
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

def _parse_help_text(text: str) -> HelpInfo:
    lines = text.splitlines()

    subcommands: Set[str] = set()
    flags: Dict[str, FlagInfo] = {}
    global_flags: Dict[str, FlagInfo] = {}

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
            # lines like "  app        Manage applications"
            m = re.match(r"^\s*([A-Za-z0-9\-_]+)\s{2,}.+$", line)
            if m:
                subcommands.add(m.group(1))

        elif section in ("flags", "global"):
            # try parse a flag line
            m = _FLAG_LINE.match(line)
            if m:
                names_raw = (m.group("names") or "").strip()
                ftype = (m.group("type") or "").strip().lower()
                takes_value = ftype not in ("", "bool", "count")  # common cobra types that don't need values

                # names_raw could be "-n, --namespace" or "--server"
                names = [n.strip() for n in names_raw.split(",") if n.strip()]
                name_set = set(names)
                canonical = next((n for n in names if n.startswith("--")), names[0]) if names else ""

                finfo = FlagInfo(names=name_set, takes_value=takes_value, canonical=canonical)
                target = flags if section == "flags" else global_flags
                for n in name_set:
                    target[n] = finfo

        i += 1

    return HelpInfo(subcommands=subcommands, flags=flags, global_flags=global_flags)

def _split_flag_value(flag_token: str) -> Tuple[str, Optional[str]]:
    # --flag=value or -f=value ; also handle --flag=
    if "=" in flag_token and not flag_token.startswith(("'","\"")):
        name, val = flag_token.split("=", 1)
        return name, val
    return flag_token, None

def _maybe_build_correction(tokens: List[str], path: List[str],
                            cache: Dict[Tuple[str, ...], HelpInfo], logger=None) -> Optional[List[str]]:
    """
    If we encountered exactly one unknown subcommand earlier and had a suggestion,
    we've already advanced 'path' with the top suggestion. Rebuild command with that path.
    Otherwise, return None.
    """
    if len(path) <= 1:
        return None  # nothing to correct
    # Rebuild: keep 'argocd', then the chosen path[1:], then append all original flags/args that followed the first bad token
    # Find the index where original path diverged
    rebuilt = ["argocd"] + path[1:]
    # collect original flags/args that are not part of the accepted subcommand chain
    # Find first non-subcommand token in original tokens
    idx = 1
    info = cache.get(tuple(["argocd"]), None)
    while idx < len(tokens) and not tokens[idx].startswith("-") and info:
        if tokens[idx] in info.subcommands:
            info = cache.get(tuple(["argocd"] + tokens[1:idx+1]), info)  # advance info if available
            idx += 1
        else:
            break
    # append the rest
    rebuilt.extend(tokens[idx:])
    return rebuilt
