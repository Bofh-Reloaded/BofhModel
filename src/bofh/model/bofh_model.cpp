#include "bofh_model.hpp"
#include "bofh_entity_idx.hpp"
#include <exception>


namespace bofh {
namespace model {

using namespace idx;


struct bad_argument: public std::runtime_error
{
    using std::runtime_error::runtime_error ;
};
#define check_not_null_arg(name) if (name == nullptr) throw bad_argument("can't be null: " #name);


TheGraph::TheGraph(): index(new EntityIndex()) {};


const Exchange *TheGraph::add_exchange(const Exchange::name_t &name
                                       , const char *address)
{
    auto entity_type = EntityType::EXCHANGE;

    auto res = index->emplace(address, entity_type);
    auto has_been_added = res.second;
    auto &entry = res.first->second;
    if (has_been_added)
    {
        auto address_ptr = &res.first->first;
        entry.exchange = Exchange::make(name, address_ptr);
    }
    else {
        // already known to the index. Check it it's of the correct type
        if (entry.type != entity_type)
        {
            // it's not. sorry
            return nullptr;
        }
    }

    return entry.exchange;
}

const Exchange *TheGraph::lookup_exchange(datatag_t tag)
{
    auto res = index->tag_index.find(idx::datatag_indexed_key(EntityType::EXCHANGE, tag));
    if (res == index->tag_index.end())
    {
        return nullptr;
    }
    return res->second.exchange;
}



const Token *TheGraph::add_token(const char *name
                                 , const char *address
                                 , const char *symbol
                                 , unsigned int decimals
                                 , bool is_stablecoin)
{
    auto entity_type = EntityType::TOKEN;
    auto res = index->emplace(address, entity_type);
    auto has_been_added = res.second;
    auto &entry = res.first->second;
    if (has_been_added)
    {
        auto address_ptr = &res.first->first;
        entry.token = Token::make(name, address_ptr, symbol, decimals, is_stablecoin);
    }
    else {
        // already known to the index. Check it it's of the correct type
        if (entry.type != entity_type)
        {
            // it's not. sorry
            return nullptr;
        }
    }

    return entry.token;
}


const LiquidityPool *TheGraph::add_lp(const Exchange *exchange
                                        , const char *address
                                        , Token *token0
                                        , Token *token1)
{
    check_not_null_arg(address);
    check_not_null_arg(token0);
    check_not_null_arg(token1);
    auto entity_type = EntityType::LP;
    auto res = index->emplace(address, entity_type);
    auto has_been_added = res.second;
    auto &entry = res.first->second;
    if (has_been_added)
    {
        auto address_ptr = &res.first->first;
        entry.lp = LiquidityPool::make(exchange, address_ptr, token0, token1);
        token0->successors.emplace_back(OperableSwap::make(token0, token1, entry.lp));
        token0->predecessors.emplace_back(OperableSwap::make(token1, token0, entry.lp));
    }
    else {
        // already known to the index. Check it it's of the correct type
        if (entry.type != entity_type)
        {
            // it's not. sorry
            return nullptr;
        }

    }

    return entry.lp;
}

const Token *TheGraph::lookup_token(const address_t &address)
{
    auto entity_type = EntityType::TOKEN;
    auto res = index->find(address);
    if (res == index->end() || res->second.type != entity_type)
    {
        return nullptr;
    }
    return res->second.token;
}

const Token *TheGraph::lookup_token(datatag_t tag)
{
    auto res = index->tag_index.find(idx::datatag_indexed_key(EntityType::TOKEN, tag));
    if (res == index->tag_index.end())
    {
        return nullptr;
    }
    return res->second.token;
}

const LiquidityPool *TheGraph::lookup_lp(const address_t &address)
{
    auto entity_type = EntityType::LP;
    auto res = index->find(address);
    if (res == index->end() || res->second.type != entity_type)
    {
        return nullptr;
    }
    return res->second.lp;
}

const LiquidityPool *TheGraph::lookup_lp(datatag_t tag)
{
    ;
    auto res = index->tag_index.find(idx::datatag_indexed_key(EntityType::LP, tag));
    if (res == index->tag_index.end())
    {
        return nullptr;
    }
    return res->second.lp;
}

const IndexedObject *TheGraph::lookup(const address_t &address)
{
    auto res = index->find(address);
    if (res == index->end())
    {
        return nullptr;
    }
    return res->second.lp;
}

void TheGraph::reindex(void)
{
    index->tag_index.clear();
    index->stable_tokens.clear();
    for (auto &i: *index)
    {
        auto obj = i.second;
        index->tag_index.emplace(idx::datatag_indexed_key(obj.type, obj.indexed_object->tag), i.second);
        if (i.second.type == EntityType::TOKEN
            && i.second.token->is_stable)
        {
            index->stable_tokens.emplace(i.second.token);
        }
    }
}



} // namespace model
} // namespace bofh
