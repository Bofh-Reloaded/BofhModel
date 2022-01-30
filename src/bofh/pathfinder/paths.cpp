#include "paths.hpp"
#include "../commons/bofh_log.hpp"
#include "../model/bofh_model.hpp"
#include <assert.h>

namespace bofh {
namespace pathfinder {

//double Path::estimate_profit_ratio() const
//{
//    // DEPRECATED: better implementation in TheGraph::debug_evaluate_known_paths
//    double ratio = 1.0f;
//    for (unsigned int i = 0; i < size(); ++i)
//    {
//        auto swap = get(i);
//        assert(swap != nullptr);
//        auto pool = swap->pool;
//        assert(pool != nullptr);
//        ratio *= pool->swapRatio(swap->tokenSrc);
//    }
//    return ratio;
//}

} // namespace pathfinder
} // namespace bofh


