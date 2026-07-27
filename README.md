# EvolvingMario

P5: evolving Super Mario levels with a genetic algorithm.

## Running

Use **`python3.12`** — it is the interpreter on this machine that has both `numpy` and
`scipy` installed (`metrics.py` needs `scipy.stats.linregress`). Plain `python3` is 3.14
and has numpy only.

```sh
cd src
python3.12 ga.py          # Individual_Grid encoding
DE=1 python3.12 ga.py     # Individual_DE encoding
python3.12 test_ga.py     # self-checks
```

Ctrl-c to stop the search. Each generation's best level is written to `src/levels/last.txt`,
and the top 10 of the final generation are dumped to timestamped files in the same dir.

Work split and ownership: see `PLAN.md`. Writeup: `writeup.md`.
