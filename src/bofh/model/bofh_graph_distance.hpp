/**
 * @file bofh_model_distance.hpp
 * @brief Graph node node distance estimation
 */

#pragma once


#include "bofh_model_fwd.hpp"

namespace bofh {
namespace model {


/**
 * @brief calc pool distance (in terms of # of swaps) from current start_token
 *
 * All connected pools in the graph are tagged with the their respective
 * distance from the graph's start_token. (Basically applies an incremental
 * Djikstra search crossing al conntected nodes).
 *
 * Pools that exchange start_token get the minimum distance (0).
 * Disconnected pools have distance MAX_UINT.
 */
//void calc_pools_distance_on_pools(TheGraph *graph);
void calc_pools_distance_on_tokens(TheGraph *graph);


} // namespace model
} // namespace bofh

