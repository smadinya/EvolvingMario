# P5: Evolving Mario Levels — Writeup

Alcocer & Madinya

Run with `python3.12` (see `README.md`): `python3.12 ga.py` for the grid encoding,
`DE=1 python3.12 ga.py` for the design-element encoding.

---

## 1. Selection strategies *(Madinya)*

`generate_successors` combines two strategies.

**Elitism.** The top `ELITE_FRAC` (5%) of the population by fitness is copied into the next
generation untouched, via `heapq.nlargest`. This is cheap insurance: crossover and mutation
are both destructive, and without elitism a generation can be strictly worse than the one
before it. With it, max fitness is monotonically non-decreasing — visible in our run logs,
which never show a downward step.

**Tournament selection (k = `TOURNAMENT_K`).** The remaining 95% is bred by sampling `k`
individuals uniformly at random and taking the fittest as a parent, twice, then calling
`generate_children`. We chose tournament over roulette-wheel because our fitness values are
not all positive — an unsolvable level can score negative — and roulette-wheel needs
non-negative weights to be a probability distribution, so it would have needed a shift or
rank transform first. Tournament only ever compares fitnesses, so the sign never matters.

`k` is the explore/exploit knob: k=1 is random drift, and as k grows the fittest individual
wins more tournaments and diversity collapses. Sweeping it (population 120, 10 generations,
one seed each, mutation rate 0.01):

| k | best fitness @ gen 10 | population average |
| --- | --- | --- |
| 2 | 28.18 | 22.72 |
| 5 | **31.48** | 24.54 |
| 10 | 30.19 | 22.83 |
| 20 | 32.73 | **27.12** |

k=2 is clearly the worst — too little pressure, the population drifts. Above that the
differences are within single-seed noise, so we kept **k=5** as a middle setting: it was
the best of the low-pressure options, and our full-length runs at k=5 were still improving
at generation 36 rather than plateauing, which is the failure mode we were guarding against
with high k.

One implementation detail worth noting: `generate_successors` must not assume how many
children a pairing produces. Our grid crossover returns 2 and the DE crossover returns 2,
but neither is contractual, so the loop is `while len(results) < n: results.extend(...)`
followed by a `[:n]` truncation. That keeps the population pinned at 480 across generations
regardless of encoding.

## 2. Grid encoding: crossover, mutation, fitness, initialization *(Madinya)*

### Crossover — single-point, by column

We pick one cut point `x_cut ∈ [1, width-1]` and build two children: child A takes columns
left of the cut from parent A and the rest from parent B, child B is the exact complement
(everything the first child left behind — a free second individual out of the same work).

The choice that matters here is **columns, not tiles**. Uniform per-tile crossover, which the
handout offers as an option, decides each of the 3200 tiles independently, which shreds every
vertical structure in the level: a pipe's `T` gets separated from the `|` beneath it, a
staircase loses its supports, a platform keeps half its blocks. Cutting by column means an
entire column is inherited intact from one parent, so vertical structures survive by
construction. We rely on this: it is why our crossover needs no repair pass for floating
pipes, while the mutation operator (which does edit single tiles) does need one.

Keeping `x_cut ≥ 1` and `< width` also preserves the fixed first and last columns — Mario's
start and the goal flag — without any special-casing.

### Mutation

Rate `MUTATION_RATE` per interior tile, applied to rows 0–14 and columns 1–198. At each tile
the mutation draws a replacement from `TILE_WEIGHTS` rather than uniformly from `options`,
for the same reason the initialization is weighted (below). Constraints:

- **Column 0 and column 199 are never touched** — the spec fixes them.
- **`"|"` has weight 0.** A pipe body is only ever placed by the `"T"` branch, which fills
  `|` from the top down to the floor. This makes floating pipe segments unreachable rather
  than merely unlikely; `test_ga.py` asserts it.
- **The floor (row 15) is not mutated by this loop** — it gets its own operator.

**The floor-gap operator.** This one is not in the skeleton and is the change we would most
want to explain. `metrics.py` defines a gap as a `-` in row 15, and `meaningfulJumps` counts
jumps that clear one. But `empty_individual` and `random_individual` both fill row 15 with
`X`, and the obvious safe mutation rule ("never touch the floor") means nothing in the grid
encoding can ever create a gap. So `meaningfulJumps` is *structurally pinned at 0* — you can
put any weight you like on it and the search cannot respond. Since our design goal was a
jumpy, gap-heavy level, we added a separate per-column pass that carves a hole of width
1–`GAP_MAX_W` with probability `FLOOR_GAP_RATE`.

Two bounds keep this from destroying the level: gaps are capped at width 5 (the jump arcs in
`metrics.py` reach dx=8, so ≤5 is comfortably clearable), and floor columns 0–3 and 196–199
stay solid — `metrics` begins pathfinding at x=2 and needs ground under it, and the goal test
is `x == 198`. Measured before wiring it in: 20 gaps of width ≤5 still left 15/15 sampled
levels solvable while lifting `meaningfulJumps` from 0 to ~25.

**Rate.** We swept 0.005 / 0.01 / 0.02 / 0.05 (population 120, 10 generations):

| rate | best fitness @ gen 10 | population average |
| --- | --- | --- |
| 0.005 | 31.04 | **27.35** |
| 0.01 | **31.48** | 24.54 |
| 0.02 | 30.83 | 22.46 |
| 0.05 | 31.45 | 16.01 |

The best-of column is nearly flat, which is elitism doing its job — the single best individual
is protected no matter how destructive mutation gets. The **population average** is where the
damage shows, falling off steeply above 0.005. High mutation also made runs several times
slower, because cluttered levels give the pathfinder far more nodes to expand. We settled on
**0.005**: at 15×198 interior tiles that is ~15 tile changes per child, enough drift to
explore without overwhelming what crossover just assembled.

### Fitness

Design goal: **jumpy and gap-heavy, but always solvable.** Starting from the handout's
coefficients we raised `solvability` from 2.0 to 10.0 and added `meaningfulJumps` (0.3) and
`jumps` (0.05). Unsolvable levels get −1 for all three jump metrics *and* lose the solvability
term, so the effective penalty for unsolvability is large — solvability stays dominant, which
is what stops the search from converging on a level that is all holes.

**Bounded vs unbounded metrics — the mistake we made twice.** Two of the metrics we weighted
are fractions or flags with a known range, and two are unbounded counts. Mixing them in one
weighted sum bit us both times, and in the same way: we estimated a count's magnitude from a
*random* level, but a GA's whole job is to push that number far past where it starts.

1. `leniency` (below) — estimated at a level where it read −135, weighted −0.1, and it turned
   into a "spam coins" bonus worth up to +50.
2. `meaningfulJumps` — we sized the 0.3 weight against a random level's ~25, giving a term of
   ~7.5 under a solvability term of 10. The GA then optimized it to **86**, making the term
   25.8, comfortably the largest in the sum. The result was a level that maximized holes right
   up to the edge of solvability: **135 of 192 floor columns removed**, so Mario crosses on
   scattered debris rather than a floor. It satisfied the fitness function exactly and was not
   the level we asked for.

The fix for (2) is to clamp the measurement before weighting it, `min(meaningfulJumps,
JUMP_TARGET)` with `JUMP_TARGET = 30`. That pins the jump term at 9.0, just under solvability's
10.0, so the search is paid to reach a jumpy level and then paid to keep it beatable rather
than to keep digging. The general rule we would apply next time: an unbounded count needs
either a target/clamp or normalization before it shares a sum with a 0–1 term.

**A coefficient we tried and removed.** We initially added `leniency=-0.1`, reasoning that
`leniency = enemies − 0.5·powerups − 0.5·rewards + len(gaps)` would reward coins and
simultaneously discourage gap spam. It backfired, and the sweep is what caught it: a
*uniform-random* population scored **higher** (46.88) than an evolved one (32.30). The cause
is scale. `leniency` is unbounded — it measured −135 on an evolved level and roughly −500 on
a uniform-random one — so at weight −0.1 it contributed +13.5 and +50 respectively, swamping
a solvability term worth 10. The `−0.5·rewards` half completely dwarfs the `+len(gaps)` half,
so the net effect was simply "paying the GA to carpet the level in coins", and the levels it
produced were visibly cluttered. We dropped the term. With it gone the comparison inverts to
what the solvability data predicts: weighted init 31.48 vs uniform 16.68. The lesson we took
from this is that mixing a 0–1 metric and an unbounded count in one weighted sum is fragile,
and that a metric worth weighting should be one you have actually looked at the range of.

### Initialization

`random_individual` had two latent bugs and one design problem.

The bugs: `g[8:14][-1] = ["f"]*6` and `g[14:16][-1] = ["X","X"]` assign into a *temporary
slice copy*, so they are no-ops — random individuals were being created with no goal flag
column at all, unlike `empty_individual`, which does the same job correctly with a loop. We
replaced both with loops. We also clear the first and last columns explicitly, since the spec
fixes them and the random fill was otherwise scattering tiles there.

The design problem: the original draws tiles uniformly from all 9 options, which produces
levels so dense that **0 out of 20 sampled random individuals were solvable**. Since
solvability is the dominant fitness term, that means generation 0 is a population in which
essentially every individual scores the same low value — the search has no gradient to climb
and has to stumble onto solvability by chance. Weighting the draw toward `-` (70%) gives
**20/20 solvable**. End to end this was the single highest-impact change we made: with the
corrected fitness, weighted init reaches 31.48 by generation 10 against uniform's 16.68, and
the population averages (24.54 vs 5.21) show why — a uniform population stays mostly
unsolvable, so most of its members contribute nothing to the search.

We also seed 3–12 floor gaps into each random individual, so generation 0 already contains
something to jump over rather than having to discover gaps through mutation alone.

We considered seeding real level chunks from `level.txt` and decided against it: that file is
14 rows × 201 columns against our 16 × 200 grid, so it needs a crop-and-pad step, and the
weighted initialization was already supplying enough biodiversity to make the search work.

## 3. DE encoding: crossover and mutation explained *(Alcocer)*
Crossover:
Each individual's genome is just a list of design elements (like holes, platforms, pipes, etc.), but for every individual, the list can be a different length (ex: one level can have 10 elements and another can have like 70).
In generate_children, it basically just picks a random cut point in each parent separately: pa for one parent, pb for the other parent's. Child A is the elements before pa + the elements after pb. So, Child B is the leftover pieces (swapped the other way).
Since the cut points are independent and the lists aren't a fixed size, that means that the children will usually end up with a different number of elements than either parent. That's the main source of diversity, it's not just mixing tile values like the grid encoding, it's mixing like whole chunks of structure and changing how much structure there is.
One bug fixed was: empty_individual(), it returns an empty genome([]), and the original code crashed on it, because random.randint(0, len(self.genome) -1) becomes random.randint(0, -1). Made pa/pb default to 0 when the genome is empty, so crossing anempty individual with anything else just takes the whole non-empty side instead.

Mutation:
10% of the time, we grab one random element and tweak one of its number (position, width, height, etc.) using offset_by_upto function. That function simply adds a small random offset and clips it to stay in range, so small changes are common and big jumps are rare. boolean properties (like whether a block is breakable), it just flips the value instead. The original version only ever changes one element's parameters.

<!-- variable-point crossover walkthrough + diagram, offset_by_upto, the heap -->

## 4. DE encoding: fitness redesign and mutation additions *(Alcocer)*
Fitness

The starting fitness had like no jump term at all, and solvability was only weighted 2.0 which was much weaker than Grid's 10.0. I matched Grid's weights: solvability=10.0, meaningfulJumps=0.3.
I also added a DE only penalty: holes can overlap here, so I sum total hole width from the genome and penalize past 35% of teh level width.
Bloat: When I added the insert/delete mutaation (which is below), average genome lengtj grew from 27 to 278 over 18 generation with no sign of stopping, and generation got around 37% slower for no real fitness gain. This is a known problem with variable length genomes, bigger genomes score slightly better, so selection keeps favoring them with no ceiling. Also, I added a small fitness cost per element:
Penalty weight    Avg length at gen 15    If it's still growing      Fitness at gen 15
      0                    263.3                   yea                        34.60
   0.01                    183.5                yea, still speeding up        32.04
   0.03                    88.9.3                 nope, flattened out         29.97

0.03 was the first weight that actually stopped growth instead of just slowing it, for about a 13% fitness cost. After I also changed which element types get picked more often, 0.03 stopped being enough, bigger genomes were earning more fitness now, so the same flat penalty mattered less. Then, I bumped it to 0.05, which restored the flattening for about a 9% cost.

Mutation additions

The original mutation only tweaks one existing element, it can;t add or remove elements, so crossover was the onyl way genome size changed. I added insert and delete, both at a 5% chance per mutation call. This is also what caused the bloat above, since even a "balanced" insert/delete rate gets pulled off balance by selection favoring bigger genomes.

Initialization (made two changes)

1. which element types get picked. Originally uniform across all 8 types, so a random individual could get a dozen overlapping holes before ever being cored, immediately eating the hole penalty. I weighted the draw so holes and stairs (both penalized past a threshold) are rarer, and lowered the starting element count from 8-128 down to 8-60. These are the results of the same generations compared:

Gen      Before      After
1         19.50      20.03
5         23.50      24.00
10        27.61      28.89

2. How many individuals start empty. empty_individual() for DE is just an empty genome, which renders as the same flat, boring level Grid's empty individual is. For Grid that's a useful like a safety net. For DE it scores only around 10-11 once random_individual is reliably scoring 18-20+ by generation 1, so most of the 10% empty slots were dead weight. So I lowered DE's share to 3%:

Gen      10% empty      3% empty
1         18.69      18.41
5         24.43      24.79
10        28.61      29.09

This was a small but consistent improvement by generation 10

Stopping condition

ga() originally never stopped on its own, so Ctrl C was the only option to stop it. I added a 50 generation cap and an early stop if fitness doesn't improve for 15 generations. I tested it on a full run and it never stopped early. Fitness kept improving in small bursts even at generation 50 (35.58-> 38.01 over the last 20 generations), so it correctly ran the full cap instead of cutting off a search that was still working. Total time: ~171 seconda

<!-- DE-count targets and why, insert/delete mutation, constraints -->

## 5. Favorite level #1 — Grid *(Madinya)*

Submitted as `alcocer_madinya.txt` (from `src/levels/07_27_16_07_35_4.txt`).

**Numbers.** 35 generations, 395.7 seconds wall clock (plus 19.9 s to build and evaluate the
initial population), population 480, on a 10-core machine. Max fitness went 22.11 → 26.09.
Generations cost ~11 s each, of which ~10.5 s is the parallel fitness evaluation and only
~0.3 s is `generate_successors` — the pathfinding in `metrics.py` dominates everything, and it
gets *more* expensive as levels become solvable and the search has more reachable space to
expand.

**Why we like it.** The floor alternates long solid runs with gaps of 3–6 columns —
`XXXXXXXXXXXXXX---X-------XXXX-XXX-----XXX-XXXXXXXXX` — so it plays as a rhythm of run,
jump, land, rather than either a flat corridor or the hole-riddled mess the uncapped fitness
produced. 70 of 192 floor columns are gaps and the pathfinder clears them in 58 meaningful
jumps, which is exactly the "jumpy but beatable" target we set. Pipes are all correctly
grounded (a `T` with `|` running down to the floor beneath it), which is the crossover
operator's column-wise design paying off — no repair pass was ever needed for structures that
came through crossover.

**What we would fix.** The area above the floor is noisy: ~790 of 3200 tiles are decorative
blocks, coins, and enemies scattered without much structure. This is the grid encoding's
characteristic weakness — the genome has no notion of "a platform" or "a pipe", only 3200
independent tiles, so nothing in the representation resists clutter and nothing in our fitness
function directly rewards spatial coherence. `linearity` measures 0.0, meaning the solid tiles
have essentially no linear trend at all. The DE encoding (§3–4) gets this for free by
construction, and comparing the two side by side is the clearest illustration we found of the
representation tradeoff the assignment is about: the grid encoding surprises us, the DE
encoding composes.

## 6. Favorite level #2 — DE *(Alcocer)*
It's in alcocer_madinya.txt
NUmbers. 50 generation, ~155 secs, population 480. Fitness reached 36.56 and the run stopped because it hit the generation cap, not because it plateaued, it was still slowly improving at the end , so a longer run would probably do better.
Why we like it. The floor mixes solid ground with gaps of different sizes, so it's intersting and fun instead of flat or hold filled. The pipes are placed correctly, and there's real staircase instead of random blocks. Enemies and blocks are spread out instead of clumped together. Compared to the grid level, this one looks less cluttered, since each DE element is a whole object (a pipe, a platform) instead of one of 3200 separate tiles
what was fixed. By the last generation, the top individuals were mostly near duplicates of each other so more mutation or a longer run helped with that.
Grid vs. DE. The grid encoding can surprise you good or bad. The DE encoding builds from real level pieces, so it looks more like an actual MArio level, but tis also more limited in what it can priduce. We picked our favorite by looking at the levels.

<!-- why we like it, generations, wall-clock seconds -->
