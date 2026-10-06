#!/usr/bin/env python3
"""Build every scene master into ../scenes/. Usage: python build.py [scene-name ...]"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scenes, scenes_b

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scenes")
out = os.path.abspath(out)
os.makedirs(out, exist_ok=True)
wanted = set(sys.argv[1:])
for make in scenes.SCENES + scenes_b.SCENES:
    doc = make()
    if wanted and not any(w in doc.name for w in wanted):
        continue
    print("building", doc.name, flush=True)
    doc.build(out)
