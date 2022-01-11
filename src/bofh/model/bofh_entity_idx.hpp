#pragma once
#include "bofh_model_fwd.hpp"
#include "bofh_types.hpp"
#include <unordered_map>
#include <set>
#include <hash_fun.h>
#include <boost/functional/hash.hpp>

namespace bofh {
namespace model {
namespace idx {

enum class EntityType {
    TOKEN,
    LP,
    EXCHANGE
};

struct IndexEntry {
    EntityType type;
    union {
        Token* token;
        LiquidityPool *lp;
        Exchange *exchange;
        IndexedObject *indexed_object;
    };

    IndexEntry(EntityType t): type(t) {}
    IndexEntry(const IndexEntry &t) = default;
};

struct address_sort
{
    size_t operator()( const address_t & key ) const
    {
        return boost::hash_range(key.begin(), key.end());
    }
};

struct EntityIndex: std::unordered_map<address_t, IndexEntry, address_sort> {
    std::unordered_map<datatag_t, IndexEntry> tag_index;
    std::set<Token*> stable_tokens;
};

} // namespace idx
} // namespace model
} // namespace bofh
