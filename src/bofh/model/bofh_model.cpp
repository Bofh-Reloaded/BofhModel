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


const Exchange *TheGraph::add_exchange(const Exchange::name_t &name)
{
    auto i = exchanges.find(name);
    if (i != exchanges.end())
    {
        return i->second;
    }
    auto entry = exchanges.emplace(name, Exchange::make());
    entry.first->second->name = &entry.first->first;
    return entry.first->second;
}


const Token *TheGraph::add_token(const std::string &name
                                 , const char *address
                                 , bool is_stablecoin)
{
    auto entity_type = EntityType::TOKEN;
    auto res = index->emplace(address, entity_type);
    auto has_been_added = res.second;
    auto &entry = res.first->second;
    if (has_been_added)
    {
        auto address_ptr = &res.first->first;
        entry.token = Token::make(&name, address_ptr, is_stablecoin);
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


const SwapPair *TheGraph::add_swap_pair(const char *address
                                        , Token *token0
                                        , Token *token1)
{
    check_not_null_arg(address);
    check_not_null_arg(token0);
    check_not_null_arg(token1);
    auto entity_type = EntityType::SWAP_PAIR;
    auto res = index->emplace(address, entity_type);
    auto has_been_added = res.second;
    auto &entry = res.first->second;
    if (has_been_added)
    {
        auto address_ptr = &res.first->first;
        entry.swap_pair = SwapPair::make(address_ptr, token0, token1);
    }
    else {
        // already known to the index. Check it it's of the correct type
        if (entry.type != entity_type)
        {
            // it's not. sorry
            return nullptr;
        }

    }

    return entry.swap_pair;
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

const SwapPair *TheGraph::lookup_swap_pair(const address_t &address)
{
    auto entity_type = EntityType::SWAP_PAIR;
    auto res = index->find(address);
    if (res == index->end() || res->second.type != entity_type)
    {
        return nullptr;
    }
    return res->second.swap_pair;
}


} // namespace model
} // namespace bofh
