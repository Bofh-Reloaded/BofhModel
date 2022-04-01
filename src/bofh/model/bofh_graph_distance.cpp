#include "bofh_graph_distance.hpp"
#include "bofh_model.hpp"
#include "bofh_entity_idx.hpp"
#include <set>
#include <vector>
#include <algorithm>
#include <limits>
#include <fstream>


namespace bofh {
namespace model {


///**
// * @brief calc pool distance (in terms of # of swaps) from current start_token
// *
// * All connected pools in the graph are tagged with the their respective
// * distance from the graph's start_token.
// *
// * Pools that exchange start_token get the minimum distance (0).
// * Disconnected pools have distance MAX_INT.
// */
//void calc_pools_distance_on_pools(TheGraph *graph)
//{
//    assert(graph != nullptr);
//    if (graph->m_start_token == nullptr)
//    {
//        throw std::runtime_error("start_token is not set");
//    }

//    constexpr auto normal_swap_distance_increment = 2;
//    constexpr auto stabletoken_swap_distance_increment = 1;


//    std::set<const Token *> visited_tokens;

//    auto set_distance = [](auto lp, unsigned distance)
//    {
//        const_cast<LiquidityPool*>(lp)->set_distance(std::min(distance, lp->distance()));
//    };

//    auto handle_not_visited = [&](auto token)
//    {
//        return visited_tokens.emplace(token).second;
//    };


//    // mark LPs unvisited
//    for (auto i = graph->entity_index->begin();
//         i != graph->entity_index->end();
//         ++i)
//    {
//        if ((*i)->type == EntityType_e::TYPE_LP)
//        {
//            auto pool = reinterpret_cast<LiquidityPool*>(*i);
//            pool->unset_distance();
//        }
//    }

//    // recursive lamba, must use std::function instead of auto
//    std::function<void(const Token *, unsigned)> visit_token
//            = [&](const Token *current_token
//            , unsigned current_distance)
//    {
//        if (handle_not_visited(current_token))
//        {
//            // mark all afferent pools with their now-known distance
//            for (auto lp: current_token->m_pools)
//            {
//                auto pool_distance =
//                        lp->token0->is_stable || lp->token1->is_stable
//                        ? current_distance+stabletoken_swap_distance_increment
//                        : current_distance+normal_swap_distance_increment;
//                set_distance(lp, pool_distance);
//            }
//            // visit all neighbouring nodes that still aren't visited
//            for (auto lp: current_token->m_pools)
//            {
//                auto other = current_token == lp->token0
//                        ? lp->token1
//                        : lp->token0;
//                visit_token(other, lp->distance());
//            }
//        }
//    };

//    visit_token(graph->m_start_token, 0);

////    std::ofstream fout;
////    fout.open("all_pools.txt");
////    fout << "id,distance,address" << std::endl;
////    for (auto i = graph->entity_index->begin();
////         i != graph->entity_index->end();
////         ++i)
////    {
////        if ((*i)->type == EntityType_e::TYPE_LP)
////        {
////            auto pool = reinterpret_cast<LiquidityPool*>(*i);
////            fout << pool->tag << "," << pool->distance() << "," << pool->address << std::endl;
////        }
////    }

////    for (auto i = graph->entity_index->begin();
////         i != graph->entity_index->end();
////         ++i)
////    {
////        if ((*i)->type == EntityType_e::TYPE_LP)
////        {
////            auto pool = reinterpret_cast<const LiquidityPool*>(*i);
////            //if (pool->distance == unknown_distance || pool->distance < 10) continue;

////            assert(pool != nullptr);
////            fout << "Trying to reach start_token " << graph->get_start_token()->symbol
////                 << " (" << graph->get_start_token()->address << "), starting from pool "
////                 << pool->address << ", which has distance " << pool->distance() << ":" << std::endl;
////            for (unsigned i = 0; i < 1000; ++i)
////            {
////                fout << " - " << pool->get_name() << " (dist=" << pool->distance() << ") on " << pool->exchange->name
////                     << " has id " << pool->tag << " and address " << pool->address
////                     << ", connects tokens "
////                     << pool->token0->symbol << " (" << pool->token0->address << ")"
////                     << " and "
////                     << pool->token1->symbol << " (" << pool->token1->address << ")"
////                     << std::endl;
////                if (pool->distance() == 1)
////                {
////                    fout << "we are at destination. good job. swaps performed = " << i << std::endl;
////                    break;
////                }
////                unsigned dist_min = unknown_distance;
////                const LiquidityPool *next_pool = nullptr;
////                for (auto lp: pool->token0->m_pools)
////                {
////                    if (lp->distance() < dist_min)
////                    {
////                        dist_min = lp->distance();
////                        next_pool = lp;
////                    }
////                }
////                for (auto lp: pool->token1->m_pools)
////                {
////                    if (lp->distance() < dist_min)
////                    {
////                        dist_min = lp->distance();
////                        next_pool = lp;
////                    }
////                }
////                if (next_pool == nullptr)
////                {
////                    fout << "unable to find next pool (BUG!!)" << std::endl;
////                    break;
////                }
////                pool = next_pool;
////            }

////        }
////    }
////    fout.close();
//}


void calc_pools_distance_on_tokens(TheGraph *graph)
{
    assert(graph != nullptr);
    if (graph->m_start_token == nullptr)
    {
        throw std::runtime_error("start_token is not set");
    }

    constexpr auto distance_increment = 1;

    std::set<const Token *> visited_tokens;

    auto set_distance = [](auto token, unsigned distance)
    {
        const_cast<Token*>(token)->set_distance(std::min(distance, token->distance()));
    };

    auto handle_not_visited = [&](auto token)
    {
        return visited_tokens.emplace(token).second;
    };

    auto other_token = [](auto tok, auto lp)
    {
        return lp->token0 == tok ? lp->token1 : lp->token0;
    };


    // mark Tokens as unvisited
    for (auto i = graph->entity_index->begin();
         i != graph->entity_index->end();
         ++i)
    {
        if ((*i)->type == EntityType_e::TYPE_TOKEN)
        {
            auto tok = reinterpret_cast<Token*>(*i);
            tok->unset_distance();
        }
    }

    // recursive lamba, must use std::function instead of auto
    std::function<void(const Token *, unsigned)> visit_token
            = [&](const Token *current_token
            , unsigned current_distance)
    {
        if (handle_not_visited(current_token))
        {
            auto next_distance = current_distance + distance_increment;

            // mark all neighbouring nodes with their now-known distance
            for (auto lp: current_token->m_pools)
            {
                auto otok = other_token(current_token, lp);
                set_distance(otok, next_distance);
            }

            // visit all neighbouring nodes
            for (auto lp: current_token->m_pools)
            {
                auto otok = other_token(current_token, lp);
                visit_token(otok, next_distance);
            }
        }
    };

    set_distance(graph->m_start_token, 0);
    visit_token(graph->m_start_token, 0);
}

} // namespace model
} // namespace bofh

