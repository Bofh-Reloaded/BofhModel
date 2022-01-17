#include "finder_3way.hpp"
#include <bofh/model/bofh_model.hpp>
#include <bofh/model/bofh_entity_idx.hpp>
#include <assert.h>

namespace bofh {
namespace pathfinder {





namespace {

auto WBNB_address = "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c";

using namespace model;

template<typename Iter>
struct iterpair_range
{
    std::pair<Iter, Iter> m_range;
    iterpair_range(const std::pair<Iter, Iter> &r) : m_range(r) {}

    Iter& begin() noexcept { return m_range.first; }
    const Iter& begin() const noexcept { return m_range.first; }
    Iter& end() noexcept { return m_range.second; }
    const Iter& end() const noexcept { return m_range.second; }
};

/**
 *  turns the weird iterator-pair returned my a multiindex.equal_range()
 *  into something that C++11 implicitly knows how to iterate upon
 */
static auto iterable_please = [](auto iterpair){
    return iterpair_range<decltype(iterpair.first)>(iterpair);
};


};



void Finder::find_all_paths_3way_var(Path3Way::listener_t callback
                                     , const model::Token *start_node)
{
    using namespace model;
    using namespace std;

    assert(start_node != nullptr);

    // orig code:
    //      usable_nodes = (set(stable_list) & (predecessorslist)) #filter blue arrows on stable nodes
    // means:
    //      list of nodes which are stable tokens AND for which a swap exists, that lands on start_node
    // can be also seen as:
    //      list of swaps that have tokenDest == start_node AND tokenSrc IN (stable_list)
    // implemented as:
    //      there is a dedicated index that does exactly this, it's called idx::stable_predecessors;
    //      it just needs to be queried with (stable_tokens=true, tokenDest=start_node)
    // notes:
    //      the query extracts a range of OperableSwaps, not Tokens. Here we work in terms of swaps

    auto usable_swaps = graph
            ->swap_index
            ->get<idx::stable_predecessors>()
            .equal_range(boost::make_tuple(true, start_node));

    for (auto stable_swap: iterable_please(usable_swaps))
    {
        auto stable_node = stable_swap->tokenSrc;

        // orig code:
        //      tc_nodes = set(graph.predecessors(stable_node)) & set(successorslist)
        // means:
        //      list of nodes for which a swap exists that lands on stable_node and
        //      at the same time, another swap exists that starts from start_token
        // can also be seen as:
        //      let's find a subset of swap couples that have a tc_node in the middle, AND
        //      start from start_node AND terminate on stable_node
        // implemented as:
        //      swaps0 = all swaps where tokenSrc = start_node
        //      swaps1 = all swaps where tokenDest = stable_node
        //      foreach tc_node in select all couple where swap0.tokenDest = swap1.tokenSrc:
        //          do_stuff()
        auto swaps0 = graph
                ->swap_index
                ->get<idx::by_src_token>()
                .equal_range(start_node);
        auto swaps1 = graph
                ->swap_index
                ->get<idx::by_dest_token>()
                .equal_range(stable_node);

        for (auto swap0: iterable_please(swaps0))
        for (auto swap1: iterable_please(swaps1))
        if (swap0->tokenDest == swap1->tokenSrc)
        {
            auto tc_node = swap0->tokenDest;

            // orig code:
            //      for tc_node in tc_nodes:
            //          path = [start_node, tc_node, stable_node, start_node]
            //          path_list.append(path)
            // means:
            //      compound a list of swap paths with new entries. Each entry consisting of
            //      a token walking sequence: start_node, tc_node, stable_node, start_node
            // can also be seen as:
            //      compound a list of swap paths with new entries. Each entry consisting of
            //      an order list of swaps, of length 3, for which swap[0].tokenSrc == swap[2].tokenDest == start_node
            // implemented as:
            //      compounding a list of Path3Way tuples
            assert(swap0->tokenSrc == start_node);
            assert(swap0->tokenDest == tc_node);

            assert(swap1->tokenSrc == tc_node);
            assert(swap1->tokenDest == stable_node);

            auto swap2 = stable_swap;
            assert(swap2->tokenSrc == stable_node);
            assert(swap2->tokenDest == start_node);

            // send the new entry to whoever requested it
            callback(Path3Way{swap0, swap1, swap2});
        }
    }
}

} // namespace pathfinder
} // namespace bofh

