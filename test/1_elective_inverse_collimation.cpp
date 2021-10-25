
// THIS IS BROKEN. Do not use.
// The model has changed.
//

#include "test_utils.hpp"
#include <set>
#include <map>
#include <list>

using namespace bofh::model::test;
using namespace bofh::model;


static void djikstra(TheGraph::ref graph)
{
    constexpr auto base_token_name = "tok_0";
    constexpr auto initial_amount = 1000;

    // How many swaps try to include in the chain:
    // (not including the final comeback swap)
    constexpr auto min_swaps_count = 2;
    constexpr auto max_swaps_count = 5;

    assert(graph != nullptr);

    // initial token. We start with a balance of this, and aim to make a circular
    // path to go back here. In real world this would be USDC or some other
    // token used as out storage of value
    auto token = Token::make("tok_0");

    // This is its soulmate in the graph
    typedef TheGraph::Node::ref       node_ref; // TODO: work raw pointers:
    typedef TheGraph::Node::Edge::ref edge_ref; // shared_ptr slows things down

    typedef std::map<node_ref, edge_ref> swap_candidates_t;

    auto one_step_of_educated_guessing = [](auto &start_node
                                            , swap_candidates_t &candidate_swaps)
    {
        // find all possible swaps from the base token (start_node).
        // These are all candidates for the first node of the swap chain.
        // There can be multiple redundant swaps between two same tokens:
        // this selects only the most convenient one, discards all others.

        // Still no particular preference here, but a weighted preference
        // should be inferred from future imbalances spotted in the mempool.
        // *** Mempool is our primary clue beacon here.
        // *** Also mempool should be a source of convergence.
        // *** This search step should probably downrank swaps not likely
        // *** to be influenced by mempool or by inbound the tx gossiping.


        for (auto &edge: start_node->edges)
        {
            if (edge->landing == start_node) continue;

            auto item = candidate_swaps.find(edge->landing);
            if (item == candidate_swaps.end())
            {
                candidate_swaps.emplace(edge->landing, edge);
                continue;
            }

            // **** BROKEN ***
            // **** BROKEN *** This assumption is invalid.
            // **** BROKEN *** go back to drawing board.
            // **** BROKEN ***
            if (item->second->pair->rate > edge->pair->rate)
            {
                // we found a better deal to swap our token.
                // take note and carry on
                item->second = edge;
            }
        }
    };


    // step 0
    // we start with a base balance in the reference token.
    // Aim is to increase this balance by electing an hopefully optimal
    // circular walk of multiple swap.

    auto initial_balance = Balance::make(token, initial_amount);
    auto base_node = graph->node_for_token(token);
    assert(base_node != nullptr);
    std::list<swap_candidates_t> a_random_walk_down_defi;

    // step 1
    // find all possible swaps from the reference token
    // For all redundant swaps of every single token, select the one with the
    // best exchange rate.
    // In particular, this is a 1:1 set of destination tokens and exchange pairs.
    // This are all candidates for the first node of the swap chain.


    swap_candidates_t l1;
    one_step_of_educated_guessing(base_node, l1);
    a_random_walk_down_defi.emplace_back(std::move(l1));


    for (int swap_ctr = 0; swap_ctr < max_swaps_count; ++swap_ctr)
    {
        // step 2..n
        // collect all possible destination tokens, considering all the possibilities extracted at the at the previous step:
        // again, for each destination token, pick the swap with the most favorable exchange rate.
        // we end up with a set of possible swaps for the second node of the swap chain.
        // dimension(step[n+1]) should approach or slightly exceed that of dimension(step[n]).
        // Hint: the problem is walking O(m^n) paths, exponentnial on paper.
        // But each step has only about O(m) destinations (tokens), and *THIS IS KEY*
        // This caveat is what allows complexity to be linearly manageable.
        // In an actual implementation, moreover, said dimension is very reduced,
        // because anything that isn't being affected by mempool is downranked.
        // This, at least, is true while swap_ctr < min_swaps_count (...)

        swap_candidates_t swap_candidates;

        auto &previous_candidates = a_random_walk_down_defi.back();

        for (auto &i: previous_candidates)
        {
            one_step_of_educated_guessing(i.first, swap_candidates);
        }

        if (swap_ctr < min_swaps_count)
        {
            // we shouldn't consider ever paths that may accidentally
            // lead to the token we started from
            swap_candidates.erase(base_node);
        }
        else {
            // otherwise we start looking for a way out. Our aim is to
            // go back to the inital store of value, therefore I am
            // not removing it anymore from the swap candidates

            ; // do nothing
        }

        a_random_walk_down_defi.emplace_front(std::move(swap_candidates));
    }

    // at this point a_random_walk_down_defi is a nice list of
    // possible swaps, which can be used to describe a AT LEAST ONE possible
    // walk around the graph (but probably they in the order
    // of dimension(tokens)^max_swaps_count).
    // All swaps have been selected by ranking them across the same pair of
    // start and destination token.

    // and now we it comes the math piece

    typedef std::vector<edge_ref> path_candidate_t;
    typedef std::map<node_ref, Balance::ref> balances_t;

    balances_t balances;

    int i = -1;
    for (auto &swap_candidates: a_random_walk_down_defi)
    {
        ++i;

        if (i == 0)
        {
            // it's step 0 of the swap chain. we always start with our starting
            // balance. Let's try attempts to swap it, with every candidate pair
            for (auto &sc: swap_candidates)
            {
                assert(base_node->token == sc.second->pair->first);
                balances.emplace(sc.first, sc.second->pair->swap(initial_balance));
            }

            // we have populated "balances" with a nice map of tokens and
            // prospective new balances, one for each accessible token
            continue;
        }

        // typedef std::map<node_ref, edge_ref> swap_candidates_t;

        // for each swap candidate, attempt to locate a profitable swap.
        // It goes like this: at every swap we start with the hypotetical set of
        // balances, and end up with a new set of modified ones.
        // Those swaps that show improvements are elected into candidate chains.
        for (auto &sc: swap_candidates)
        {
            auto pre_balance_p = balances.find(sc.first);
            if (pre_balance_p == balances.end())
            {
                // TODO: IMPLEMENT ME
                continue;
            }
            auto &prev_balance = pre_balance_p->second;
            auto &required_token = sc.second->pair->first;

            auto new_balance = sc.second->pair->swap(prev_balance);

            balances.emplace(sc.first, sc.second->pair->swap(initial_balance));
        }
    }
}

int main()
{
    {
        auto graph = make_random_graph();
    }
    return 0;
}
