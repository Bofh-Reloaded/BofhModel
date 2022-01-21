#pragma once

#include "paths.hpp"

namespace bofh {
namespace pathfinder {

/**
 * for the time being, this is the collection of path discovery algos that we implement
 */
struct Finder {
    // it needs access to the big graph object
    model::TheGraph *graph;

    // find all 3-way paths that start and end on start_node, and exit via a stable node
    void find_all_paths_3way_var_based_on_swaps(Path::listener_t callback
                                 , const model::Token *start_node);
    void find_all_paths_3way_var(Path::listener_t callback
                                 , const model::Token *start_node);
};

} // namespace pathfinder
} // namespace bofh

