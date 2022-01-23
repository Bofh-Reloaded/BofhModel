#include "bofh_model.hpp"
#include "bofh_entity_idx.hpp"
#include "../pathfinder/swaps_idx.hpp"
#include "../pathfinder/finder_3way.hpp"
#include "../commons/bofh_log.hpp"
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
    }

    return amountOutWithFees;
}

double LiquidityPool::swapRatio(const Token *tokenIn) const noexcept
{
    assert(tokenIn == token1 || tokenIn == token0);

    double reserveOut = tokenIn == token0 ? freserve0 : freserve1;
    double reserveIn  = tokenIn == token0 ? freserve1 : freserve0;

    return (reserveOut - (fk / (reserveIn+1.0))) * (1.0f - fees());
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

        log_debug("found path: [%1%, %2%, %3%, %4%]"
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

void TheGraph::debug_evaluate_known_paths(double convenience_min_threshold
                                          , double convenience_max_threshold
                                          , unsigned int limit)
{
    unsigned int ctr = 0;
    for (auto path: paths_index->holder)
    {
        auto ratio = path->estimate_profit_ratio();
        if (convenience_min_threshold >= 0 && ratio < convenience_min_threshold) continue;
        if (convenience_max_threshold >= 0 && ratio > convenience_max_threshold) continue;
        if (limit > 0 && ctr > limit) return;
        std::stringstream ss;
        ss << "known path ";
        for (auto i = 0; i < path->size(); ++i)
        {
            auto swap = path->get(i);
            if (i > 0) ss << ",";
            auto fmt = boost::format(" %2%-%3%@%1%(%4%)")
                    % swap->pool->exchange->name
                    % swap->tokenSrc->symbol
                    % swap->tokenDest->symbol
                    % swap->pool->tag;
            ss << fmt;
        }
        ss << " yield is " << ratio;
        log_info("%1%", ss.str().c_str());
        ctr++;
    }
}



} // namespace model
} // namespace bofh
