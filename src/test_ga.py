"""Self-checks for ga.py.  Plain asserts, no framework: python3.12 test_ga.py"""
import random

import ga
import metrics

REFERENCE = ga.Individual_Grid.empty_individual().genome


def test_successors_keep_population_size():
    pop = [ga.Individual_Grid.random_individual() for _ in range(20)]
    kids = ga.generate_successors(pop)
    assert len(kids) == len(pop), len(kids)


def test_children_shape_and_fixed_columns():
    a = ga.Individual_Grid.random_individual()
    b = ga.Individual_Grid.random_individual()
    for child in a.generate_children(b):
        g = child.genome
        assert len(g) == ga.height, len(g)
        assert all(len(row) == ga.width for row in g)
        for y in range(ga.height):
            assert g[y][0] == REFERENCE[y][0], ("col 0", y, g[y][0])
            assert g[y][-1] == REFERENCE[y][-1], ("col -1", y, g[y][-1])


def test_mutation_constraints():
    ind = ga.Individual_Grid.random_individual()
    g = ind.mutate(ind.genome)
    for y in range(ga.height):
        for x in range(ga.width):
            if g[y][x] == "|":
                # A pipe body always has a body or a top directly above it, never air.
                assert y > 0 and g[y - 1][x] in ("|", "T"), ("floating pipe", x, y)
    # Mario's landing zone and the goal approach must stay walkable.
    assert all(g[15][x] == "X" for x in range(4)), "start columns lost their floor"
    assert all(g[15][x] == "X" for x in range(ga.width - 4, ga.width)), "goal columns lost their floor"


def test_submitted_level_is_solvable():
    """The level we actually hand in must be the right shape and beatable.

    Checks the committed submission rather than levels/last.txt, which is gitignored
    and would make this check silently skip on a fresh clone.
    """
    with open("../alcocer_madinya.txt") as f:
        level = [list(line.rstrip("\n")) for line in f]
    assert len(level) == ga.height, len(level)
    assert all(len(row) == ga.width for row in level)
    assert metrics.metrics(level)["solvability"] == 1.0, "submitted level is not solvable"


def test_de_empty_genome_does_not_raise():
    """Alcocer's Phase 2B guard.  Expected RED until his branch merges."""
    a = ga.Individual_DE.empty_individual()
    b = ga.Individual_DE.empty_individual()
    a.generate_children(b)


if __name__ == "__main__":
    random.seed(0)
    failures = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_"):
            continue
        try:
            fn()
            print("PASS", name)
        except Exception as e:
            failures += 1
            print("FAIL", name, "->", repr(e))
    print(("all good" if not failures else str(failures) + " failing"))
