/**
 * @file bofh_model_paths.hpp
 * @brief Path discovery algirithms
 */

#pragma once


#include "bofh_model_fwd.hpp"
#include "../pathfinder/paths.hpp"

namespace bofh {
namespace model {

pathfinder::PathList calc_paths_crossing(TheGraph *graph
                                         , const LiquidityPool *pool);


} // namespace model
} // namespace bofh

