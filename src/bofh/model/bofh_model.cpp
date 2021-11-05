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

const Token *TheGraph::add_token(const std::string &name
                           , const address_t &address)
{
    auto entity_type = EntityType::TOKEN;
    auto res = index->emplace(address, entity_type);
    auto has_been_added = res.second;
    auto &entry = res.first->second;
    if (has_been_added)
    {
        entry.token = new Token(name, address);
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

const SwapPair *TheGraph::add_swap_pair(const address_t &address
                                        , const Token::ref token0
                                        , const Token::ref token1
                                        , SwapPair::rate_t rate)
{
    check_not_null_arg(token0);
    check_not_null_arg(token1);
    auto entity_type = EntityType::SWAP_PAIR;
    auto res = index->emplace(address, entity_type);
    auto has_been_added = res.second;
    auto &entry = res.first->second;
    if (has_been_added)
    {
        entry.swap_pair = SwapPair::make(address, token0, token1, rate);
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
