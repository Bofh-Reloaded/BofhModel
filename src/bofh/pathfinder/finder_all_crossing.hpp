#pragma once

#include "paths.hpp"

namespace bofh {
namespace pathfinder {

/**
 * Find all paths that cross a specific pool
 */
struct AllPathsCrossingPool
{
    AllPathsCrossingPool(const model::TheGraph *graph): m_graph(graph) {}

    void operator()(Path::listener_t callback
                    , const model::LiquidityPool *pool
                    , unsigned max_length
                    , unsigned max_count) const;

    const model::TheGraph *m_graph;
};

} // namespace pathfinder
} // namespace bofh

