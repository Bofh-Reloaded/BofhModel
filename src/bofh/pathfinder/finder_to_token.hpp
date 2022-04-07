#pragma once

#include "paths.hpp"

namespace bofh {
namespace pathfinder {

/**
 * Find all paths that cross a specific pool
 */
struct PathsToToken
{
    PathsToToken(const model::TheGraph *graph): m_graph(graph) {}

    void operator()(Path::listener_t callback
                    , const model::Token *token
                    , unsigned max_length
                    ) const;

    const model::TheGraph *m_graph;
};

} // namespace pathfinder
} // namespace bofh

