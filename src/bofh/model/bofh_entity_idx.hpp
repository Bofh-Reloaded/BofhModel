#pragma once
#include "bofh_model_fwd.hpp"
#include <unordered_map>

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

struct EntityIndex: std::unordered_map<address_t, IndexEntry> {};

} // namespace idx
} // namespace model
} // namespace bofh
