#pragma once

#include <bofh/model/bofh_model_fwd.hpp>
#include <functional>

namespace bofh {
namespace pathfinder {

using OperableSwap = model::OperableSwap;

/**
 * @brief Describes a 3-way swap path
 */
struct Path3Way: std::array<const OperableSwap*, 3>
{
    typedef std::array<const OperableSwap*, 3> base_t;

    /**
     * @brief callback type
     *
     * Algos that discover Path3Way objects don't simply add them to lists
     * to be passed arount.
     * They invoke a callback functor upon discovery of a valid path,
     * and whatever is at the other end gets the notification.
     *
     * This saves on memory and time.
     */
    typedef std::function<void(const Path3Way &)> listener_t;
};

/**
 * for the time being, this is the collection of path discovery algos that we implement
 */
struct Finder {
    // it needs access to the big graph object
    model::TheGraph *graph;

    // find all 3-way paths that start and end on start_node, and exit via a stable node
    void find_all_paths_3way_var(Path3Way::listener_t callback
                                 , const model::Token *start_node);
};

} // namespace pathfinder
} // namespace bofh

