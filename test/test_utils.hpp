#pragma once

#include "finder_model.hpp"

namespace bofh {
namespace model {
namespace test {

constexpr int use_a_sensible_default = -1;

/**
 * @brief build a random graph of token and swap pairs between them
 *
 * The tokens will all have dummy names such as tok_0, tok_1 [...].
 *
 * The graph will know a number of swap pairs between the tokens,
 * each with its own exchange rate.
 * Swaps and reates will be picked randomly.
 *
 * @param how_many_known_tokens
 * @param how_many_possible_pair_swaps
 * @param random_pair_swap_rate_min
 * @param random_pair_swap_rate_max
 * @return the graph instance
 */
TheGraph::ref  make_random_graph(  int how_many_known_tokens        = use_a_sensible_default
                                 , int how_many_possible_pair_swaps = use_a_sensible_default
                                 , double random_pair_swap_rate_min = use_a_sensible_default
                                 , double random_pair_swap_rate_max = use_a_sensible_default);

}
}
};

