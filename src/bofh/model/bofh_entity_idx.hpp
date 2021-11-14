#pragma once
#include "bofh_model_fwd.hpp"
#include "bofh_types.hpp"
#include <unordered_map>
#include <hash_fun.h>
#include <boost/functional/hash.hpp>

namespace bofh {
namespace model {
namespace idx {

enum class EntityType {
    TOKEN,
    SWAP_PAIR
};

struct IndexEntry {
    EntityType type;
    union {
        Token* token;
        SwapPair* swap_pair;
    };

    IndexEntry(EntityType t): type(t) {}
};

struct address_sort
{
    size_t operator()( const address_t & key ) const
    {
        return boost::hash_range(key.begin(), key.end());
    }
};

struct EntityIndex: std::unordered_map<address_t, IndexEntry, address_sort> {};

} // namespace idx
} // namespace model
} // namespace bofh
