#include "finder_all_crossing.hpp"
#include "../commons/bofh_log.hpp"
#include <bofh/model/bofh_model.hpp>
#include <bofh/model/bofh_entity_idx.hpp>
#include <assert.h>
#include <algorithm>
#include <limits>
#include <vector>

namespace bofh {
namespace pathfinder {


void AllPathsCrossingPool::operator()(Path::listener_t callback
                                      , const model::LiquidityPool *target_pool
                                      , unsigned max_length
                                      , unsigned max_count) const
{
    using namespace model;

    assert(callback);
    assert(target_pool != nullptr);
    assert(m_graph != nullptr);
    assert(max_length <= MAX_PATHS);

    static constexpr auto distance_max = std::numeric_limits<unsigned>::max();

    auto start_token = m_graph->get_start_token();
    if (start_token == nullptr)
    {
        throw std::runtime_error("graph start_token is not set");
    }

    log_info("find paths crossing %1% and circular against token %2%"
             , target_pool->tag, start_token->tag
             );

    // allocate a path array large enough to comfortably
    // fit 2x the maximum path length
    auto constexpr bunk_size = MAX_PATHS*2+1;
    std::array<const LiquidityPool *, bunk_size> candidate;
    // path [begin,end] pointers
    auto path_begin = &candidate[bunk_size/2];
    auto path_end = path_begin;
    unsigned count = 0;

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
            txt += strfmt("%1%(%2%,%3%-%4%)", (*i)->tag, *i, (*i)->token0, (*i)->token1);
        }
        if (txt.empty()) txt += "empty";
        log_info("path[%1%] = %2%", path_len(), txt);
    };

    // return rightmost added LP, if any
    auto get_rightmost = [&]() -> const LiquidityPool *
    {
        if (path_begin != path_end) return path_end[-1];
        return nullptr;
    };

    // return leftmost added LP, if any
    auto get_leftmost = [&]() -> const LiquidityPool *
    {
        if (path_begin != path_end) return path_begin[0];
        return nullptr;
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

    auto path_appears_circular = [&]() {
        auto a = path_begin[0];
        auto b = path_end[-1];
        return
                a->token0 == b->token0
                || a->token0 == b->token1
                || a->token1 == b->token0
                || a->token1 == b->token1;
    };

    // emit the generated path if the current one is valid
    auto emit_path = [&]()
    {
        const auto len = path_len();
        if (len >= MIN_PATHS && len <= MAX_PATHS && path_appears_circular())
        {
            auto candidate = new Path(start_token, path_begin, len);
            if(callback(candidate))
            {
                count++;
            }
//            if(callback(Path::reversed(candidate)))
//            {
//                count++;
//            }
        }
        else {
            log_info("unable to emit path (bad size):");
        }
    };

    std::function<void(const Token *token)> extend_right = [&](const Token *token)
    {
        if (count >= max_count) return;
        assert(token != start_token);
        if (path_len() >= max_length) return;
        path_end++;
        auto converge_immediately = path_len() == max_length;
        for (auto lp: token->m_pools)
        {
            if (already_in_path(lp))
            {
                // do not backtract on the last added path step
                continue;
            }
            path_end[-1] = lp;
            auto other = lp_out_token(lp, token);
            if (other == start_token)
            {
                // we landed back home
                emit_path();
                if (count >= max_count) return;
            }
            else if (!converge_immediately)
            {
                // not at home token.
                // we can try to extend the path more, on the right side
                // tag this token to be visited later.
                extend_right(other);
            }
        }
        path_end--;
    };

    std::function<bool(const Token *token)> extend_left = [&](const Token *token)
    {
        if (path_len() >= MAX_PATHS) return false;
        path_begin--;
        std::set<const Token *> revisit;
        for (auto lp: best_to_home(token))
        {
            // do not backtrack
            if (already_in_path(lp)) continue;

            path_begin[0] = lp;
            if (lp->token0 == start_token || lp->token1 == start_token)
            {
                // found it
                return true;
            }
            else {
                auto other = lp_out_token(lp, token);
                revisit.emplace(other);
            }
        }
        for (auto other: revisit)
        {
            if (extend_left(other)) return true;;
        }
        path_begin++;
        return false;
    };

    // add target_pool in the middle of the path array (this prepares it
    // to be populated on the left and/or right side)
    log_info("placing pool %1% in the path", target_pool->tag);
    path_end[0] = target_pool;
    path_end++;


    if (target_pool->token0 != start_token && target_pool->token1 != start_token)
    {
        // target_pool does not swap start_token. This means that it will
        // NOT traversed first or last in the path sequence. Extend leftmost path
        // of the path in order to reach start_token
        log_info("target_pool %1% does not swap token %2% directly",
                 target_pool->tag, start_token->tag);
        log_info("trying to reach start_token by extending leftmost side of the path");
        auto success = extend_left(
                    target_pool->token0->distance() < target_pool->token1->distance()
                    ? target_pool->token0
                    : target_pool->token1);
        if (!success)
        {
            log_warning("pool %1% unable to reach start_token %2%"
                        , target_pool->tag
                        , start_token->tag);
            return;
        }
    }
    else {
        log_info("target_pool directly exchanges against start_token");
    }

    const Token *continuation_token = nullptr;
    if (path_len() > 1)
    {
        auto tlast = path_end[-1];
        auto tprev = path_end[-2];
        continuation_token =
                tprev->token0 == tlast->token0 || tprev->token1 == tlast->token0
                ? tlast->token1
                : tlast->token0;
    }
    else
    {
        continuation_token = lp_out_token(target_pool, start_token);
    }
    assert(continuation_token != nullptr);
    log_info("extending current path on the rightmost side, using token %1% (%2%)",
             continuation_token->tag, continuation_token->symbol);
    extend_right(continuation_token);
}




} // namespace pathfinder
} // namespace bofh

