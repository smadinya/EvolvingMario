# Status update — Madinya's half is done

Commits `30fae05` and `e43a27a`, pushed to `main`. Branch from `e43a27a`, not from the
older `ad63f2c`.

This is a work-status / handoff note. The graded rationale lives in `writeup.md`.

---

## TL;DR for Alcocer

```sh
git pull origin main
git checkout -b de-encoding
cd src && python3.12 test_ga.py     # expect 4 PASS, 1 FAIL (yours, see below)
DE=1 python3.12 ga.py               # the DE encoding runs now
```

Three things that aren't obvious from the diff:

1. **Use `python3.12`, not `python3`.** Only 3.12 has `scipy` on this machine, and
   `metrics.py` needs `scipy.stats.linregress`. No `pip install` required.
2. **The encoding switch is now an env var.** `Individual = Individual_DE if
   os.environ.get("DE") else Individual_Grid`. Neither of us edits that line again — it was
   going to be a recurring merge conflict.
3. **One test is red on purpose, and it's yours.** See "What's left" below.

---

## What was implemented

### Phase 0 — shared setup (unblocks both halves)

| Change | Why |
| --- | --- |
| `src/levels/` created with `.gitkeep` | `ga.py` wrote to `levels/last.txt` and crashed at generation 1 without it |
| `DE=1` env-var encoding switch | Removes the guaranteed merge conflict on `ga.py:343` |
| Tuning knobs hoisted to module level | The assignment wants parameter experiments; each is now a one-line edit |
| `README.md` documents `python3.12` | numpy+scipy live there, not in the default 3.14 |
| `writeup.md` skeleton, 6 disjoint sections | We only ever append to separate parts of the file |
| `.gitignore` gets `src/levels/*.txt` | Generated output, 10 files per run |

The knobs, all in `src/ga.py` just under `options`:

```python
ELITE_FRAC = 0.05        # top 5% survives untouched
TOURNAMENT_K = 5         # explore/exploit knob
MUTATION_RATE = 0.005    # per interior tile
FLOOR_GAP_RATE = 0.002   # per floor column, chance to start a gap
GAP_MAX_W = 5            # jump arcs reach dx=8, so <=5 stays clearable
JUMP_TARGET = 30         # stop paying for meaningfulJumps here
TILE_WEIGHTS = [70, 6, 3, 1, 4, 8, 0, 3, 5]   # aligned with `options`
```

### Phase 1 — `generate_successors` (was blocking your half)

Elitism + tournament, the two required strategies.

- **Elitism:** top `ELITE_FRAC` by fitness copied through via `heapq.nlargest`. Makes max
  fitness monotonically non-decreasing — a downward step in the logs now means a real bug.
- **Tournament (k=5):** sample k at random, fittest becomes a parent. Chosen over
  roulette-wheel because our fitness can go negative, and roulette-wheel needs non-negative
  weights.
- **Child-count agnostic:** `while len(results) < n: results.extend(...)` then `[:n]`. Grid
  returns 2 and DE returns 2, but neither is contractual, so nothing assumes a fixed count.
  Population stays pinned at 480 for either encoding.

Verified against `Individual_DE` as well (40 individuals in → 40 out), so this is ready for
you to build on.

### Phase 2A — `Individual_Grid`

**Crossover** — single-point by column, returning both complementary children. Column-wise
rather than tile-wise so vertical structures (a pipe's `T` over its `|`, stair supports)
survive the cut intact; uniform per-tile crossover shreds them. Also adds the `mutate()`
call the skeleton's comment promised but never made.

**Mutation** — weighted tile draw over rows 0–14, columns 1–198. `"|"` has weight 0 so pipe
bodies are only ever placed by the `"T"` branch that fills down to the floor, making
floating pipes unreachable rather than merely rare.

Plus a **floor-gap operator**, which is the addition worth knowing about: `metrics.py`
defines a gap as a `-` in row 15, but both initializers fill row 15 with `X` and the safe
mutation rule is "never touch the floor" — so `meaningfulJumps` was *structurally pinned at
0* and no weight on it could ever matter. Gaps are capped at width 5 and floor columns 0–3
and 196–199 stay solid (pathfinding starts at x=2 and the goal test is x=198).

**Fitness** — `solvability` raised 2.0 → 10.0, `meaningfulJumps` (0.3, clamped) and `jumps`
(0.05) added, `leniency` removed. See "Two fitness bugs" below.

**Initialization** — fixed two no-op lines (`g[8:14][-1] = ["f"]*6` assigns into a temporary
slice copy, so random individuals had *no goal column at all*), weighted the tile draw, and
seeded 3–12 floor gaps per individual.

### Tests — `src/test_ga.py`

Plain asserts, no framework. Population size preserved; child shape 16×200; fixed columns
unchanged; no floating pipes; floor invariants at the start and goal; the submitted level is
the right shape and solvable.

---

## Two fitness bugs worth reading about

Both were the same mistake — sizing a coefficient for an **unbounded count** against a
*random* level, when a GA's whole job is to push that number far past where it starts. The
writeup covers this properly; the short version:

1. **`leniency = -0.1` became a "spam coins" bonus.** The metric is unbounded (−135 on an
   evolved level, ~−500 on a uniform-random one), so it contributed up to +50 against a
   solvability term worth 10. Caught by a sweep where uniform-random populations scored
   **higher** (46.88) than evolved ones (32.30). Removed.
2. **`meaningfulJumps` ran away.** Sized against a random level's ~25, the GA optimized it to
   **86** and hollowed out **135 of 192 floor columns** — Mario crossing on scattered debris.
   Now clamped at `JUMP_TARGET = 30`, pinning the term at 9.0 just under solvability's 10.0.
   Floor holes dropped to ~68 and the floor alternates solid runs with 3–6 column gaps.

If you weight an unbounded count in the DE fitness, clamp or normalize it first.

---

## Measurements

Population 120, 10 generations, one seed per config. Population **average** is the more
reliable column — best-of is protected by elitism and is noisy across single seeds.

**Tournament k** (mutation 0.01): k=2 → 28.18 / 22.72 · k=5 → 31.48 / 24.54 ·
k=10 → 30.19 / 22.83 · k=20 → 32.73 / 27.12. *(best / average)*
k=2 is clearly worst; above that it's within noise. Kept k=5.

**Mutation rate** (k=5): 0.005 → 31.04 / **27.35** · 0.01 → 31.48 / 24.54 ·
0.02 → 30.83 / 22.46 · 0.05 → 31.45 / **16.01**.
Best-of is flat (elitism protecting it) while the average collapses. Settled on 0.005.

**Initialization:** weighted 31.48 / 24.54 vs uniform 16.68 / **5.21**. Separately, **0/20**
uniform-random individuals are solvable versus **20/20** weighted — that average of 5.21 is a
population that is mostly unsolvable and contributing nothing to the search.

**Full run** (population 480, 10 cores): 35 generations, 395.7 s, fitness 22.11 → 26.09.
~11 s per generation, of which ~10.5 s is the parallel fitness pass and ~0.3 s is
`generate_successors` — `metrics.py` pathfinding dominates everything.

---

## What's left

**Yours (Phase 2B):** explain the DE crossover and mutation in `writeup.md` §3 (graded item),
guard the empty genome, improve DE fitness and mutation, seed the initializers.

**The red test is your Phase 2B item #2.** `test_de_empty_genome_does_not_raise` fails
because `Individual_DE.generate_children` calls `random.randint(0, len(self.genome) - 1)`,
which raises on the empty genome `empty_individual` returns. Goes green when you guard it.

**Joint, at the end:** `alcocer_madinya.txt` currently holds my Grid level (16×200, solvable,
70/192 floor gaps, 58 meaningful jumps). The assignment wants *one* favorite from *either*
encoding, so if your DE level is better, it replaces mine.

**Deliberately skipped**, both explained in the writeup: seeding real chunks from `level.txt`
(it's 14×201 against our 16×200 grid, needs crop/pad, and weighted init already gives enough
diversity), and adding a metric to `metrics.py` (`meaningfulJumps` already measures the design
goal). **`metrics.py` is unchanged**, so there's nothing extra to submit for it.

**Ownership:** I own `Individual_Grid` (`ga.py:32-121`-ish) and `generate_successors`. You own
`Individual_DE` and `ga()`. Writeup §3, §4, §6 are yours and already stubbed.
