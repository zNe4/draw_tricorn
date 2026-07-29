#include "numeric.h"

#include "numeric_internal.h"

#include <complex.h>
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#ifdef _OPENMP
#include <omp.h>
#endif

typedef struct {
    LoomComplex first;
    LoomComplex second;
} Segment;

typedef struct {
    Segment *items;
    size_t count;
    size_t capacity;
} SegmentVector;

typedef struct {
    int64_t x;
    int64_t y;
    LoomComplex point;
    size_t *edges;
    size_t edge_count;
    size_t edge_capacity;
} Node;

typedef struct {
    size_t first;
    size_t second;
    int visited;
} Edge;

typedef struct {
    int used;
    int64_t x;
    int64_t y;
    size_t node_index;
} HashEntry;

typedef struct {
    LoomComplex *items;
    size_t count;
    size_t capacity;
} PointVector;

typedef struct {
    LoomPolyline *items;
    size_t count;
    size_t capacity;
} PolylineVector;

typedef struct {
    LoomInternalCurve *items;
    size_t count;
    size_t capacity;
} CurveVector;

static double complex to_complex(LoomComplex value) {
    return value.real + I * value.imag;
}

static double complex power_int(double complex value, int exponent) {
    double complex result = 1.0;
    while (exponent > 0) {
        if (exponent & 1) {
            result *= value;
        }
        value *= value;
        exponent >>= 1;
    }
    return result;
}

static double complex map_value(
    double complex value,
    double complex parameter,
    int degree,
    int antiholomorphic
) {
    double complex powered = power_int(value, degree);
    return (antiholomorphic ? conj(powered) : powered) + parameter;
}

static double complex iterate_value(
    double complex value,
    double complex parameter,
    int steps,
    int degree,
    int antiholomorphic
) {
    for (int step = 0; step < steps; ++step) {
        value = map_value(value, parameter, degree, antiholomorphic);
    }
    return value;
}

static int reserve_segments(SegmentVector *vector, size_t required) {
    if (required <= vector->capacity) {
        return 1;
    }
    size_t capacity = vector->capacity == 0 ? 256 : vector->capacity;
    while (capacity < required) {
        if (capacity > SIZE_MAX / 2) {
            return 0;
        }
        capacity *= 2;
    }
    Segment *items = realloc(vector->items, capacity * sizeof(*items));
    if (items == NULL) {
        return 0;
    }
    vector->items = items;
    vector->capacity = capacity;
    return 1;
}

static int append_segment(
    SegmentVector *vector,
    LoomComplex first,
    LoomComplex second
) {
    if (!reserve_segments(vector, vector->count + 1)) {
        return 0;
    }
    vector->items[vector->count++] = (Segment){first, second};
    return 1;
}

static int reserve_points(PointVector *vector, size_t required) {
    if (required <= vector->capacity) {
        return 1;
    }
    size_t capacity = vector->capacity == 0 ? 512 : vector->capacity;
    while (capacity < required) {
        if (capacity > SIZE_MAX / 2) {
            return 0;
        }
        capacity *= 2;
    }
    LoomComplex *items = realloc(vector->items, capacity * sizeof(*items));
    if (items == NULL) {
        return 0;
    }
    vector->items = items;
    vector->capacity = capacity;
    return 1;
}

static int append_point(PointVector *vector, LoomComplex point) {
    if (!reserve_points(vector, vector->count + 1)) {
        return 0;
    }
    vector->items[vector->count++] = point;
    return 1;
}

static int append_polyline(
    PolylineVector *vector,
    size_t first_point,
    size_t point_count
) {
    if (vector->count == vector->capacity) {
        size_t capacity = vector->capacity == 0 ? 64 : vector->capacity * 2;
        LoomPolyline *items = realloc(
            vector->items, capacity * sizeof(*items)
        );
        if (items == NULL) {
            return 0;
        }
        vector->items = items;
        vector->capacity = capacity;
    }
    vector->items[vector->count++] = (LoomPolyline){first_point, point_count};
    return 1;
}

static int append_curve(
    CurveVector *vector,
    double log_radius,
    size_t first_polyline,
    size_t polyline_count,
    int representative
) {
    if (vector->count == vector->capacity) {
        size_t capacity = vector->capacity == 0 ? 16 : vector->capacity * 2;
        LoomInternalCurve *items = realloc(
            vector->items, capacity * sizeof(*items)
        );
        if (items == NULL) {
            return 0;
        }
        vector->items = items;
        vector->capacity = capacity;
    }
    vector->items[vector->count++] = (LoomInternalCurve){
        log_radius,
        first_polyline,
        polyline_count,
        representative,
    };
    return 1;
}

static LoomComplex interpolate(
    LoomComplex first,
    LoomComplex second,
    double first_value,
    double second_value,
    double level
) {
    double difference = second_value - first_value;
    double amount = difference == 0.0
        ? 0.5
        : (level - first_value) / difference;
    if (amount < 0.0) {
        amount = 0.0;
    } else if (amount > 1.0) {
        amount = 1.0;
    }
    return (LoomComplex){
        first.real + amount * (second.real - first.real),
        first.imag + amount * (second.imag - first.imag),
    };
}

static int marching_segments(
    const double *field,
    int resolution,
    double xmin,
    double xmax,
    double ymin,
    double ymax,
    double level,
    SegmentVector *segments
) {
    static const int pair_count[16] = {
        0, 1, 1, 1, 1, 2, 1, 1, 1, 1, 2, 1, 1, 1, 1, 0
    };
    static const int pairs[16][4] = {
        {0, 0, 0, 0},
        {3, 0, 0, 0},
        {0, 1, 0, 0},
        {3, 1, 0, 0},
        {1, 2, 0, 0},
        {3, 2, 0, 1},
        {0, 2, 0, 0},
        {3, 2, 0, 0},
        {2, 3, 0, 0},
        {0, 2, 0, 0},
        {0, 3, 1, 2},
        {1, 2, 0, 0},
        {3, 1, 0, 0},
        {0, 1, 0, 0},
        {3, 0, 0, 0},
        {0, 0, 0, 0},
    };
    static const int edge_corners[4][2] = {
        {0, 1}, {1, 2}, {2, 3}, {3, 0}
    };
    double dx = (xmax - xmin) / (resolution - 1);
    double dy = (ymax - ymin) / (resolution - 1);
    segments->count = 0;

    for (int row = 0; row < resolution - 1; ++row) {
        double top = ymax - row * dy;
        double bottom = top - dy;
        for (int column = 0; column < resolution - 1; ++column) {
            double left = xmin + column * dx;
            double right = left + dx;
            size_t top_left = (size_t)row * resolution + column;
            size_t top_right = top_left + 1;
            size_t bottom_left = (size_t)(row + 1) * resolution + column;
            size_t bottom_right = bottom_left + 1;
            double samples[4] = {
                field[top_left],
                field[top_right],
                field[bottom_right],
                field[bottom_left],
            };
            if (!isfinite(samples[0]) || !isfinite(samples[1])
                || !isfinite(samples[2]) || !isfinite(samples[3])) {
                continue;
            }
            int contour_case = 0;
            for (int index = 0; index < 4; ++index) {
                if (samples[index] >= level) {
                    contour_case |= 1 << index;
                }
            }
            if (contour_case == 0 || contour_case == 15) {
                continue;
            }
            LoomComplex corners[4] = {
                {left, top},
                {right, top},
                {right, bottom},
                {left, bottom},
            };
            LoomComplex edge_points[4];
            int edge_ready[4] = {0, 0, 0, 0};
            for (int pair = 0; pair < pair_count[contour_case]; ++pair) {
                for (int side = 0; side < 2; ++side) {
                    int edge = pairs[contour_case][pair * 2 + side];
                    if (!edge_ready[edge]) {
                        int first = edge_corners[edge][0];
                        int second = edge_corners[edge][1];
                        edge_points[edge] = interpolate(
                            corners[first], corners[second],
                            samples[first], samples[second], level
                        );
                        edge_ready[edge] = 1;
                    }
                }
                int first_edge = pairs[contour_case][pair * 2];
                int second_edge = pairs[contour_case][pair * 2 + 1];
                if (!append_segment(
                        segments,
                        edge_points[first_edge],
                        edge_points[second_edge]
                    )) {
                    return 0;
                }
            }
        }
    }
    return 1;
}

static uint64_t hash_key(int64_t x, int64_t y) {
    uint64_t first = (uint64_t)x * UINT64_C(11400714819323198485);
    uint64_t second = (uint64_t)y * UINT64_C(14029467366897019727);
    uint64_t mixed = first ^ (second + UINT64_C(0x9e3779b97f4a7c15)
                              + (first << 6) + (first >> 2));
    mixed ^= mixed >> 30;
    mixed *= UINT64_C(0xbf58476d1ce4e5b9);
    mixed ^= mixed >> 27;
    mixed *= UINT64_C(0x94d049bb133111eb);
    return mixed ^ (mixed >> 31);
}

static size_t next_power_of_two(size_t value) {
    size_t result = 1;
    while (result < value && result <= SIZE_MAX / 2) {
        result *= 2;
    }
    return result;
}

static int node_append_edge(Node *node, size_t edge_index) {
    if (node->edge_count == node->edge_capacity) {
        size_t capacity = node->edge_capacity == 0 ? 4 : node->edge_capacity * 2;
        size_t *edges = realloc(node->edges, capacity * sizeof(*edges));
        if (edges == NULL) {
            return 0;
        }
        node->edges = edges;
        node->edge_capacity = capacity;
    }
    node->edges[node->edge_count++] = edge_index;
    return 1;
}

static int find_or_add_node(
    HashEntry *table,
    size_t table_size,
    Node **nodes,
    size_t *node_count,
    size_t *node_capacity,
    int64_t x,
    int64_t y,
    LoomComplex point,
    size_t *index_output
) {
    size_t mask = table_size - 1;
    size_t slot = (size_t)hash_key(x, y) & mask;
    while (table[slot].used) {
        if (table[slot].x == x && table[slot].y == y) {
            *index_output = table[slot].node_index;
            return 1;
        }
        slot = (slot + 1) & mask;
    }
    if (*node_count == *node_capacity) {
        size_t capacity = *node_capacity == 0 ? 256 : *node_capacity * 2;
        Node *resized = realloc(*nodes, capacity * sizeof(*resized));
        if (resized == NULL) {
            return 0;
        }
        *nodes = resized;
        *node_capacity = capacity;
    }
    size_t index = (*node_count)++;
    (*nodes)[index] = (Node){x, y, point, NULL, 0, 0};
    table[slot] = (HashEntry){1, x, y, index};
    *index_output = index;
    return 1;
}

static void free_nodes(Node *nodes, size_t node_count) {
    for (size_t index = 0; index < node_count; ++index) {
        free(nodes[index].edges);
    }
    free(nodes);
}

static int stitch_segments(
    const SegmentVector *segments,
    double tolerance,
    PointVector *points,
    PolylineVector *polylines
) {
    if (segments->count == 0) {
        return 1;
    }
    size_t table_size = next_power_of_two(segments->count * 4 + 1);
    if (table_size < 16) {
        table_size = 16;
    }
    HashEntry *table = calloc(table_size, sizeof(*table));
    Edge *edges = calloc(segments->count, sizeof(*edges));
    Node *nodes = NULL;
    size_t node_count = 0;
    size_t node_capacity = 0;
    if (table == NULL || edges == NULL) {
        free(table);
        free(edges);
        return 0;
    }

    for (size_t index = 0; index < segments->count; ++index) {
        LoomComplex endpoints[2] = {
            segments->items[index].first,
            segments->items[index].second,
        };
        size_t node_indices[2];
        for (int endpoint = 0; endpoint < 2; ++endpoint) {
            int64_t x = llround(endpoints[endpoint].real / tolerance);
            int64_t y = llround(endpoints[endpoint].imag / tolerance);
            if (!find_or_add_node(
                    table, table_size, &nodes, &node_count, &node_capacity,
                    x, y, endpoints[endpoint], &node_indices[endpoint]
                )) {
                free(table);
                free(edges);
                free_nodes(nodes, node_count);
                return 0;
            }
        }
        edges[index] = (Edge){node_indices[0], node_indices[1], 0};
        if (!node_append_edge(&nodes[node_indices[0]], index)
            || !node_append_edge(&nodes[node_indices[1]], index)) {
            free(table);
            free(edges);
            free_nodes(nodes, node_count);
            return 0;
        }
    }
    free(table);

    for (int endpoint_pass = 0; endpoint_pass < 2; ++endpoint_pass) {
        for (size_t start = 0; start < node_count; ++start) {
            int is_endpoint = nodes[start].edge_count == 1;
            if ((endpoint_pass == 0 && !is_endpoint)
                || (endpoint_pass == 1 && is_endpoint)) {
                continue;
            }
            for (size_t incident = 0;
                 incident < nodes[start].edge_count;
                 ++incident) {
                size_t edge_index = nodes[start].edges[incident];
                if (edges[edge_index].visited) {
                    continue;
                }
                size_t first_point = points->count;
                if (!append_point(points, nodes[start].point)) {
                    free(edges);
                    free_nodes(nodes, node_count);
                    return 0;
                }
                size_t current = start;
                while (1) {
                    size_t next_edge = SIZE_MAX;
                    for (size_t choice = 0;
                         choice < nodes[current].edge_count;
                         ++choice) {
                        size_t candidate = nodes[current].edges[choice];
                        if (!edges[candidate].visited) {
                            next_edge = candidate;
                            break;
                        }
                    }
                    if (next_edge == SIZE_MAX) {
                        break;
                    }
                    edges[next_edge].visited = 1;
                    size_t next = edges[next_edge].first == current
                        ? edges[next_edge].second
                        : edges[next_edge].first;
                    if (!append_point(points, nodes[next].point)) {
                        free(edges);
                        free_nodes(nodes, node_count);
                        return 0;
                    }
                    current = next;
                }
                size_t point_count = points->count - first_point;
                if (point_count >= 2
                    && !append_polyline(polylines, first_point, point_count)) {
                    free(edges);
                    free_nodes(nodes, node_count);
                    return 0;
                }
            }
        }
    }

    free(edges);
    free_nodes(nodes, node_count);
    return 1;
}

static int compare_doubles(const void *first, const void *second) {
    double a = *(const double *)first;
    double b = *(const double *)second;
    return (a > b) - (a < b);
}

static double median(const double *values, size_t count) {
    double *copy = malloc(count * sizeof(*copy));
    if (copy == NULL) {
        return NAN;
    }
    memcpy(copy, values, count * sizeof(*copy));
    qsort(copy, count, sizeof(*copy), compare_doubles);
    double result = count % 2
        ? copy[count / 2]
        : 0.5 * (copy[count / 2 - 1] + copy[count / 2]);
    free(copy);
    return result;
}

static int coordinate_field(
    double complex parameter,
    const LoomComplex *cycle_values,
    size_t cycle_count,
    double xmin,
    double xmax,
    double ymin,
    double ymax,
    int resolution,
    int max_returns,
    int degree,
    int antiholomorphic,
    double **field_output,
    int *return_period_output,
    int *kind_output,
    double *scale_output,
    double *minimum_output,
    double *maximum_output
) {
    size_t cell_count = (size_t)resolution * resolution;
    double complex *values = malloc(cell_count * sizeof(*values));
    double *field = malloc(cell_count * sizeof(*field));
    unsigned char *active = malloc(cell_count * sizeof(*active));
    double complex *cycle = malloc(cycle_count * sizeof(*cycle));
    double *multipliers = malloc(cycle_count * sizeof(*multipliers));
    double *coefficients = malloc(cycle_count * sizeof(*coefficients));
    if (values == NULL || field == NULL || active == NULL || cycle == NULL
        || multipliers == NULL || coefficients == NULL) {
        free(values);
        free(field);
        free(active);
        free(cycle);
        free(multipliers);
        free(coefficients);
        return 0;
    }
    for (size_t index = 0; index < cycle_count; ++index) {
        cycle[index] = to_complex(cycle_values[index]);
    }

    double dx = (xmax - xmin) / (resolution - 1);
    double dy = (ymax - ymin) / (resolution - 1);
    #pragma omp parallel for schedule(static)
    for (int row = 0; row < resolution; ++row) {
        double imag = ymax - row * dy;
        for (int column = 0; column < resolution; ++column) {
            size_t index = (size_t)row * resolution + column;
            values[index] = xmin + column * dx + I * imag;
            field[index] = NAN;
            active[index] = 1;
        }
    }

    int period = (int)cycle_count;
    int return_period = (
        !antiholomorphic || period % 2 == 0
        ? period
        : 2 * period
    );
    double complex forward = iterate_value(
        cycle[0] + 2e-6, parameter, return_period, degree, antiholomorphic
    );
    double complex backward = iterate_value(
        cycle[0] - 2e-6, parameter, return_period, degree, antiholomorphic
    );
    double approximate_multiplier = cabs((forward - backward) / 4e-6);
    int superattracting = approximate_multiplier < 1e-6;
    int local_degree = 1;
    if (superattracting) {
        local_degree = (!antiholomorphic || period % 2 == 0)
            ? degree
            : degree * degree;
    }

    for (size_t index = 0; index < cycle_count; ++index) {
        double complex anchor = cycle[index];
        if (local_degree == 1) {
            double step = 2e-6 * fmax(1.0, cabs(anchor));
            double complex plus = iterate_value(
                anchor + step, parameter, return_period,
                degree, antiholomorphic
            );
            double complex minus = iterate_value(
                anchor - step, parameter, return_period,
                degree, antiholomorphic
            );
            multipliers[index] = fmax(cabs((plus - minus) / (2.0 * step)), 1e-300);
            coefficients[index] = 1.0;
        } else {
            double step = local_degree == 2 ? 2e-4 : 8e-3;
            double complex base = iterate_value(
                anchor, parameter, return_period, degree, antiholomorphic
            );
            double complex nearby = iterate_value(
                anchor + step, parameter, return_period,
                degree, antiholomorphic
            );
            multipliers[index] = 0.0;
            coefficients[index] = fmax(
                cabs((nearby - base) / pow(step, local_degree)),
                1e-300
            );
        }
    }

    for (int return_index = 1; return_index <= max_returns; ++return_index) {
        int any_active = 0;
        #pragma omp parallel for reduction(|:any_active) schedule(static)
        for (size_t index = 0; index < cell_count; ++index) {
            if (!active[index]) {
                continue;
            }
            double complex value = values[index];
            for (int step = 0; step < return_period; ++step) {
                value = map_value(value, parameter, degree, antiholomorphic);
            }
            values[index] = value;
            if (cabs(value) > 1e8 || !isfinite(creal(value))
                || !isfinite(cimag(value))) {
                active[index] = 0;
                continue;
            }
            any_active = 1;
            if (isfinite(field[index])) {
                continue;
            }
            double nearest = INFINITY;
            size_t phase = 0;
            for (size_t anchor = 0; anchor < cycle_count; ++anchor) {
                double distance = cabs(value - cycle[anchor]);
                if (distance < nearest) {
                    nearest = distance;
                    phase = anchor;
                }
            }
            if (nearest >= 1e-6) {
                continue;
            }
            double safe_distance = fmax(nearest, 1e-300);
            if (superattracting) {
                field[index] = (
                    log(coefficients[phase]) + log(safe_distance)
                ) / pow((double)local_degree, return_index);
            } else {
                field[index] = log(safe_distance)
                    - return_index * log(multipliers[phase]);
            }
        }
        if (!any_active) {
            break;
        }
    }

    double minimum = INFINITY;
    double maximum = -INFINITY;
    for (size_t index = 0; index < cell_count; ++index) {
        if (isfinite(field[index])) {
            if (field[index] < minimum) {
                minimum = field[index];
            }
            if (field[index] > maximum) {
                maximum = field[index];
            }
        }
    }
    double scale = superattracting
        ? (double)local_degree
        : median(multipliers, cycle_count);

    free(values);
    free(active);
    free(cycle);
    free(multipliers);
    free(coefficients);
    if (!isfinite(scale)) {
        free(field);
        return 0;
    }
    *field_output = field;
    *return_period_output = return_period;
    *kind_output = superattracting ? 1 : 2;
    *scale_output = scale;
    *minimum_output = minimum;
    *maximum_output = maximum;
    return 1;
}

void loom_free_internal_curve_result(LoomInternalCurveResult *result) {
    if (result == NULL) {
        return;
    }
    free(result->curves);
    free(result->polylines);
    free(result->points);
    memset(result, 0, sizeof(*result));
}

int loom_trace_internal_grand_orbit(
    LoomComplex parameter_value,
    const LoomComplex *cycle,
    size_t cycle_count,
    double xmin,
    double xmax,
    double ymin,
    double ymax,
    double representative_log_radius,
    int generations,
    int resolution,
    int max_returns,
    int degree,
    int antiholomorphic,
    LoomInternalCurveResult *result
) {
    loom_set_error(NULL);
    if (result == NULL) {
        loom_set_error("An internal-curve result pointer is required.");
        return -1;
    }
    memset(result, 0, sizeof(*result));
    if (cycle == NULL || cycle_count == 0) {
        loom_set_error("No attracting cycle is available.");
        return -1;
    }
    if (generations < 0 || generations > 10) {
        loom_set_error("Generations must be between 0 and 10.");
        return -1;
    }
    if (resolution < 80 || resolution > 600) {
        loom_set_error("Resolution must be between 80 and 600.");
        return -1;
    }
    if (max_returns < 1 || !isfinite(representative_log_radius)) {
        loom_set_error("Internal-curve controls must be finite and positive.");
        return -1;
    }
    if (degree < 2 || degree > 32) {
        loom_set_error("Degree must be between 2 and 32.");
        return -1;
    }
    if (!(xmin < xmax && ymin < ymax)) {
        loom_set_error("Internal-curve bounds are invalid.");
        return -1;
    }

    double *field = NULL;
    int return_period = 0;
    int kind = 0;
    double scale = NAN;
    double minimum = INFINITY;
    double maximum = -INFINITY;
    if (!coordinate_field(
            to_complex(parameter_value), cycle, cycle_count,
            xmin, xmax, ymin, ymax, resolution, max_returns,
            degree, antiholomorphic, &field, &return_period, &kind,
            &scale, &minimum, &maximum
        )) {
        loom_set_error("Could not compute the internal-coordinate field.");
        return -1;
    }
    if (!isfinite(minimum) || !isfinite(maximum)) {
        free(field);
        loom_set_error(
            "The selected view did not resolve the attracting basin coordinate."
        );
        return 1;
    }

    int level_count = 2 * generations + 1;
    double levels[21];
    for (int index = -generations; index <= generations; ++index) {
        int output = index + generations;
        if (kind == 1) {
            levels[output] = representative_log_radius * pow(scale, index);
        } else {
            levels[output] = representative_log_radius + index * log(scale);
        }
    }
    qsort(levels, (size_t)level_count, sizeof(*levels), compare_doubles);

    SegmentVector segments = {0};
    PointVector points = {0};
    PolylineVector polylines = {0};
    CurveVector curves = {0};
    double dx = (xmax - xmin) / (resolution - 1);
    double dy = (ymax - ymin) / (resolution - 1);
    double stitch_tolerance = fmax(dx, dy) * 1e-5;

    for (int index = 0; index < level_count; ++index) {
        double level = levels[index];
        if (index > 0 && level == levels[index - 1]) {
            continue;
        }
        if (level < minimum || level > maximum) {
            continue;
        }
        if (!marching_segments(
                field, resolution, xmin, xmax, ymin, ymax,
                level, &segments
            )) {
            free(field);
            free(segments.items);
            free(points.items);
            free(polylines.items);
            free(curves.items);
            loom_set_error("Not enough memory for internal contour segments.");
            return -1;
        }
        size_t first_polyline = polylines.count;
        if (!stitch_segments(
                &segments, stitch_tolerance, &points, &polylines
            )) {
            free(field);
            free(segments.items);
            free(points.items);
            free(polylines.items);
            free(curves.items);
            loom_set_error("Not enough memory for stitched internal curves.");
            return -1;
        }
        size_t polyline_count = polylines.count - first_polyline;
        if (polyline_count > 0) {
            double absolute_tolerance = 1e-12;
            double relative_tolerance = 1e-12 * fabs(representative_log_radius);
            int representative = fabs(level - representative_log_radius)
                <= fmax(absolute_tolerance, relative_tolerance);
            if (!append_curve(
                    &curves, level, first_polyline,
                    polyline_count, representative
                )) {
                free(field);
                free(segments.items);
                free(points.items);
                free(polylines.items);
                free(curves.items);
                loom_set_error("Not enough memory for internal curves.");
                return -1;
            }
        }
    }
    free(field);
    free(segments.items);

    if (curves.count == 0) {
        free(points.items);
        free(polylines.items);
        free(curves.items);
        loom_set_error(
            "No requested coordinate levels crossed the resolved basin. "
            "Try a representative log-radius closer to zero."
        );
        return 1;
    }

    result->coordinate_kind = kind;
    result->return_period = return_period;
    result->curve_count = curves.count;
    result->polyline_count = polylines.count;
    result->point_count = points.count;
    result->curves = curves.items;
    result->polylines = polylines.items;
    result->points = points.items;
    return 0;
}
