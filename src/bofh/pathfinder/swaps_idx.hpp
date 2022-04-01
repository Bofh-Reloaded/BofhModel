/**
 * @file swaps_idx.hpp
 * @brief Lookup index for swap opportunities
 */

#pragma once

#include "paths.hpp"
#include <boost/functional/hash.hpp>
#include <map>

namespace bofh {
namespace pathfinder {
namespace idx {


struct SwapPathsIndex {
    typedef struct {
        bool added;
        const Path *path;
    } add_path_rt;

    add_path_rt add_path(const Path *p);
    bool has_paths_for(const model::LiquidityPool *lp);
    void connect_path_to_lp(const Path *p, const model::LiquidityPool *lp);
    void clear();
    std::size_t paths_count();
    std::size_t matrix_count();
    void get_paths_for_lp(PathList &out, const model::LiquidityPool *lp);

//private:
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

