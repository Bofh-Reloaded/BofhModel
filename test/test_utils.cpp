#include "test_utils.hpp"

// for test code only:
#include <iostream>
#include <sstream>

namespace bofh {
namespace model {
namespace test {


TheGraph::ref  test_get_random_graph(  int how_many_known_tokens
                                     , int how_many_possible_pair_swaps
                                     , double random_pair_swap_rate_min
                                     , double random_pair_swap_rate_max)
{
    using namespace bofh::model;


    // let's build a sample graph of possible swap walks to experiment with.

    // here are some parameters to be used if the caller is lazy/has no clue:
    if (how_many_known_tokens == use_a_sensible_default)        how_many_known_tokens = 200;
    if (how_many_possible_pair_swaps == use_a_sensible_default) how_many_possible_pair_swaps = (how_many_known_tokens*how_many_known_tokens*5) / 3;
    if (random_pair_swap_rate_min == use_a_sensible_default)    random_pair_swap_rate_min = 0.01;
    if (random_pair_swap_rate_max == use_a_sensible_default)    random_pair_swap_rate_max = 10;

    // a bunch of dummy tokens with names such as tok_1, tok_2 ...
    std::vector<Token::ref> tokens;
    for (int i = 0; i < how_many_known_tokens; ++i)
    {
        std::ostringstream sstr;
        sstr << "tok_" << i;
        tokens.emplace_back(Token::make(sstr.str()));
    };

    // callable that returns a random swap pair of two tokens with random exchange rate
    auto random_pair = [&](){
        for (;;)
        {
            auto t1 = tokens[rand()%tokens.size()];
            auto t2 = tokens[rand()%tokens.size()];
            if (t1 == t2) continue;
            auto min = random_pair_swap_rate_min;
            auto max = random_pair_swap_rate_max;
            auto rate = (rand()/RAND_MAX) * (max - min) + min;
            return Pair::make(t1, t2, rate);
        }
    };


    auto graph = TheGraph::make();
    assert(graph != nullptr);
    // populate graph with random pairs
    for (int i = 0; i < how_many_possible_pair_swaps; ++i)
    {
        auto pair = random_pair();
        graph->add_pair(pair);
        graph->add_pair(pair->reciprocal());
    }

    return graph;
}



}
}
};
