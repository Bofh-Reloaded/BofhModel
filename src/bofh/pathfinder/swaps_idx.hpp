/**
 * @file swaps_idx.hpp
 * @brief Lookup index for swap opportunities
 */

#pragma once

#include "finder_3way.hpp"
#include <boost/functional/hash.hpp>
#include <map>

namespace bofh {
namespace pathfinder {
namespace idx {


struct SwapPathsIndex {

    const Path *add_path(const Path *p);

    // effective owenr of Path object pointers (stored here so that later they can be deleted)
    // TODO: use unique_ptr and correct RAII
    std::unordered_map<std::size_t, const Path*> path_idx;

    // in case anyone is baffled by what an unordered_multimap is,
    // this implements the case of one-to-many map: key -> multiple values.
    // It's an index of occurring token transitions among all known paths,
    // versus one or more path objects in which that transition occurs.
    std::unordered_multimap<const model::LiquidityPool *, const Path*> path_by_lp_idx;
};

} // namespace idx
} // namespace pathfinder
} // namespace bofh

