"""Applies the avrgram changes to a checkout of Telegram-iOS.

    python3 patches/apply.py <path to Telegram-iOS>

Each change is one exact replacement; when Telegram moves a line, the script says which one no longer matches
(and stops, so a build is not started on a half-patched tree).
"""
import json
import pathlib
import re
import sys

src = pathlib.Path(sys.argv[1]).resolve()
here = pathlib.Path(__file__).resolve().parent
failed = []


def read(rel):
    return (src / rel).read_text(encoding="utf-8")


def write(rel, text):
    (src / rel).write_text(text, encoding="utf-8", newline="")


def replace(rel, old, new, count=1):
    text = read(rel)
    if new in text and old not in text:
        return
    n = text.count(old)
    if n == 0 or (count == 1 and n != 1):
        failed.append(f"{rel}: {n} matches for {old.strip().splitlines()[0][:70]!r}")
        return
    write(rel, text.replace(old, new) if count == 0 else text.replace(old, new, count))


# ---- the name ---------------------------------------------------------------------------------------
BUILD = "Telegram/BUILD"
text = read(BUILD)
text = text.replace("<key>CFBundleDisplayName</key>\n    <string>Telegram</string>", "<key>CFBundleDisplayName</key>\n    <string>avrgram</string>")
text = text.replace("<key>CFBundleName</key>\n    <string>Telegram</string>", "<key>CFBundleName</key>\n    <string>avrgram</string>")
write(BUILD, text)

# ---- the icon: the avr star on a dark violet disc, in the place of the paper plane ---------------------
icon = "Telegram/Telegram-iOS/Telegram.icon"
star = ("M50 2 C53 30 70 47 98 50 C70 53 53 70 50 98 C47 70 30 53 2 50 C30 47 47 30 50 2Z")
svg = ('<?xml version="1.0" encoding="UTF-8"?>\n'
       '<svg width="1024px" height="1024px" viewBox="0 0 1024 1024" version="1.1" xmlns="http://www.w3.org/2000/svg">\n'
       '    <title>Plane</title>\n'
       '    <g id="Plane" stroke="none" fill="none" fill-rule="nonzero">\n'
       f'        <path fill="#FFFFFF" transform="translate(512 512) scale(4.9) translate(-50 -50)" d="{star}"/>\n'
       '    </g>\n</svg>\n')
write(f"{icon}/Assets/Plane.svg", svg)
spec = json.loads(read(f"{icon}/icon.json"))


def walk(o):
    if isinstance(o, dict):
        for k, v in list(o.items()):
            if k == "linear-gradient":
                o[k] = ["display-p3:0.36,0.31,0.80,1.00000", "srgb:0.04,0.03,0.10,1.00000"]
            else:
                walk(v)
    elif isinstance(o, list):
        for v in o:
            walk(v)


walk(spec)
write(f"{icon}/icon.json", json.dumps(spec, indent=2))

# ---- later waves add more here (theme, ghost mode, kept deleted messages ...) --------------------------
for extra in sorted((here / "features").glob("*.py")) if (here / "features").exists() else []:
    exec(compile(extra.read_text(encoding="utf-8"), str(extra), "exec"), {"src": src, "read": read, "write": write, "replace": replace, "failed": failed})

if failed:
    print("DID NOT MATCH:")
    for f in failed:
        print("  " + f)
    sys.exit(1)
print("avrgram changes are in place")
