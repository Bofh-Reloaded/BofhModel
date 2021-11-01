#pragma once
#include "finder_model_fwd.hpp"
#include <unordered_map>

namespace bofh {
namespace model {


enum class IndexEntity {
    TOKEN,
    SWAP_PAIR
};

struct IndexEntry {
    IndexEntity type;
    union {
        Token* token;
        SwapPair* swap_pair;
    };
};

struct MainIndex: std::unordered_map<address_t, IndexEntry> {};

} // namespace model
} // namespace bofh
