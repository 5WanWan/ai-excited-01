# ai-excited-01 — "The Lighthouse Inside the Wave"

Entry for make.fun competition `ai-excited-01`: one image made to excite
the AI judge.

## The image

A colossal ocean wave curls into a barrel that fills the whole frame,
lit by a low golden sun half-hidden behind the crest. Inside the barrel —
impossibly small against the water — stands a tiny red-and-white
lighthouse on a rock, its beam cutting out toward the viewer. It is the
second before the wave swallows it: one big readable shape (the curl),
one small surprise for the second look (the lighthouse).

## The program

`main.py` draws the image procedurally with Python's standard library
only (`zlib` + `struct` to write the PNG; no image libraries, no
downloaded assets). Everything is seeded (`SEED = 20261116`), so two
runs write byte-identical output.

Run it:

```
mkdir -p out && MAKEFUN_OUTPUT_DIR=out python3 main.py
```

It writes `entry.png` (1024x1024, ~216 KB).

## License

MIT — see `LICENSE`.
