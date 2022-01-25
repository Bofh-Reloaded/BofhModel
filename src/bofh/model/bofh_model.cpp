#include "bofh_model.hpp"
#include "../commons/bofh_log.hpp"
#include "bofh_entity_idx.hpp"
#include "../pathfinder/swaps_idx.hpp"
#include "../pathfinder/finder_3way.hpp"
#include <sstream>
#include <exception>


namespace bofh {
namespace model {

using namespace idx;
using namespace pathfinder::idx;

struct bad_argument: public std::runtime_error
{
    using std::runtime_error::runtime_error ;
};
#define check_not_null_arg(name) if (name == nullptr) throw bad_argument("can't be null: " #name);



void LiquidityPool::setReserve(const Token *token, const balance_t &reserve)
{
    assert(token == token1 || token == token0);
    if (token == token0)
    {
        reserve0 = reserve;
        freserve0 = reserve.convert_to<double>();
    }
    else if (token == token1)
    {
        reserve1 = reserve;
        freserve1 = reserve.convert_to<double>();
    }
    k = reserve0 * reserve1;
    fk = k.convert_to<double>();
}

const balance_t &LiquidityPool::getReserve(const Token *token)
{
    assert(token == token1 || token == token0);
    return token == token0 ? reserve0 : reserve1;
}

void LiquidityPool::setReserves(const balance_t &reserve0_, const balance_t &reserve1_)
{
    reserve0 = reserve0_;
    reserve1 = reserve1_;
    k = reserve0 * reserve1;
    fk = k.convert_to<double>();
    freserve0 = reserve0.convert_to<double>();
    freserve1 = reserve1.convert_to<double>();
}

balance_t LiquidityPool::simpleSwap(const Token *tokenIn, const balance_t &amountIn, bool updateReserves)
{
    assert(tokenIn == token1 || tokenIn == token0);

    // Let's simulate how an Uniswap's AMM compliant LP would behave. Let's take
    // for example an hypotetical ETH/LTC pool.
    //
    // Such pool has: reserveETH=100 and reserveLTC=200, making LTC more abundant than ETH
    // The k value of the pool is reserveETH*reserveLTC = 100*200 = 20000

    // A consumer comes and wants to swap balanceIn=45 of LTC into a ETH using this pool.
    // Respective of the pool's reserves, such operation would entail:
    // - adding LTC to the pool (in) --> reserveLTC+=amountIn
    // - subtracting ETH from the pool (out) --> reserveETH-=amountOut

    // As per Uniswap's AMM specifications, here is what is set in stone for the operation:
    // - by contract constraint, the pool must maintain k=200000 after the swap
    // - the pool will have reserveLTC+balanceIn = 200+45 = 245 LTC in its reserves
    // - a number of ETH must be calculated to substract in order to maintain k constant
    // - since k=reserveETH*reserveLTC=20000 --->
    //     k=(reserveETH-amountOut)*(reserveLTC+amountIn) --->
    //     reserveETH-amountOut = k / (reserveLTC+amountIn) --->
    // (written in a form compatible with uints) -->
    //     amountOut = reserveETH - (k / (reserveLTC+amountIn))

    balance_t reserveIn  = tokenIn == token0 ? reserve0 : reserve1;
    balance_t reserveOut = tokenIn == token0 ? reserve1 : reserve0;

    balance_t newReserveIn = reserveIn+amountIn;
    balance_t amountOutIdeal = reserveOut - k / newReserveIn;
    balance_t amountOutWithFees(amountOutIdeal.convert_to<double>() * (1.0f-fees()));

    if (updateReserves)
    {
        (tokenIn == token0 ? reserve0 : reserve1) = newReserveIn;
        (tokenIn == token0 ? reserve1 : reserve0) = reserveOut - amountOutWithFees;
        k = reserve0 * reserve1;
        fk = k.convert_to<double>();
        freserve0 = reserve0.convert_to<double>();
        freserve1 = reserve1.convert_to<double>();
    }

    return amountOutWithFees;
}

double LiquidityPool::simpleSwapF(const Token *tokenIn, double amountIn) const noexcept
{
    assert(tokenIn == token1 || tokenIn == token0);

    double reserveOut = tokenIn == token0 ? freserve0 : freserve1;
    double reserveIn  = tokenIn == token0 ? freserve1 : freserve0;

    return (reserveOut - (fk / (reserveIn+amountIn))) * (1.0f - fees());
}

double LiquidityPool::swapRatio(const Token *tokenIn) const noexcept
{
    return simpleSwapF(tokenIn, 1.0f);
}

double LiquidityPool::estimateSwapStress(const Token *tokenIn, const balance_t &amountInB) const
{
    assert(tokenIn == token1 || tokenIn == token0);

    double reserveOut = tokenIn == token0 ? freserve0 : freserve1;
    double reserveIn  = tokenIn == token0 ? freserve1 : freserve0;
    double amountIn = amountInB.convert_to<double>();

    // assumption:
    //     fk = (reserveIn+amountIn) * (reserveOut-amountOut);
    //
    // need to compute:
    //     inbalanceOut = amountOut / reserveOut (amountOut not known yet)
    //
    // rewriting the equation as:
    //     inbalanceOut =
    //         amountOut / reserveOut =
    //             (reserveOut - (k / (reserveIn+amountIn))) / reserveOut
    //
    // perk:
    //     amountOut isn't explicitly needed anymore

    double inbalanceIn = amountIn/reserveIn;
    double inbalanceOut = (reserveOut - (fk / (reserveIn+amountIn))) / reserveOut;

    // in LPs that are reasonably financed, inbalanceIn should be
    // roughly equal to inbalanceOut, but they tend to deviate sharply as
    // LP reserves run low. As a security measure, we calculate both and return
    // the worst one.

    return std::max(inbalanceIn, inbalanceOut);
}


TheGraph::TheGraph()
    : entity_index(new EntityIndex)
    , swap_index(new SwapIndex)
    , paths_index(new SwapPathsIndex)
{
    log_trace("TheGraph created at 0x%p", this);
};

namespace {
// FIY: an unnamed namespace makes its content private to this code unit

/**
 * Use this to check the outcome of any cointainer emplace()
 * @return true if the emplace() was rejected and an existing
 *         duplicate was found in the container
 */
auto already_exists = [](const auto &i) { return !i.second; };

}; // unnamed namespace


const Exchange *TheGraph::add_exchange(datatag_t tag
                                       , const char *address
                                       , const string &name
                                       )
{
    auto ptr = std::make_unique<Exchange>(tag, address, name);
    auto item = entity_index->emplace(ptr.get());
    if (already_exists(item))
    {
        return nullptr;
    }
    return reinterpret_cast<Exchange*>(ptr.release());
}


const Exchange *TheGraph::lookup_exchange(datatag_t tag)
{
    return entity_index->lookup<Exchange, TYPE_EXCHANGE>(tag);
}


const Token *TheGraph::add_token(datatag_t tag
                                 , const char *address
                                 , const char *name
                                 , const char *symbol
                                 , unsigned int decimals
                                 , bool is_stablecoin)
{
    auto ptr = std::make_unique<Token>(tag
                                       , address
                                       , name
                                       , symbol
                                       , decimals
                                       , is_stablecoin);
    auto item = entity_index->emplace(ptr.get());
    if (already_exists(item))
    {
        return nullptr;
    }
    return reinterpret_cast<Token*>(ptr.release());
}


const Token *TheGraph::lookup_token(const char *address)
{
    return entity_index->lookup<Token, TYPE_TOKEN>(address);
}


const Token *TheGraph::lookup_token(datatag_t tag)
{
    return entity_index->lookup<Token, TYPE_TOKEN>(tag);
}


const LiquidityPool *TheGraph::add_lp(datatag_t tag
                                      , const char *address
                                      , const Exchange* exchange
                                      , Token* token0
                                      , Token* token1)
{
    check_not_null_arg(exchange);
    check_not_null_arg(token0);
    check_not_null_arg(token1);
    auto ptr = std::make_unique<LiquidityPool>(tag
                                               , address
                                               , exchange
                                               , token0
                                               , token1);
    auto item = entity_index->emplace(ptr.get());
    if (already_exists(item))
    {
        return nullptr;
    }

    auto lp = reinterpret_cast<LiquidityPool*>(ptr.release());

    // create OperableSwap objects
    swap_index->emplace(OperableSwap::make(token0, token1, lp));
    swap_index->emplace(OperableSwap::make(token1, token0, lp));

    return lp;
}

const LiquidityPool *TheGraph::lookup_lp(const address_t &address)
{
    return entity_index->lookup<LiquidityPool, TYPE_LP>(address);
}

std::vector<const OperableSwap *> TheGraph::lookup_swap(datatag_t token0, datatag_t token1)
{
    std::vector<const OperableSwap *> res;
    auto t0 = lookup_token(token0);
    auto t1 = lookup_token(token1);

    if (t0 == nullptr)
    {
        log_error("token0 id %1% not found", token0);
        return res;
    }
    if (t1 == nullptr)
    {
        log_error("token1 id %1% not found", token1);
        return res;
    }

    auto range = swap_index->get<idx::by_src_and_dest_token>().equal_range(boost::make_tuple(t0, t1));
    for (auto i = range.first; i != range.second; ++i)
    {
        res.push_back(*i);
    }

    return res;
}



const LiquidityPool *TheGraph::lookup_lp(datatag_t tag)
{
    return entity_index->lookup<LiquidityPool, TYPE_LP>(tag);
}

static auto clear_existing_paths_if_any = [](TheGraph *graph)
{
    assert(graph);
    assert(graph->paths_index);

    for (auto p: graph->paths_index->holder)
    {
        assert(p != nullptr);
        delete p;
    }

    graph->paths_index->paths.clear();
    graph->paths_index->holder.clear();
};

void TheGraph::calculate_paths()
{
    using Path = pathfinder::Path;

    clear_existing_paths_if_any(this);

    pathfinder::Finder f{this};

    if (start_token == nullptr)
    {
        log_error("calculate_paths(): start_token not set");
        return;
    }

    log_info("calculate_paths() considering start_token %s at %p"
             , start_token->symbol.c_str()
             , start_token);

    auto listener = [&](const Path *path)
    {
        paths_index->holder.emplace_back(path);
        // TODO: fix theoretical memleak in case of emplace() exception

        log_trace("found path: [%1%, %2%, %3%, %4%]"
                  , (*path)[0]->tokenSrc->tag
                  , (*path)[1]->tokenSrc->tag
                  , (*path)[2]->tokenSrc->tag
                  , (*path)[2]->tokenDest->tag);

        for (unsigned int i = 0; i < path->size(); ++i)
        {
            auto key = TokenTransition(
                          (*path)[i]->tokenSrc
                        , (*path)[i]->tokenDest);
            paths_index->paths.emplace(key, path);
        }
    };

    f.find_all_paths_3way_var(listener, start_token);
    log_info("computed: %u paths, %u entries in hot swaps index"
             , paths_index->holder.size()
             , paths_index->paths.size());
}

void TheGraph::debug_evaluate_known_paths(const PathEvalutionConstraints &c)
{
    struct ConstraintViolation {};
    struct LimitReached {};

    log_debug("evaluate_known_paths() seach of swap opportunities starting");
    log_debug(" \\__ start_token is %1% (%2%)", start_token->symbol, start_token->address);
    if (c.initial_token_wei_balance > 0)
    {
        log_debug(" \\__ initial_token_wei_balance is %1% (%2% Weis)"
                  , start_token->fromWei(c.initial_token_wei_balance)
                  , c.initial_token_wei_balance);
    }
    else {
        log_debug(" \\__ no balance provided. Please set "
                  "initial_token_wei_balance to a meaningful Wei amount of start_token (%1%)"
                  , start_token->symbol);
        return;
    }
    if (c.max_lp_reserves_stress > 0)
    {
        log_debug(" \\__ max_lp_reserves_stress set at %1%", c.max_lp_reserves_stress);
    }
    if (c.convenience_min_threshold >= 0)
    {
        log_debug(" \\__ ignore yields < convenience_min_threshold (%1%)", c.convenience_min_threshold);
    }
    if (c.convenience_max_threshold >= 0)
    {
        log_debug(" \\__ ignore yields > convenience_max_threshold (%1%)", c.convenience_max_threshold);
    }
    if (c.match_limit)
    {
        log_debug(" \\__ match limit is set at %1%", c.match_limit);
    }
    if (c.limit)
    {
        log_debug(" \\__ loop limit is set at %1%", c.limit);
    }


    unsigned int ctr = 0;
    unsigned int matches = 0;
    for (auto path: paths_index->holder) try
    {
        // @note: loop body is a try block

        ctr++;
        if (c.limit > 0 && ctr >= c.limit)
        {
            log_trace("loop limit reached (%1%)"
                      , c.limit);
            throw LimitReached();
        }


        balance_t    balance = c.initial_token_wei_balance;
        const Token *token   = start_token;

        // local functor: returns a string representation of the steps involved
        // in the currently examined swap.  Only used for logging.
        // returns a string
        auto log_path_nodes = [&](bool include_addesses=false, bool include_tags=true) {
            std::stringstream ss;
            for (auto i = 0; i < path->size(); ++i)
            {
                auto swap = path->get(i);
                if (i > 0) ss << ",";
                ss << " " << swap->pool->exchange->name
                   << "(" << swap->tokenSrc->symbol
                   << "-" << swap->tokenDest->symbol;
                if (include_tags) ss << ", " << swap->pool->tag;
                if (include_addesses) ss << ", " << swap->pool->address;
                ss << ")";
            }
            return ss.str();
        };

        log_trace("evaluating path %1%", log_path_nodes(true));

        // walk the swap path:
        for (unsigned int i = 0; i < path->size(); ++i)
        {
            // excuse the following assert soup. They are only intended to
            // early catch of inconsistencies in debug builds. None is functional.
            auto swap = path->get(i);
            assert(swap != nullptr);
            auto pool = swap->pool;
            assert(pool != nullptr);

            assert(token == swap->tokenSrc);
            assert(token == pool->token0 || token == pool->token1);

            log_trace(" \\__ current token is %1%", token->symbol);

            log_trace(" \\__ current balance is %1% (%2% Weis)"
                      , token->fromWei(balance)
                      , balance);
            if (c.max_lp_reserves_stress > 0)
            {
                auto stress = pool->estimateSwapStress(token, balance);
                log_trace(" \\__ swap attempt would induce a %0.03f%% "
                          "reserves stress on the pool"
                          , (stress * 100.0));
                if (stress > c.max_lp_reserves_stress)
                {
                    log_trace(" \\__ swap stress would induce excessive "
                              "reserves unbalance on the pool (path skipped)");
                    throw ConstraintViolation();
                }
            }
            auto ncpool = const_cast<LiquidityPool*>(pool);
            balance = ncpool->simpleSwap(token, balance);
            token = swap->tokenDest;
            assert(token != nullptr);
            log_trace(" \\__ after the swap, the new balance would be %1% %2% (%3% Weis)"
                      , token->fromWei(balance)
                      , token->symbol
                      , balance);


        }
        if (token != start_token)
        {
            log_error("BROKEN SWAP: it's not circular. start_token is %1%,"
                      " terminal token is %2%"
                      , start_token->symbol
                      , token->symbol);

            throw ConstraintViolation();
        }


        double yieldRatio = balance.convert_to<double>() - c.initial_token_wei_balance.convert_to<double>();
        log_trace(" \\__ after the final swap yield would be %0.5f%%"
                  , yieldRatio*100.0);
        if (balance > c.initial_token_wei_balance)
        {
            auto gap = balance - c.initial_token_wei_balance;
            log_trace(" \\__ the operation gains %0.5f %s"
                      , token->fromWei(gap)
                      , token->symbol.c_str());
            log_trace("         \\__ or +%1% %2% Weis :)"
                      , gap
                      , token->symbol);
        }
        else {
            auto gap = c.initial_token_wei_balance - balance;
            log_trace(" \\__ the operation loses %0.5f %s"
                      , token->fromWei(gap)
                      , token->symbol.c_str());
            log_trace("         \\__ or -%1% %2% Weis :("
                      , gap
                      , token->symbol);
        }
        if (c.convenience_min_threshold >= 0 && yieldRatio < c.convenience_min_threshold)
        {
            log_trace(" \\__ final yield is under the set convenience_min_threshold (path skipped)");
            throw ConstraintViolation();
        }

        if (c.convenience_max_threshold >= 0 && yieldRatio > c.convenience_max_threshold)
        {
            log_trace(" \\__ final yield is under the set convenience_min_threshold (path skipped)");
            throw ConstraintViolation();
        }

        assert(token == start_token);

        auto print_swap_candidate = [&]() {
            log_info("mathing path %s would yield %0.5f%%"
                     , log_path_nodes().c_str()
                     , yieldRatio*100);
            if (c.initial_token_wei_balance != 0)
            {
                log_info(" \\__ initial balance of %1% %2% (%3% Weis) "
                         "turned in %4% %5% (%6% Weis)"
                         , start_token->fromWei(c.initial_token_wei_balance)
                         , start_token->symbol
                         , c.initial_token_wei_balance
                         , token->fromWei(balance)
                         , token->symbol
                         , balance
                         );
            }
        };


        matches++;
        print_swap_candidate();

        if (c.match_limit > 0 && matches >= c.match_limit)
        {
            log_trace("match limit reached (%1%)"
                      , c.match_limit);
            throw LimitReached();
        }

    }
    catch (ConstraintViolation&) { continue; }
    catch (LimitReached &) { break; }

}



} // namespace model
} // namespace bofh
