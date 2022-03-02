#include "swaps_idx.hpp"
#include "../model/bofh_model.hpp"

namespace bofh {
namespace pathfinder {
namespace idx {


const Path * SwapPathsIndex::add_path(const Path *path)
{
    path_idx.emplace(path->m_hash, path);
    for (unsigned int i = 0; i < path->size(); ++i)
    {
        path_by_lp_idx.emplace((*path)[i]->pool, path);
    }

    return path;
}

} // namespace idx
} // namespace pathfinder
} // namespace bofh


