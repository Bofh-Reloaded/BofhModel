#include "swaps_idx.hpp"
#include "../model/bofh_model.hpp"

namespace bofh {
namespace pathfinder {
namespace idx {


SwapPathsIndex::add_path_rt SwapPathsIndex::add_path(const Path *path)
{
    add_path_rt res;
    auto emp = path_idx.emplace(path->m_hash, path);
    res.added = emp.second;
    res.path = emp.first->second;
    return res;
}

bool SwapPathsIndex::has_paths_for(const model::LiquidityPool *lp)
{
    auto range = path_by_lp_idx.equal_range(lp);
    return range.first != range.second;
}

void SwapPathsIndex::connect_path_to_lp(const Path *p
                                        , const model::LiquidityPool *lp)
{
    path_by_lp_idx.emplace(lp, p);
}

void SwapPathsIndex::clear()
{
    for (auto p: path_idx)
    {
        assert(p.second != nullptr);
        delete p.second;
    }

    path_by_lp_idx.clear();
    path_idx.clear();
}

std::size_t SwapPathsIndex::paths_count()
{
    return path_idx.size();
}

std::size_t SwapPathsIndex::matrix_count()
{
    return path_by_lp_idx.size();
}

void SwapPathsIndex::get_paths_for_lp(PathList &out
                                      , const model::LiquidityPool *lp)
{
    auto range = path_by_lp_idx.equal_range(lp);
    for (auto i=range.first; i!=range.second; ++i)
    {
        out.emplace_back(i->second);
    }
}


} // namespace idx
} // namespace pathfinder
} // namespace bofh


