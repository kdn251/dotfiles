#!/usr/bin/env python3
"""Display-scale helper for display-panel.sh.

Scale must be written through KANSHI, not hyprctl. kanshi holds the
authoritative scale per profile and re-applies it whenever outputs change --
which a scale change itself triggers -- so `hyprctl keyword monitor ...,1.6`
reports "ok" and is silently reverted within about a second. Verified by
stopping kanshi: the same hyprctl call then applies correctly.

Note ~/.config/kanshi is a symlink into the dotfiles repo, so changing scale
edits a tracked file. It also means the scale persists across reboots, which
hyprctl would not.

Usage:
  display-scale.py --current      current scale of the focused output
  display-scale.py --neighbours   "<prev> <next>" valid steps ('-' if none)
  display-scale.py --set VALUE    write it into the active kanshi profile
"""

import fnmatch
import json
import os
import re
import subprocess
import sys

CANDIDATES = (1, 1.2, 1.25, 1.5, 1.6, 2, 2.4, 2.5, 3)
KANSHI_CFG = os.path.expanduser("~/.config/kanshi/config")


def g(v):
    """Compact form for display: 2, 1.6, 1.25."""
    return "%g" % v


def g_cfg(v):
    """Form written into kanshi's config. Keeps its existing one-decimal
    style for whole numbers (scale 2.0, not scale 2) so writing a value back
    does not produce a gratuitous diff in the tracked file."""
    out = "%g" % v
    return out + ".0" if "." not in out else out


def sh(*cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def monitors():
    return json.loads(sh("hyprctl", "monitors", "-j").stdout or "[]")


def focused():
    live = [m for m in monitors() if not m.get("disabled")]
    if not live:
        return None
    return next((m for m in live if m.get("focused")), live[0])


def valid_scales(w, h):
    return [s for s in CANDIDATES
            if abs(w / s - round(w / s)) < 1e-6 and abs(h / s - round(h / s)) < 1e-6]


def _close(text, start):
    i, depth = start, 1
    while i < len(text) and depth:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    return i - 1


def _outputs(body):
    """Yield (identifier, enabled, start, end, braced) for each output entry.

    kanshi accepts two forms and this config uses both:
        output "eDP-1" { enable  mode ...  scale 2.0 }      (braced)
        output "LG ... *" enable mode ... scale 1.5          (single line)
    Only handling the braced form made every docked profile look like it had
    no outputs at all.
    """
    for om in re.finditer(r'output\s+"([^"]+)"[ \t]*(\{?)', body):
        ident, brace = om.group(1), om.group(2)
        if brace:
            e = _close(body, om.end())
            yield ident, "disable" not in body[om.end():e], om.end(), e, True
        else:
            e = body.find("\n", om.end())
            if e == -1:
                e = len(body)
            yield ident, "disable" not in body[om.end():e], om.end(), e, False


def matches(ident, mon):
    """kanshi identifies outputs by connector name OR by a description glob
    ("LG Electronics LG ULTRAGEAR+ *"), while hyprctl reports connector names.
    Compare against both."""
    if ident == mon.get("name"):
        return True
    return fnmatch.fnmatch(mon.get("description", ""), ident)


def active_profile(cfg, mons):
    """Profile whose enabled outputs all correspond to connected monitors.

    Falls back to a docked/undocked guess by monitor count, because a profile
    can name an output by a glob that matches nothing currently connected.
    """
    host = os.uname().nodename
    docked = len(mons) > 1
    candidates = []
    for m in re.finditer(r"profile\s+(\S+)\s*\{", cfg):
        s, e = m.end(), _close(cfg, m.end())
        enabled = [i for i, on, *_ in _outputs(cfg[s:e]) if on]
        if not enabled:
            continue
        hit = all(any(matches(i, mon) for mon in mons) for i in enabled)
        if hit and len(enabled) == len(mons):
            candidates.append((0, m.group(1), s, e))
        elif m.group(1).startswith(host) and (
            ("docked" in m.group(1) and "undocked" not in m.group(1)) == docked
        ):
            candidates.append((1, m.group(1), s, e))
    if not candidates:
        return None
    candidates.sort(key=lambda c: (c[0], not c[1].startswith(host)))
    return candidates[0][1], candidates[0][2], candidates[0][3]


def set_scale(mon, value):
    try:
        cfg = open(KANSHI_CFG).read()
    except OSError as exc:
        return False, "kanshi config unreadable: %s" % exc

    mons = [m for m in monitors() if not m.get("disabled")]
    found = active_profile(cfg, mons)
    if not found:
        return False, "no kanshi profile matches the connected outputs"
    pname, s, e = found

    body = cfg[s:e]
    target = None
    for ident, on, os_, oe, braced in _outputs(body):
        if on and matches(ident, mon):
            target = (os_, oe, braced)
            break
    if not target:
        return False, "%s not in profile %s" % (mon.get("name"), pname)
    os_, oe, braced = target
    blk = body[os_:oe]

    if re.search(r"(?<![\w-])scale\s+[\d.]+", blk):
        blk2 = re.sub(r"((?<![\w-])scale\s+)[\d.]+", r"\g<1>%s" % g_cfg(value), blk, count=1)
    elif braced:
        blk2 = blk.rstrip() + "\n        scale %s\n    " % g_cfg(value)
    else:
        blk2 = blk.rstrip() + " scale %s" % g_cfg(value)

    try:
        with open(KANSHI_CFG, "w") as fh:
            fh.write(cfg[:s] + body[:os_] + blk2 + body[oe:] + cfg[e:])
    except OSError as exc:
        return False, "write failed: %s" % exc

    if sh("kanshictl", "reload").returncode != 0:
        return False, "kanshictl reload failed"
    return True, "%s now %sx" % (mon.get("name"), g(value))


def main():
    mon = focused()
    if not mon:
        print("no active monitor", file=sys.stderr)
        return 1
    scales = valid_scales(mon["width"], mon["height"])
    cur = round(float(mon["scale"]), 4)
    idx = min(range(len(scales)), key=lambda i: abs(scales[i] - cur)) if scales else -1

    arg = sys.argv[1] if len(sys.argv) > 1 else "--current"

    if arg == "--current":
        print(g(scales[idx]) if idx >= 0 else g(cur))
    elif arg == "--neighbours":
        prev = g(scales[idx - 1]) if idx > 0 else "-"
        nxt = g(scales[idx + 1]) if 0 <= idx < len(scales) - 1 else "-"
        print("%s %s" % (prev, nxt))
    elif arg == "--set":
        if len(sys.argv) < 3:
            print("--set needs a value", file=sys.stderr)
            return 2
        ok, msg = set_scale(mon, float(sys.argv[2]))
        print(msg)
        return 0 if ok else 1
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
