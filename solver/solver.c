/*
 * EvoHive P0 baseline solver for AlphaEvolve Problem 59 (TRI-19).
 *
 * Finds a subset of the 32 x 32 integer grid with no isosceles triangle
 * (degenerate collinear "flat" triples included, matching the upstream
 * verifier), from an EMPTY state. It never reads a file and contains no
 * hardcoded point list: the public 58-point certificate is only an external
 * target for the controller, never an initialization.
 *
 * Search space: sets symmetric under the mirror y -> 31-y. A move unit is a
 * mirror pair {(x,y), (x,31-y)}, y in 0..15, so every state has EVEN size.
 * NOTE: this baseline exists to reproduce 58. It can reach 56/58/60 but never
 * 59; a later record-search operator must break the mirror symmetry.
 *
 * Exact incremental structure (all integer, no floating point):
 *   cnt[c][d]  number of selected points at squared distance d from cell c
 *   tri[c]     number of unordered selected pairs equidistant from c
 *              (= sum over d>0 of C(cnt[c][d], 2)); "c would be an apex"
 *   blk[c]     number of ordered (apex p, other r) selected with
 *              d(p,c) == d(p,r), c not in {p,r}; "c would be a base end"
 * Adding point c to set S creates exactly tri[c] + blk[c] isosceles triples,
 * and removing it destroys exactly that many, so the violation count V is
 * maintained exactly. Add and remove are exact inverses.
 *
 * Algorithm (deterministic for fixed --seed and --iters):
 *   1. Seeded construction: scan mirror pairs in seeded random order, adding
 *      each pair that creates no violation, until the set is maximal.
 *   2. Conflict-guided ruin/repair with a tabu list at fixed cardinality:
 *      force in the cheapest extra pair (temporary infeasibility), then each
 *      iteration ruins the most conflicted pair (with probability
 *      NOISE_PCT% a uniformly random conflicted pair instead) and repairs
 *      with the cheapest non-tabu pair. When V returns to 0 the set is re-checked by an
 *      independent brute-force pass, recorded as the incumbent, and the
 *      cardinality is raised again.
 *   The run stops after exactly --iters ruin/repair iterations or when the
 *   incumbent reaches --target (default 58).
 *
 * Output: one JSON object on stdout. Diagnostics go to stderr only.
 * Exit codes: 0 ok, 2 malformed arguments, 3 internal consistency failure.
 *
 * Build: cc -O2 -std=c99 -Wall -Wextra -Werror -o build/solver solver/solver.c
 */
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define SOLVER_VERSION "evohive-symtabu-c99-1 noise=20 tabu=3+rand10"
#define N 32
#define CELLS (N * N)
#define HALF (N / 2)
#define PAIRS (N * HALF)
#define MAXD (2 * (N - 1) * (N - 1))
#define OFFSETS ((2 * N - 1) * (2 * N - 1))
/* Search parameters frozen after calibration on off-gate seeds 1000..1015
 * (never on the gate seeds 0..63). Overridable with -D for calibration only;
 * the controller always builds with these defaults. */
#ifndef TABU_BASE
#define TABU_BASE 3
#endif
#define TABU_RAND 10
#ifndef NOISE_PCT
#define NOISE_PCT 20
#endif
#define MAX_POINTS 250 /* cnt is uint8_t */

static uint8_t cnt[CELLS][MAXD + 1];
static int32_t tri[CELLS];
static int32_t blk[CELLS];
static uint8_t sel[CELLS];
static int selpts[CELLS];
static int selpos[CELLS];
static int nsel;
static long violations;

static int circ_start[MAXD + 2];
static int8_t circ_dx[OFFSETS];
static int8_t circ_dy[OFFSETS];

static uint64_t rng_state;

static uint64_t rng_next(void) { /* splitmix64 */
    uint64_t z = (rng_state += 0x9E3779B97F4A7C15ULL);
    z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
    z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
    return z ^ (z >> 31);
}

static int rng_below(int n) { return (int)(rng_next() % (uint64_t)n); }

static void build_circles(void) {
    int fill[MAXD + 2];
    memset(circ_start, 0, sizeof circ_start);
    for (int dx = -(N - 1); dx < N; dx++)
        for (int dy = -(N - 1); dy < N; dy++)
            if (dx || dy) circ_start[dx * dx + dy * dy + 1]++;
    for (int d = 0; d <= MAXD; d++) circ_start[d + 1] += circ_start[d];
    memcpy(fill, circ_start, sizeof fill);
    for (int dx = -(N - 1); dx < N; dx++)
        for (int dy = -(N - 1); dy < N; dy++)
            if (dx || dy) {
                int k = fill[dx * dx + dy * dy]++;
                circ_dx[k] = (int8_t)dx;
                circ_dy[k] = (int8_t)dy;
            }
}

static int sqdist(int a, int b) {
    int dx = a / N - b / N, dy = a % N - b % N;
    return dx * dx + dy * dy;
}

/* blk[c] += delta for every cell c != skip at squared distance d from center */
static void circle_bump(int center, int d, int skip, int delta) {
    int cx = center / N, cy = center % N;
    for (int k = circ_start[d]; k < circ_start[d + 1]; k++) {
        int x = cx + circ_dx[k], y = cy + circ_dy[k];
        if (x < 0 || x >= N || y < 0 || y >= N) continue;
        int c = x * N + y;
        if (c != skip) blk[c] += delta;
    }
}

static void point_add(int r) {
    int rx = r / N, ry = r % N;
    violations += tri[r] + blk[r];
    for (int i = 0; i < nsel; i++) {
        int p = selpts[i], d = sqdist(p, r);
        circle_bump(p, d, r, 1);
        circle_bump(r, d, p, 1);
    }
    for (int x = 0; x < N; x++)
        for (int y = 0; y < N; y++) {
            int c = x * N + y, d = (x - rx) * (x - rx) + (y - ry) * (y - ry);
            tri[c] += cnt[c][d]++;
        }
    sel[r] = 1;
    selpos[r] = nsel;
    selpts[nsel++] = r;
}

static void point_remove(int r) {
    int rx = r / N, ry = r % N;
    int last = selpts[--nsel];
    selpts[selpos[r]] = last;
    selpos[last] = selpos[r];
    sel[r] = 0;
    for (int i = 0; i < nsel; i++) {
        int p = selpts[i], d = sqdist(p, r);
        circle_bump(p, d, r, -1);
        circle_bump(r, d, p, -1);
    }
    for (int x = 0; x < N; x++)
        for (int y = 0; y < N; y++) {
            int c = x * N + y, d = (x - rx) * (x - rx) + (y - ry) * (y - ry);
            tri[c] -= --cnt[c][d];
        }
    violations -= tri[r] + blk[r];
}

/* mirror pair u = x*HALF + y, y in 0..15: cells (x,y) and (x,31-y) */
static int pair_low(int u) { return (u / HALF) * N + u % HALF; }
static int pair_high(int u) { return (u / HALF) * N + (N - 1 - u % HALF); }

static void pair_add(int u) {
    point_add(pair_low(u));
    point_add(pair_high(u));
}

static void pair_remove(int u) {
    point_remove(pair_high(u));
    point_remove(pair_low(u));
}

/* Violations created by adding unselected pair u to a mirror-symmetric set.
 * By symmetry both halves cost the same; the cross term counts triples that
 * contain both halves (no lattice apex lies on the axis y = 15.5). */
static long pair_add_cost(int u) {
    int q = pair_low(u), gap = N - 1 - 2 * (u % HALF);
    return 2L * (tri[q] + blk[q] + cnt[q][gap * gap]);
}

/* Independent O(n^2) recheck: no apex sees a repeated distance. */
static int brute_force_valid(void) {
    static int stamp[MAXD + 1];
    static int epoch;
    for (int i = 0; i < nsel; i++) {
        epoch++;
        for (int j = 0; j < nsel; j++) {
            if (i == j) continue;
            int d = sqdist(selpts[i], selpts[j]);
            if (stamp[d] == epoch) return 0;
            stamp[d] = epoch;
        }
    }
    return 1;
}

static int parse_u64(const char *text, uint64_t *out) {
    char *end = NULL;
    if (text == NULL || *text < '0' || *text > '9') return 0;
    errno = 0;
    unsigned long long value = strtoull(text, &end, 10);
    if (errno != 0 || *end != '\0') return 0;
    *out = (uint64_t)value;
    return 1;
}

static int usage(const char *why) {
    fprintf(stderr, "solver: %s\nusage: solver --seed <u64> --iters <u64> [--target <even 2..%d>]\n",
            why, MAX_POINTS);
    return 2;
}

int main(int argc, char **argv) {
    uint64_t seed = 0, iters = 0, target = 58;
    int have_seed = 0, have_iters = 0;
    for (int i = 1; i < argc; i += 2) {
        uint64_t *slot = NULL;
        if (strcmp(argv[i], "--seed") == 0) { slot = &seed; have_seed = 1; }
        else if (strcmp(argv[i], "--iters") == 0) { slot = &iters; have_iters = 1; }
        else if (strcmp(argv[i], "--target") == 0) slot = &target;
        else return usage("unknown argument");
        if (i + 1 >= argc || !parse_u64(argv[i + 1], slot)) return usage("malformed value");
    }
    if (!have_seed || !have_iters) return usage("--seed and --iters are required");
    if (target < 2 || target > MAX_POINTS || target % 2 != 0) return usage("bad --target");

    rng_state = seed;
    build_circles();

    static int order[PAIRS];
    static uint8_t pair_sel[PAIRS];
    static uint64_t tabu_until[PAIRS];
    static int best[CELLS];
    int best_n = 0, npairs = 0;
    uint64_t moves = 0, point_adds = 0, point_removes = 0, levels = 0;
    uint64_t construction_adds = 0, aspirations = 0;
    long level_best = 0;
    const char *reason = "iterations_exhausted";

    /* 1. seeded greedy construction from the empty set */
    for (int u = 0; u < PAIRS; u++) order[u] = u;
    for (int u = PAIRS - 1; u > 0; u--) {
        int k = rng_below(u + 1), t = order[u];
        order[u] = order[k];
        order[k] = t;
    }
    for (int i = 0; i < PAIRS; i++) {
        int u = order[i];
        if (pair_add_cost(u) == 0) {
            pair_add(u);
            pair_sel[u] = 1;
            npairs++;
            point_adds += 2;
            construction_adds++;
        }
    }

    /* 2. conflict-guided ruin/repair at increasing fixed cardinality */
    for (;;) {
        if (violations == 0) {
            if (!brute_force_valid()) {
                fprintf(stderr, "solver: incremental state disagrees with brute force\n");
                return 3;
            }
            best_n = nsel;
            memcpy(best, selpts, sizeof(int) * (size_t)nsel);
            if ((uint64_t)best_n >= target) { reason = "target_reached"; break; }
            if (moves >= iters) break;
            if (nsel + 2 > MAX_POINTS) { reason = "capacity_reached"; break; }
            /* raise cardinality: force in the cheapest pair */
            int pick = -1, ties = 0;
            long low = 0;
            for (int u = 0; u < PAIRS; u++) {
                if (pair_sel[u]) continue;
                long cost = pair_add_cost(u);
                if (pick < 0 || cost < low) { pick = u; low = cost; ties = 1; }
                else if (cost == low && rng_below(++ties) == 0) pick = u;
            }
            if (pick < 0) { reason = "grid_full"; break; }
            pair_add(pick);
            pair_sel[pick] = 1;
            npairs++;
            point_adds += 2;
            levels++;
            level_best = violations;
            continue;
        }
        if (moves >= iters) break;
        moves++;

        /* ruin: the most conflicted pair (random ties), or with probability
         * NOISE_PCT percent a uniformly random conflicted pair */
        int out = -1, seen = 0, worst = 0, noisy = rng_below(100) < NOISE_PCT;
        for (int u = 0; u < PAIRS; u++) {
            if (!pair_sel[u]) continue;
            int q = pair_low(u), conf = tri[q] + blk[q];
            if (conf <= 0) continue;
            if (noisy) { if (rng_below(++seen) == 0) out = u; }
            else if (conf > worst) { out = u; worst = conf; seen = 1; }
            else if (conf == worst && rng_below(++seen) == 0) out = u;
        }
        pair_remove(out);
        pair_sel[out] = 0;
        point_removes += 2;
        tabu_until[out] = moves + TABU_BASE + (uint64_t)rng_below(TABU_RAND);

        /* repair: cheapest pair that is not tabu (aspiration: new level best) */
        int in = -1, ties = 0, used_aspiration = 0;
        long low = 0;
        for (int u = 0; u < PAIRS; u++) {
            if (pair_sel[u]) continue;
            long cost = pair_add_cost(u);
            int aspire = violations + cost < level_best;
            if (tabu_until[u] > moves && !aspire) continue;
            if (in < 0 || cost < low) {
                in = u; low = cost; ties = 1;
                used_aspiration = tabu_until[u] > moves;
            } else if (cost == low && rng_below(++ties) == 0) {
                in = u;
                used_aspiration = tabu_until[u] > moves;
            }
        }
        if (in < 0) in = out; /* everything tabu: undo */
        pair_add(in);
        pair_sel[in] = 1;
        point_adds += 2;
        aspirations += (uint64_t)used_aspiration;
        if (violations < level_best) level_best = violations;
    }

    /* canonical output: points sorted by (x, y) */
    static uint8_t in_best[CELLS];
    for (int i = 0; i < best_n; i++) in_best[best[i]] = 1;
    printf("{\"solver_version\":\"%s\",\"grid_size\":%d,\"symmetry\":\"y->%d-y\","
           "\"seed\":%llu,\"iters\":%llu,\"target\":%llu,\"score\":%d,"
           "\"termination_reason\":\"%s\",\"counters\":{\"ruin_repair_moves\":%llu,"
           "\"point_adds\":%llu,\"point_removes\":%llu,\"construction_pair_adds\":%llu,"
           "\"cardinality_raises\":%llu,\"aspirations\":%llu,"
           "\"final_working_pairs\":%d,\"final_working_violations\":%ld},\"points\":[",
           SOLVER_VERSION, N, N - 1, (unsigned long long)seed, (unsigned long long)iters,
           (unsigned long long)target, best_n, reason, (unsigned long long)moves,
           (unsigned long long)point_adds, (unsigned long long)point_removes,
           (unsigned long long)construction_adds, (unsigned long long)levels,
           (unsigned long long)aspirations, npairs, violations);
    for (int c = 0, first = 1; c < CELLS; c++)
        if (in_best[c]) {
            printf("%s[%d,%d]", first ? "" : ",", c / N, c % N);
            first = 0;
        }
    printf("]}\n");
    return fflush(stdout) == 0 ? 0 : 3;
}
