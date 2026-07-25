# P5 Evolving Mario Levels — two-person work split

## Context

P5 asks for a genetic algorithm producing Super Mario levels in two encodings
(`Individual_Grid`, `Individual_DE`), graded 7 points code + 3 points writeup.
Nearly all the work lands in one file — `src/ga.py` — which makes a 2-person split
mostly a *merge-conflict* problem, not a workload problem. This plan splits by
**code region ownership** so the two people almost never touch the same lines,
and orders the one true dependency (`generate_successors` is shared by both
encodings, so it must land before the DE half can be run).

Owners: **Madinya** = Selection + Grid encoding. **Alcocer** = DE encoding + writeup
assembly. (Swap freely — the split is symmetric in effort.)

## Facts found while reading the repo

These are real and will bite whoever hits them first, so they're assigned explicitly:

- **`src/levels/` does not exist.** `ga.py:387` does `open("levels/last.txt", 'w')`
  → crashes on generation 2. Must `mkdir` + commit a `.gitkeep`.
- **`scipy` is not installed** in this environment (`numpy` may be). `pip install numpy scipy`.
- **`ga.py:343` `Individual = Individual_Grid`** is the encoding switch. Both people need
  to flip it locally → guaranteed recurring merge conflict. Fix once, in Phase 0.
- **`generate_children` never calls `mutate`** in `Individual_Grid` (`ga.py:79-91`) —
  the comment says "do mutation" but no call exists. Grid owner must add it.
- **`Individual_Grid.random_individual` (`ga.py:111-121`) has two no-op lines**:
  `g[8:14][-1] = ["f"] * 6` and `g[14:16][-1] = ["X", "X"]` assign into a temporary
  slice copy, so random individuals get no goal flag/flagpole column at all
  (unlike `empty_individual`, which does it correctly with a loop).
- **`Individual_DE.generate_children` (`ga.py:264`)** calls
  `random.randint(0, len(self.genome) - 1)` → `ValueError` on an empty genome, and
  `empty_individual` returns exactly that (`[]`). DE owner must guard it.
- **`Individual_Grid.generate_children` returns 1 child; `Individual_DE` returns 2.**
  `generate_successors` must not assume a fixed child count.
- `os.cpu_count()` here is 10, `pop_limit = 480` → 48/batch, divides evenly. Leave it.

## Phase 0 — shared setup (one person, ~10 min, commit to `main` first)

Both branches start from this commit.

1. `pip install numpy scipy`
2. `mkdir -p src/levels && touch src/levels/.gitkeep`
3. Replace `ga.py:343` with an env-var switch so neither person edits it again:
   ```python
   Individual = Individual_DE if os.environ.get("DE") else Individual_Grid
   ```
   (`os` is already imported at `ga.py:5`.) Grid runs as `python3 ga.py`,
   DE runs as `DE=1 python3 ga.py`.
4. Write the writeup skeleton `writeup.md` with empty owned sections (below) so both
   people append to disjoint parts of the file.
5. Branches: `git checkout -b grid-selection` / `git checkout -b de-encoding`.

## Phase 1 — BLOCKING: `generate_successors` (Madinya, do this first)

`ga.py:346-350`. Both encodings call it, so Alcocer cannot run a DE search until it
exists. Land it on `main` before Phase 2 starts (or hand Alcocer the branch).

Requirement is **at least two selection strategies**. Recommended combination:

- **Elitism**: copy the top ~5% by `Individual.fitness()` straight through (cheap
  insurance against losing the best level; use `sorted(...)` or `heapq.nlargest`).
- **Tournament selection** (k≈5) for the remaining ~95%: sample k individuals at
  random, take the fittest as parent A, repeat for parent B, call
  `a.generate_children(b)`, extend `results` with whatever comes back.

Critical details:

- Loop `while len(results) < len(population)` and `results.extend(children)` —
  Grid yields 1 child, DE yields 2. Then truncate to `len(population)` so the
  population size stays fixed at 480 across generations.
- `fitness()` is cached per individual, so calling it inside a tournament loop is
  cheap. Do **not** call `calculate_fitness()` — `ga()` already does that in parallel.
- Put the knobs (`ELITE_FRAC`, `TOURNAMENT_K`) at module level as named constants —
  the assignment explicitly wants parameter experiments in the writeup, and this makes
  them one-line edits. Leave a `# ponytail:` comment noting tournament k is the
  explore/exploit knob.

Verify: `python3 ga.py` survives 3+ generations with max fitness trending up, and
`levels/last.txt` is 16 lines of 200 chars.

## Phase 2A — Grid encoding (Madinya, `ga.py:32-121`)

1. **`generate_children` (`ga.py:79-91`) — crossover.** Recommend **single-point
   crossover by column**: pick one `x_cut` in `[1, width-1)`, take self's columns left
   of it and other's columns from it rightward, and return **both** children (the
   second being the complement, i.e. the genes each parent "left behind"). Column-wise
   beats tile-wise here because vertical structures (pipe `T` over `|`, stairs) stay
   intact — say exactly this in the writeup. End with
   `return (Individual_Grid(self.mutate(child_a)), Individual_Grid(self.mutate(child_b)))`
   — the missing `mutate` call.
2. **`mutate` (`ga.py:66-76`).** Per-tile rate around `0.005`–`0.02` (tune it; note the
   chosen value and why in the writeup). Use a **weighted** tile choice, not
   `random.choice(options)` — heavy `-`, light `X`/`?`/`o`/`E`, very light `|`/`T`
   (`random.choices(options, weights=[...])`). Constraints: never touch column 0 or
   `width-1`, never touch row 15 (the floor), and when placing a `T` fill `|` down to
   the floor so no pipes float. Keep the `left = 1 / right = width - 1` bounds already there.
3. **`calculate_fitness` coefficients (`ga.py:47-54`).** State a design goal in one
   sentence (e.g. "jumpy, coin-rich, definitely solvable"), then move the weights toward
   it — keep `solvability` dominant, raise `meaningfulJumps`/`jumps`, keep `linearity`
   negative. Optional: add a metric to `metrics.py` (e.g. enemy count or coin density);
   only do this if the required work is already done.
4. **Population init (`ga.py:111-121`).** Fix the two no-op lines so random individuals
   get the goal column (copy `empty_individual`'s loop at `ga.py:105-108`). Optionally
   bias the random fill toward `-` and seed a few individuals from `src/level.txt` —
   real-level seeds are cheap biodiversity and are worth a writeup paragraph.

## Phase 2B — DE encoding (Alcocer, `ga.py:143-340`)

1. **Explain, don't rewrite, the given operators** (this is a graded writeup item):
   - `generate_children` (`ga.py:262-273`): **variable-point crossover** — an
     independent cut `pa` in parent A and `pb` in parent B, child 1 = `A[:pa] + B[pb:]`,
     child 2 = `B[:pb] + A[pa:]`. Because the two cut points are independent, child
     *length* varies (unlike single-point on a fixed-length genome), so the number of
     design elements drifts across generations — that's the diversity mechanism.
     `__init__` re-heapifies, so DE ordering stays canonical. Include an ASCII diagram.
   - `mutate` (`ga.py:182-260`): 10% chance to perturb exactly one randomly chosen DE;
     which *parameter* changes is a per-type `choice` branch; numeric params move via
     `offset_by_upto(val, variance)` = add `normalvariate(0, sqrt(variance))` then clip
     — so small nudges are common and big jumps rare. Note `"2_enemy"` has no mutable
     parameter (`pass`) and that the DE is popped and re-pushed to keep the heap valid.
2. **Guard the empty genome** in `generate_children` (`ga.py:264-265`): if either genome
   is empty, `randint` raises. `pa = random.randint(0, len(self.genome)) if self.genome else 0`
   (or return the non-empty parent's children).
3. **Improve DE fitness (`ga.py:155-175`).** This is where the DE encoding earns its
   keep — count DE types with the existing `filter(lambda de: de[1] == ...)` pattern at
   `ga.py:170` and penalize deviation from a target budget you pick, e.g. holes 4–8,
   platforms 3–6, pipes 2–4, enemies 5–15, coins 10–25, stairs ≤3. Keep the existing
   stairs penalty. Document the targets in the writeup as your design intent.
4. **Improve DE mutation.** Raise the 0.1 rate, and add **insert** and **delete** DE
   operations — length-changing mutation is the main thing missing, and it pairs with
   the variable-length crossover. Constrain generation so pipes sit on the ground and
   platforms stay above it.
5. **Seed `empty_individual` / `random_individual` (`ga.py:320-340`)** — `empty_individual`
   returning `[]` gives a genome that can't crossover meaningfully; seed a handful of DEs.
6. Run `DE=1 python3 ga.py`, harvest a favorite level from `src/levels/`.

## Phase 3 — writeup + deliverables (both)

`writeup.md`, disjoint sections so the merge is trivial:

| Section | Owner |
| --- | --- |
| Selection strategies (elitism + tournament), parameters tried, what changed in results | Madinya |
| Grid: crossover choice + why column-wise, mutation rate/operator, fitness weights, init changes | Madinya |
| DE: crossover + mutation explanation with diagram (graded item) | Alcocer |
| DE: fitness redesign, DE-count targets, mutation additions | Alcocer |
| Favorite level #1 (Grid) — why, generations, seconds | Madinya |
| Favorite level #2 (DE) — why, generations, seconds | Alcocer |

**Capture generation count and wall-clock while running** — `ga.py` prints `Generation:`
and `Net time:` every generation; screenshot or copy the last lines before ctrl-c.
Reconstructing these numbers afterwards is impossible.

Submission files:
- `src/ga.py` (merged), `src/metrics.py` if changed.
- One favorite level copied to `alcocer_madinya.txt` (assignment names it
  `lastName1_lastName2.txt`).
- `writeup.md`.

## Phase 4 — stretch only: FI-2POP (Alcocer)

**Last-day-only work, if both required halves are done and verified.** Sketch: add a
`_constraint` slot to `Individual_DE`, split `ga()`'s population into feasible (solvable)
and infeasible lists, evolve each with its own fitness meaning, and route each child by
its `solvability` metric. Do not start this while anything above is unfinished.

## Verification

Run from `/home/smadinya/GameAI/EvolvingMario/src`:

1. `python3 ga.py` — Grid. Let it run ~5 generations, ctrl-c. Expect max fitness to
   increase, no exceptions, `levels/last.txt` written each generation.
2. `DE=1 python3 ga.py` — same for DE.
3. Eyeball `levels/last.txt`: 16 rows × 200 chars, `m` at row 14 col 0, flag column at
   the right edge, no floating pipe tops.
4. One committed self-check, `src/test_ga.py` — plain asserts, no framework, run with
   `python3 test_ga.py`:
   - `len(generate_successors(pop)) == len(pop)` for a small pop of each encoding
   - every child level is exactly 16×200 and column 0 / column 199 are unchanged from
     `empty_individual`
   - `Individual_DE.generate_children` on two empty genomes does not raise
   - `metrics.metrics(best.to_level())["solvability"] == 1` for the chosen favorite level
5. Optional, if the Unity player is used: `python3 copy_level.py levels/last.txt`.

## Coordination rules

- Ownership is by line range in `ga.py`: Madinya owns lines ~32-121 + ~346-350,
  Alcocer owns ~143-340 + `ga()`. Stay inside your range; if you need a change outside
  it, ask rather than edit.
- Phase 0 and Phase 1 land on `main` before Phase 2 branches diverge.
- Merge Phase 2 branches into `main` before starting Phase 3.
