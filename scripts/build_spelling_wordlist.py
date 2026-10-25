"""Build src/vixl/plugins/spelling/data/en.txt.gz from SCOWL 2020.12.07 (levels 10-60).

Usage: python scripts/build_spelling_wordlist.py SCOWL_DIR OUT.txt.gz, where SCOWL_DIR is the unpacked
scowl-2020.12.07.tar.gz from http://wordlist.aspell.net/ (it holds final/ and Copyright). The output is
deterministic (sorted words, gzip mtime 0) and carries SCOWL's Copyright file verbatim in its header.
"""
import glob
import gzip
import io
import os
import sys

scowl, out = sys.argv[1], sys.argv[2]
SPELLINGS = ("english", "american", "british", "british_z", "canadian", "australian")
KINDS = ("words", "upper", "contractions", "abbreviations", "proper-names")
words = set()
for path in glob.glob(os.path.join(scowl, "final", "*")):
    base, level = os.path.basename(path).rsplit(".", 1)
    spelling, _, kind = base.partition("-")
    if int(level) > 60 or spelling not in SPELLINGS or kind not in KINDS:
        continue
    with open(path, encoding="latin-1") as f:
        for line in f:
            word = line.strip()
            if word and " " not in word:
                words.add(word.lower())
header = [
    "# Vixl spelling plugin: compact English word list (lowercase, one word per line).",
    "# Built from SCOWL (Spell Checker Oriented Word Lists) 2020.12.07, http://wordlist.aspell.net/,",
    "# size 60 and below, the english, american, british, british_z, canadian and australian spellings",
    "# (words, upper, contractions, abbreviations and proper names), lowercased and merged.",
    "# SCOWL's levels 70 and above (which carry the UKACD notice) are not included.",
    "# SCOWL's copyright and permission notice (its Copyright file) follows, verbatim.",
    "#",
]
with open(os.path.join(scowl, "Copyright"), encoding="latin-1") as f:
    header += ["# " + line.rstrip("\n") if line.strip() else "#" for line in f]
header.append("#")
text = "\n".join(header) + "\n" + "\n".join(sorted(words)) + "\n"
buffer = io.BytesIO()
with gzip.GzipFile(fileobj=buffer, mode="wb", compresslevel=9, mtime=0) as g:
    g.write(text.encode("utf-8"))
with open(out, "wb") as f:
    f.write(buffer.getvalue())
print(len(words), len(buffer.getvalue()))
