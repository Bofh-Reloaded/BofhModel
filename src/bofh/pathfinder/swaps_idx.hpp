/**
 * @file swaps_idx.hpp
 * @brief Lookup index for swap opportunities
 */

#pragma once

#include "finder_3way.hpp"
#include <boost/functional/hash.hpp>
#include <map>

namespace bofh {
namespace pathfinder {
namespace idx {


/**
 * @brief Represents an one-way transition between two tokens
 *
 * It's not a swap though. This is used as key for searches
 * in our swap knowledge database.
 *
 * It can be used to select those swaps in which the mentioned
 * token swap combination appears at least once.
 */
struct TokenTransition
{
    using Token = model::Token;

    const std::size_t hashValue;

    static std::size_t calcHash(const Token *tokenSrc
                                , const Token *tokenDest)
    {
        std::size_t h = 0U;
        boost::hash_combine(h, tokenSrc);
        boost::hash_combine(h, tokenDest);
        return h;
    }

    TokenTransition(const Token *tokenSrc,
                    const Token *tokenDest)
        : hashValue(calcHash(tokenSrc, tokenDest))
    { }

    bool operator==(const TokenTransition &o) const noexcept { return hashValue == o.hashValue; }

    struct hash {
        std::size_t operator()(const TokenTransition &o) const noexcept { return o.hashValue; }
    };

};



struct SwapPathsIndex {
    // effective owenr of Path object pointers (stored here so that later they can be deleted)
    // TODO: use unique_ptr and correct RAII
    std::list<const Path3Way*> holder;

    // in case anyone is baffled by what an unordered_multimap is,
    // this implements the case of one-to-many map: key -> multiple values.
    // It's an index of occurring token transitions among all known paths,
    // versus one or more path objects in which that transition occurs.
    // The weird predicament of TokenTransition::hash is the least ugly way
    // to effectively establish an hashed index. Sorry.
    std::unordered_multimap<TokenTransition
                            , const Path3Way*
                            , TokenTransition::hash> paths;


};

} // namespace idx
} // namespace pathfinder
} // namespace bofh

