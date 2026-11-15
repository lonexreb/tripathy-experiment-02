/*
 * EvoHive P1 symmetry breaker for AlphaEvolve Problem 59 (TRI-19).
 *
 * Reads an isosceles-free point set of size target-1 on the 32 x 32 grid from
 * stdin ("count" then "x y" pairs), raises the working cardinality to
 * --target and searches ARBITRARY point sets (no mirror constraint) with
 * conflict-guided single-point swaps. It opens no file and contains no
 * hardcoded point list: points arrive as data from the controller.
 *
 * The exact incremental structure is the one frozen in solver/solver.c
 * (copied, because that file is immutable and each solver is one
 * dependency-free translation unit):
 *   cnt[c][d]  selected points at squared distance d from cell c
 *   tri[c]     unordered selected pairs equidistant from c (c as apex)
 *   blk[c]     ordered (apex p, other r) selected with d(p,c) == d(p,r)
 * For a selected point q, tri[q] + blk[q] is the number of isosceles triples
 * containing q; for an unselected cell it is the cost of adding it. Add and
 * remove are exact inverses and maintain the violation count V exactly.
 *
 * Algorithm (deterministic for fixed stdin, --seed and --iters):
 *   1. Load and validate the input; it must be isosceles-free.
 *   2. Force in the cheapest unselected point (random ties): V > 0 at
 *      cardinality target.
 *   3. Each swap removes the most conflicted selected point (with probability
 *      NOISE_PCT% a uniformly random conflicted one) and adds the cheapest
 *      non-tabu unselected point (aspiration: a new best since restart).
 *   4. After RESTART_STALL swaps without a new best since restart, rebuild
 *      the original input and force in a uniformly random unselected point.
 *   5. Stop at V == 0 (target reached) or after exactly --iters swaps.
 *
 * Invariant checks (exit 3 on any failure): V is recounted by an independent
 * brute-force pass on load, at every new minimum, before every restart, at
 * V == 0 and at exit; a restart also checks that removing every point returns
 * V, tri and blk to exactly zero.
 *
 * Output: one JSON object on stdout. "points" holds ONLY the best valid set:
 * the target-size set if found, otherwise the unchanged input.
 * "closest_approach" is the lowest-violation target-size working state; it is
 * an INVALID set unless its violations are 0 and is never accepted output.
 * Parameters were fixed a priori from the P0 solver (noise, tabu); they were
 * not tuned on any seed.
 * Exit codes: 0 ok, 2 malformed arguments or input, 3 internal inconsistency.
 *
 * Build: cc -O2 -std=c99 -Wall -Wextra -Werror -o build/symmetry_breaker solver/symmetry_breaker.c
 */
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define SOLVER_VERSION "evohive-symbreak-c99-1 noise=20 tabu=3+rand10 stall=20000"
#define N 32
#define CELLS (N * N)
#define MAXD (2 * (N - 1) * (N - 1))
#define OFFSETS ((2 * N - 1) * (2 * N - 1))
#define TABU_BASE 3
#define TABU_RAND 10
#define NOISE_PCT 20
#define RESTART_STALL 20000
#define MAX_POINTS 250 /* cnt is uint8_t */

static uint8_t cnt[CELLS][MAXD + 1];
static int32_t tri[CELLS];
static int32_t blk[CELLS];
static uint8_t sel[CELLS];
static int selpts[CELLS];
static int selpos[CELLS];
static int nsel;
static long violations;
static uint64_t brute_force_checks;

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

/* Independent exact recount: unordered selected pairs equidistant from each apex. */
static long brute_force_violations(void) {
    static int seen[MAXD + 1];
    static int stamp[MAXD + 1];
    static int epoch;
    long total = 0;
    for (int i = 0; i < nsel; i++) {
        epoch++;
        for (int j = 0; j < nsel; j++) {
            if (i == j) continue;
            int d = sqdist(selpts[i], selpts[j]);
            if (stamp[d] != epoch) { stamp[d] = epoch; seen[d] = 0; }
            total += seen[d]++;
        }
    }
    return total;
}

static void fail_internal(const char *why) {
    fprintf(stderr, "symmetry-breaker: %s\n", why);
    exit(3);
}

static void check_invariant(void) {
    brute_force_checks++;
    if (brute_force_violations() != violations)
        fail_internal("incremental state disagrees with brute force");
}

/* Unselected cell to force in: uniformly random, or the cheapest (random ties). */
static int pick_entry(int uniform) {
    int pick = -1, seen = 0;
    long low = 0;
    for (int c = 0; c < CELLS; c++) {
        if (sel[c]) continue;
        long cost = tri[c] + blk[c];
        if (uniform) { if (rng_below(++seen) == 0) pick = c; }
        else if (pick < 0 || cost < low) { pick = c; low = cost; seen = 1; }
        else if (cost == low && rng_below(++seen) == 0) pick = c;
    }
    return pick;
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

static int reject(const char *why) {
    fprintf(stderr, "symmetry-breaker: %s\n"
            "usage: symmetry-breaker --seed <u64> --iters <u64> --target <2..%d> < points\n"
            "stdin: count, then count 'x y' pairs; count must equal target-1\n",
            why, MAX_POINTS);
    return 2;
}

/* Width-limited conversions cannot overflow; an overlong number splits into
 * an extra token and is rejected as a bad point or trailing data. */
static const char *read_input(int *points, int *count) {
    static uint8_t seen[CELLS];
    int n, x, y;
    char extra;
    if (scanf("%9d", &n) != 1 || n < 1 || n >= MAX_POINTS) return "bad point count on stdin";
    for (int i = 0; i < n; i++) {
        if (scanf("%9d %9d", &x, &y) != 2 || x < 0 || x >= N || y < 0 || y >= N)
            return "bad or out-of-grid point on stdin";
        if (seen[x * N + y]++) return "duplicate point on stdin";
        points[i] = x * N + y;
    }
    if (scanf(" %c", &extra) == 1) return "trailing data on stdin";
    *count = n;
    return NULL;
}

static void print_cells(const int *cells, int count) {
    static uint8_t member[CELLS];
    memset(member, 0, sizeof member);
    for (int i = 0; i < count; i++) member[cells[i]] = 1;
    for (int c = 0, first = 1; c < CELLS; c++) /* canonical: sorted by (x, y) */
        if (member[c]) {
            printf("%s[%d,%d]", first ? "" : ",", c / N, c % N);
            first = 0;
        }
}

int main(int argc, char **argv) {
    uint64_t seed = 0, iters = 0, target = 0;
    int have = 0;
    for (int i = 1; i < argc; i += 2) {
        uint64_t *slot = NULL;
        if (strcmp(argv[i], "--seed") == 0) { slot = &seed; have |= 1; }
        else if (strcmp(argv[i], "--iters") == 0) { slot = &iters; have |= 2; }
        else if (strcmp(argv[i], "--target") == 0) { slot = &target; have |= 4; }
        else return reject("unknown argument");
        if (i + 1 >= argc || !parse_u64(argv[i + 1], slot)) return reject("malformed value");
    }
    if (have != 7) return reject("--seed, --iters and --target are required");
    if (target < 2 || target > MAX_POINTS) return reject("bad --target");

    static int initial[CELLS], best[CELLS], closest[CELLS];
    static uint64_t tabu_until[CELLS];
    int n0 = 0;
    const char *problem = read_input(initial, &n0);
    if (problem != NULL) return reject(problem);
    if ((uint64_t)n0 + 1 != target) return reject("input count must equal target-1");

    rng_state = seed;
    build_circles();
    for (int i = 0; i < n0; i++) point_add(initial[i]);
    if (violations != 0) return reject("input set is not isosceles-free");
    check_invariant();

    int best_n = n0, closest_n = 0;
    memcpy(best, initial, sizeof(int) * (size_t)n0);
    uint64_t swaps = 0, restarts = 0, point_adds = 0, point_removes = 0, aspirations = 0;
    uint64_t stall = 0, min_at = 0;
    long min_violations = -1, level_best;
    const char *reason = "iterations_exhausted";

    point_add(pick_entry(0)); /* 2. raise the working cardinality to target */
    point_adds++;
    level_best = violations;

    for (;;) {
        if (min_violations < 0 || violations < min_violations) {
            check_invariant();
            min_violations = violations;
            min_at = swaps;
            closest_n = nsel;
            memcpy(closest, selpts, sizeof(int) * (size_t)nsel);
        }
        if (violations == 0) {
            best_n = nsel;
            memcpy(best, selpts, sizeof(int) * (size_t)nsel);
            reason = "target_reached";
            break;
        }
        if (swaps >= iters) break;

        if (stall >= RESTART_STALL) { /* 4. restart from the original input */
            check_invariant();
            while (nsel > 0) point_remove(selpts[nsel - 1]);
            if (violations != 0) fail_internal("remove is not the inverse of add");
            for (int c = 0; c < CELLS; c++)
                if (tri[c] != 0 || blk[c] != 0) fail_internal("counters not zero when empty");
            for (int i = 0; i < n0; i++) point_add(initial[i]);
            if (violations != 0) fail_internal("rebuilt input is not isosceles-free");
            memset(tabu_until, 0, sizeof tabu_until);
            point_add(pick_entry(1));
            point_adds++;
            restarts++;
            level_best = violations;
            stall = 0;
            continue;
        }
        swaps++;

        /* remove: the most conflicted point (random ties), or with probability
         * NOISE_PCT percent a uniformly random conflicted point */
        int out = -1, seen = 0, worst = 0, noisy = rng_below(100) < NOISE_PCT;
        for (int i = 0; i < nsel; i++) {
            int q = selpts[i], conf = tri[q] + blk[q];
            if (conf <= 0) continue;
            if (noisy) { if (rng_below(++seen) == 0) out = q; }
            else if (conf > worst) { out = q; worst = conf; seen = 1; }
            else if (conf == worst && rng_below(++seen) == 0) out = q;
        }
        point_remove(out);
        point_removes++;
        tabu_until[out] = swaps + TABU_BASE + (uint64_t)rng_below(TABU_RAND);

        /* add: cheapest cell that is not tabu (aspiration: new best since restart) */
        int in = -1, ties = 0, used_aspiration = 0;
        long low = 0;
        for (int c = 0; c < CELLS; c++) {
            if (sel[c]) continue;
            long cost = tri[c] + blk[c];
            int is_tabu = tabu_until[c] > swaps;
            if (is_tabu && violations + cost >= level_best) continue;
            if (in < 0 || cost < low) { in = c; low = cost; ties = 1; used_aspiration = is_tabu; }
            else if (cost == low && rng_below(++ties) == 0) { in = c; used_aspiration = is_tabu; }
        }
        if (in < 0) in = out; /* everything tabu: undo */
        point_add(in);
        point_adds++;
        aspirations += (uint64_t)used_aspiration;
        if (violations < level_best) { level_best = violations; stall = 0; }
        else stall++;
    }
    check_invariant();

    printf("{\"solver_version\":\"%s\",\"grid_size\":%d,\"seed\":%llu,\"iters\":%llu,"
           "\"target\":%llu,\"input_count\":%d,\"score\":%d,\"termination_reason\":\"%s\","
           "\"counters\":{\"swaps\":%llu,\"restarts\":%llu,\"point_adds\":%llu,"
           "\"point_removes\":%llu,\"aspirations\":%llu,\"brute_force_checks\":%llu,"
           "\"min_working_violations\":%ld,\"min_working_violations_at_swap\":%llu,"
           "\"final_working_points\":%d,\"final_working_violations\":%ld},"
           "\"closest_approach\":{\"violations\":%ld,\"points\":[",
           SOLVER_VERSION, N, (unsigned long long)seed, (unsigned long long)iters,
           (unsigned long long)target, n0, best_n, reason, (unsigned long long)swaps,
           (unsigned long long)restarts, (unsigned long long)point_adds,
           (unsigned long long)point_removes, (unsigned long long)aspirations,
           (unsigned long long)brute_force_checks, min_violations,
           (unsigned long long)min_at, nsel, violations, min_violations);
    print_cells(closest, closest_n);
    printf("]},\"points\":[");
    print_cells(best, best_n);
    printf("]}\n");
    return fflush(stdout) == 0 ? 0 : 3;
}
