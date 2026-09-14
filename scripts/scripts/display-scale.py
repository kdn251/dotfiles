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


def active_profile(cfg, names):
    host = os.uname().nodename
    fallback = None
    for m in re.finditer(r"profile\s+(\S+)\s*\{", cfg):
        s, e = m.end(), _close(cfg, m.end())
        body = cfg[s:e]
        outs = set()
        for om in re.finditer(r'output\s+"([^"]+)"\s*\{', body):
            oe = _close(body, om.end())
            if "disable" not in body[om.end():oe]:
                outs.add(om.group(1))
        if outs == set(names):
            if m.group(1).startswith(host):
                return m.group(1), s, e
            fallback = fallback or (m.group(1), s, e)
    return fallback


def set_scale(output, value):
    try:
        cfg = open(KANSHI_CFG).read()
    except OSError as exc:
        return False, "kanshi config unreadable: %s" % exc

    names = [m["name"] for m in monitors() if not m.get("disabled")]
    found = active_profile(cfg, names)
    if not found:
        return False, "no kanshi profile matches %s" % ", ".join(names)
    pname, s, e = found

    body = cfg[s:e]
    om = re.search(r'output\s+"%s"\s*\{' % re.escape(output), body)
    if not om:
        return False, "%s not in profile %s" % (output, pname)
    ob_s = om.end()
    ob_e = _close(body, ob_s)
    ob = body[ob_s:ob_e]

    if re.search(r"^\s*scale\s+[\d.]+\s*$", ob, re.M):
        ob2 = re.sub(r"(^\s*scale\s+)[\d.]+(\s*)$",
                     r"\g<1>%s\g<2>" % g_cfg(value), ob, count=1, flags=re.M)
    else:
        ob2 = ob.rstrip() + "\n        scale %s\n    " % g_cfg(value)

    try:
        with open(KANSHI_CFG, "w") as fh:
            fh.write(cfg[:s] + body[:ob_s] + ob2 + body[ob_e:] + cfg[e:])
    except OSError as exc:
        return False, "write failed: %s" % exc

    if sh("kanshictl", "reload").returncode != 0:
        return False, "kanshictl reload failed"
    return True, "%s now %sx" % (output, g(value))


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
        ok, msg = set_scale(mon["name"], float(sys.argv[2]))
        print(msg)
        return 0 if ok else 1
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
