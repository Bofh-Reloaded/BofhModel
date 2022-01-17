/**
 * @file bofh_entity_idx.hpp
 * @brief Facility for recurrent lookups on blockchain entities and swaps
 *
 * The machinery implemented here is based around boost::multi_index.
 * multi_index is great but ostensibly tortuous to use and read,
 * which is the reason I've partitioned this code here.
 */

#pragma once
#include "bofh_model.hpp"
#include <boost/multi_index_container.hpp>
#include <boost/multi_index/hashed_index.hpp>
#include <boost/multi_index/composite_key.hpp>
#include <boost/multi_index/member.hpp>
#include <boost/multi_index/ordered_index.hpp>
#include <boost/multi_index/global_fun.hpp>


namespace bofh {
namespace model {
namespace idx {

using namespace boost::multi_index;


/**
 * @defgroup indexes Available indexing (and lookup) strategies
 * @{
 */
struct by_tag {};
struct by_address {};
struct is_stabletoken {};
struct by_src_token {};
struct by_dest_token {};
struct by_src_and_dest_token {};
struct stable_predecessors {};

/** @} */


/**
 * @defgroup key_extractors Entity key extractors.
 *
 * They implement the equivalent of a computed key in a DB.
 *
 * @{
 */
inline bool isEntityStableToken(const Entity& e) noexcept
{
    return e.type == TYPE_TOKEN &&
           reinterpret_cast<const Token&>(e).is_stable;
};
inline bool isSwapDestStableToken(const OperableSwap &s) noexcept
{
    return isEntityStableToken(*s.tokenDest);
};

/** @} */


/**
 * @defgroup EntityIndex Blockchain-addressable index of entities
 *
 * Index container for all blockchain-addressable entities.
 * This at the moment consists of Exchanges, Tokens and LiquidityPools.
 *
 * Items can be looked up:
 *
 *  - by_address in O(1), (trivial)
 *  - by_tag in O(1) and the lookup must pinpoint in advance both tag and entity type
 *  - is_stabletoken, which is a dedicated index to isolate only the stabletoken Token objects
 *
 * @{
 */
/**
 * @brief Base multi_index implementation
 */
typedef multi_index_container<
  Entity*,
  indexed_by<
        // 1. index by on-chain address
          hashed_unique<      tag<by_address>    ,  member<Entity, const address_t, &Entity::address> >
        // 2. index by our own internal reference system:
        //    entities have an attached tracing tag, which tracks PKEY from a DB.
        //    These ids do collide across entity types, so this index is a
        //    composite key to take the necessary 2nd cardinality into account
        , hashed_unique<      tag<by_tag>         ,  composite_key<Entity,
                 member<Entity, const datatag_t   , &Entity::tag>
               , member<Entity, const EntityType_e, &Entity::type>               >
          >
        // 3. partition all entities which are elected stablecoins:
        //    using this index just as a basket. It wastes ram. The solution is
        //    is to host it in its own container (TODO: later).
        , ordered_non_unique< tag<is_stabletoken>,  global_fun<const Entity&, bool, isEntityStableToken> >
  >
> EntityIndex_base;

/**
 * @}
 */


/**
 * @brief Public EntityIndex type
 *
 * @note Promoted as struct in order no to break old API
 */
struct EntityIndex: EntityIndex_base {
    using EntityIndex_base::EntityIndex_base;

    /**
     * @brief lookup entities by tag value
     * @return matching entity pointer or null
     */
    template<typename T, EntityType_e type>
    const T* lookup(datatag_t tag) const noexcept
    {
        auto &idx = get<by_tag>();
        auto i = idx.find(boost::make_tuple(tag, type));
        if (i == idx.end())
        {
            return nullptr;
        }
        return reinterpret_cast<const T*>(&(*i));
    }

    /**
     * @brief lookup entities by on-chain address
     * @return matching entity pointer or null
     */
    template<typename T>
    const T* lookup(const address_t &addr) const noexcept
    {
        auto &idx = get<by_address>();
        auto i = idx.find(addr);
        if (i == idx.end())
        {
            return nullptr;
        }
        return reinterpret_cast<const T*>(&(*i));
    }
};


/**
 * @defgroup SwapIndex Index of known swaps
 *
 * Swaps operate a currency change operation in one direction
 * between a source and a destination token. They tie together
 * source, destination token and the operable LiquidityPool.
 *
 * Swaps can be looked up:
 *
 *  - by_src_token
 *
 * @{
 */
/**
 * @brief Base multi_index implementation
 */
typedef multi_index_container<
  OperableSwap*,
  indexed_by<
          ordered_non_unique< tag<by_src_token>,  composite_key<OperableSwap,
                 member<OperableSwap, const Token*, &OperableSwap::tokenSrc>
               , member<OperableSwap, const LiquidityPool*, &OperableSwap::pool>               >
          >
        , ordered_non_unique< tag<by_dest_token>,  composite_key<OperableSwap,
                 member<OperableSwap, const Token*, &OperableSwap::tokenDest>
               , member<OperableSwap, const LiquidityPool*, &OperableSwap::pool>               >
          >
        , ordered_non_unique< tag<by_src_and_dest_token>,  composite_key<OperableSwap,
                 member<OperableSwap, const Token*, &OperableSwap::tokenDest>
               , member<OperableSwap, const Token*, &OperableSwap::tokenSrc>                   >
          >
        , ordered_non_unique< tag<stable_predecessors>,  composite_key<OperableSwap,
                 global_fun<const OperableSwap&, bool, isSwapDestStableToken>
               , member<OperableSwap, const Token*, &OperableSwap::tokenDest>                  >
          >
  >
> SwapIndex_base;


/**
 * @brief Public SwapIndex type
 *
 * @note Promoted as struct in order no to break old API
 */
struct SwapIndex: SwapIndex_base
{
    using SwapIndex_base::SwapIndex_base;
};


/**
 * @}
 */


} // namespace idx
} // namespace model
} // namespace bofh


