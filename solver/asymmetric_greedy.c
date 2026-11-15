/* Deterministic asymmetric-from-scratch canary selected by the P3 policy. */
#include <errno.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define GRID 32
#define CELLS (GRID * GRID)
#define MAX_POINTS CELLS

typedef struct {
    int x;
    int y;
} Point;

static uint64_t state;

static uint64_t next_random(void) {
    uint64_t x = state;
    x ^= x >> 12;
    x ^= x << 25;
    x ^= x >> 27;
    state = x;
    return x * UINT64_C(2685821657736338717);
}

static int distance_squared(Point a, Point b) {
    int dx = a.x - b.x;
    int dy = a.y - b.y;
    return dx * dx + dy * dy;
}

static int can_add(const Point *points, int count, Point candidate) {
    int i;
    int j;
    for (i = 0; i < count; ++i) {
        for (j = i + 1; j < count; ++j) {
            int ab = distance_squared(points[i], points[j]);
            int ac = distance_squared(points[i], candidate);
            int bc = distance_squared(points[j], candidate);
            if (ab == ac || ab == bc || ac == bc) {
                return 0;
            }
        }
    }
    return 1;
}

static void shuffle(int *cells) {
    int i;
    for (i = CELLS - 1; i > 0; --i) {
        int j = (int)(next_random() % (uint64_t)(i + 1));
        int temp = cells[i];
        cells[i] = cells[j];
        cells[j] = temp;
    }
}

static uint64_t parse_number(const char *text, const char *name) {
    char *end = NULL;
    unsigned long long value;
    errno = 0;
    value = strtoull(text, &end, 10);
    if (errno != 0 || end == text || *end != '\0') {
        fprintf(stderr, "invalid %s: %s\n", name, text);
        exit(2);
    }
    return (uint64_t)value;
}

int main(int argc, char **argv) {
    uint64_t seed = 0;
    uint64_t restarts = 0;
    uint64_t restart;
    uint64_t checks = 0;
    int cells[CELLS];
    Point current[MAX_POINTS];
    Point best[MAX_POINTS];
    int best_count = 0;
    int i;

    if (argc != 5 || strcmp(argv[1], "--seed") != 0 || strcmp(argv[3], "--iters") != 0) {
        fprintf(stderr, "usage: %s --seed N --iters N\n", argv[0]);
        return 2;
    }
    seed = parse_number(argv[2], "seed");
    restarts = parse_number(argv[4], "iters");
    if (restarts == 0) {
        fprintf(stderr, "iters must be positive\n");
        return 2;
    }
    state = seed ^ UINT64_C(0x9e3779b97f4a7c15);
    if (state == 0) {
        state = UINT64_C(0x2545f4914f6cdd1d);
    }

    for (restart = 0; restart < restarts; ++restart) {
        int count = 0;
        for (i = 0; i < CELLS; ++i) {
            cells[i] = i;
        }
        shuffle(cells);
        for (i = 0; i < CELLS; ++i) {
            Point candidate = {cells[i] % GRID, cells[i] / GRID};
            ++checks;
            if (can_add(current, count, candidate)) {
                current[count++] = candidate;
            }
        }
        if (count > best_count) {
            best_count = count;
            memcpy(best, current, (size_t)count * sizeof(Point));
        }
    }

    printf("{\"seed\":%" PRIu64 ",\"iters\":%" PRIu64 ",\"grid_size\":%d,", seed,
           restarts, GRID);
    printf("\"points\":[");
    for (i = 0; i < best_count; ++i) {
        printf("%s[%d,%d]", i == 0 ? "" : ",", best[i].x, best[i].y);
    }
    printf("],\"score\":%d,\"counters\":{\"restarts\":%" PRIu64
           ",\"candidate_checks\":%" PRIu64 "},", best_count, restarts, checks);
    printf("\"termination_reason\":\"fixed_restart_budget\","
           "\"solver_version\":\"asymmetric-random-greedy-v1\"}\n");
    return 0;
}
