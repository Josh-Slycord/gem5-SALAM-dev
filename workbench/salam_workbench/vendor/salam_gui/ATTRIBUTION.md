# Recovered SALAM viewer subset

Copied verbatim from the independently restored gem5-SALAM engine at revision
42539ecca54ff0fed455a7afe0bda0603554e360 on 2026-10-29.
The source is /home/jslycord/projects/salam-workbench/engine, restored from the
preserved Ubuntu-20.04 Git bundle. Original sources and the recovery archive were
not modified.

Only the DOT parser and CDFG widget are retained. No simulator launcher, realtime
connection, stats heuristics, generated metrics, or live swarm components are
imported. Package initializers are new minimal scaffolding.

Upstream LICENSE and COPYING are preserved exactly as found. LICENSE contains
unfilled copyright-holder/date placeholders; this copy does not invent an author
or resolve that upstream omission. No additional individual authorship is claimed.

Files and original SHA-256 hashes:

- scripts/salam_gui/data/dot_parser.py -> data/dot_parser.py: eb5068d191836e2356aaa5dc4876886e9cde044bd4c2b4e2476000aaa1ece73f
- scripts/salam_gui/widgets/cdfg_viewer.py -> widgets/cdfg_viewer.py: f73bb8886de9b158b13218edb50c2d0334106ee545d4f1e4dbd9b59fd96eb60e
- LICENSE -> LICENSE: bafc693ac009ddd37e3a96da715eaab7b97891cbf4f800a4a9d93394dfde989c
- COPYING -> COPYING: 320ed0e3e6b1c857a638e89c5aeb06a9a6820c7f9aea89b3055bf5ecf007bb43
