#include "finder_to_token.hpp"
#include "../commons/bofh_log.hpp"
#include <bofh/model/bofh_model.hpp>
#include <bofh/model/bofh_entity_idx.hpp>
#include <assert.h>
#include <algorithm>
#include <limits>
#include <vector>

namespace bofh {
namespace pathfinder {


void PathsToToken::operator()(Path::listener_t callback
                              , const model::Token *target_token
                              , unsigned max_length) const
{
    using namespace model;

    assert(callback);
    assert(target_token != nullptr);
    assert(m_graph != nullptr);
    assert(max_length <= MAX_PATHS);

    static constexpr auto distance_max = std::numeric_limits<unsigned>::max();

    auto start_token = m_graph->get_start_token();
    if (start_token == nullptr)
    {
        throw std::runtime_error("graph start_token is not set");
    }

    // allocate a path array large enough
    auto constexpr bunk_size = MAX_PATHS;
    std::array<const LiquidityPool *, bunk_size> candidate;
    // path [begin,end] pointers
    const LiquidityPool **path_begin;
    const LiquidityPool **path_end;

    // return current path length
    auto path_len = [&](){ return path_end-path_begin; };

    auto already_in_path = [&](auto lp)
    {
        for (auto i=path_begin; i!=path_end; ++i)
        {
            if (*i == lp) return true;
        }
        return false;
    };

    // print currently accrued path (debug purposes)
    auto print_current_path = [&]()
    {
        std::string txt;
        for (auto i=path_begin; i!=path_end; ++i)
        {
            if (!txt.empty()) txt += " - ";
            txt += strfmt("%1%(%2%-%3%)", (*i)->tag, (*i)->token0->symbol, (*i)->token1->symbol);
        }
        if (txt.empty()) txt += "empty";
        log_info("target_token=%3%(%4%) path[%1%] = %2%", path_len(), txt, target_token->tag, target_token->symbol);
    };

    // given the @p lp and one of its affering tokens, return the opposite one
    auto lp_out_token = [](const LiquidityPool *lp, const Token *in_token)
    {
        assert(lp->token0 == in_token || lp->token1 == in_token);
        return lp->token0 == in_token ? lp->token1 : lp->token0;
    };

    // given the specified @p token, return a set of best LP candidates
    // to perform swaps in order to reach start_token following the shortest path
    auto best_to_home = [&](const Token *token)
    {
        assert(token != start_token);
        const auto unconnected = std::numeric_limits<unsigned>::max();
        auto best_dist = unconnected;
        std::vector<const LiquidityPool *> res;
        bool converged;
        do {
            converged = true;
            for (auto lp: token->m_pools)
            {
                auto other = lp_out_token(lp, token);
                auto d = other->distance();

                if (d == unconnected)
                {
                    continue;
                }

                if (d < best_dist)
                {
                    best_dist = d;
                    converged = false;
                    res.clear();
                    break;
                }

                if (d == best_dist)
                {
                    res.emplace_back(lp);
                }
            }
        } while(! converged);

        return res;
    };

    // emit the generated path if the current one is valid
    auto emit_path = [&]()
    {
        const auto len = path_len();
        if (len <= MAX_PATHS)
        {
            try {
                auto candidate = new Path(Path::unconnected_path(), start_token, path_begin, len);
                callback(candidate);
            } catch (...) {
                log_error("failed path:");
                print_current_path();
            }
        }
    };

    std::function<bool(const Token *token)> extend_left = [&](const Token *token)
    {
        if (path_len() >= MAX_PATHS) return false;
        path_begin--;
        for (auto lp: best_to_home(token))
        {
            // do not backtrack
            if (already_in_path(lp)) continue;

            log_trace("add< len%8% tok %6%,%7% %1%(%2%,%3% - %4%,%5%)"
                     , lp->tag
                     , lp->token0->tag, lp->token0->symbol
                     , lp->token1->tag, lp->token1->symbol
                     , token->tag, token->symbol
                     , path_len());
            path_begin[0] = lp;
            auto other = lp_out_token(lp, token);
            if (other == start_token)
            {
                // found it
                return true;
            }
            else {
                if (extend_left(other)) return true;
            }
        }
        path_begin++;
        return false;
    };

    for (auto target_pool: best_to_home(target_token))
    {
        path_begin = &candidate[0] + candidate.size();
        path_end = path_begin;

        // add target_pool in the middle of the path array (this prepares it
        // to be populated on the left and/or right side)
        path_begin--;
        path_begin[0] = target_pool;
        log_trace("eval pool %1%(%2%,%3% - %4%,%5%)"
                 , target_pool->tag
                 , target_pool->token0->tag
                 , target_pool->token0->symbol
                 , target_pool->token1->tag
                 , target_pool->token1->symbol
                 );


        if (target_pool->token0 != start_token && target_pool->token1 != start_token)
        {
            // target_pool does not swap start_token
            // Extend leftmost path
            // of the path in order to reach start_token
            auto success = extend_left(
                        target_pool->token0->distance() < target_pool->token1->distance()
                        ? target_pool->token0
                        : target_pool->token1);
            if (!success)
            {
                continue;
            }
            emit_path();
        }
        else {
            emit_path();
        }
    }

}




} // namespace pathfinder
} // namespace bofh

