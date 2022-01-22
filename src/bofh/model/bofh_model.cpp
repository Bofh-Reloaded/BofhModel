#include "bofh_model.hpp"
#include "bofh_entity_idx.hpp"
#include "../pathfinder/swaps_idx.hpp"
#include "../pathfinder/finder_3way.hpp"
#include "../commons/bofh_log.hpp"

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



} // namespace model
} // namespace bofh
