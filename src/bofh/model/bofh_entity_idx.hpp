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

struct datatag_indexed_key {
    EntityType type;
    datatag_t tag;
    std::size_t hashValue;

    datatag_indexed_key(EntityType type_, datatag_t tag_)
        : type(type_)
        , tag(tag_)
        , hashValue(0)
    {
        boost::hash_combine(hashValue, type);
        boost::hash_combine(hashValue, tag);
    }

    bool operator==(const datatag_indexed_key&o) const noexcept {
        return hashValue == o.hashValue;
    }
    bool operator<(const datatag_indexed_key&o) const noexcept {
        return hashValue < o.hashValue;
    }

    struct hasher {
        std::size_t operator()(datatag_indexed_key const& s) const noexcept {
            return s.hashValue;
        }
    };

};



struct EntityIndex: std::unordered_map<address_t, IndexEntry, address_sort> {
    std::unordered_map<datatag_indexed_key, IndexEntry, datatag_indexed_key::hasher> tag_index;
    std::set<Token*> stable_tokens;
};

} // namespace idx
} // namespace model
} // namespace bofh


