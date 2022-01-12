#pragma once

#include "bofh_common.hpp"
#include "bofh_model_fwd.hpp"
#include "bofh_types.hpp"
#include "bofh_entity_idx_fwd.hpp"
#include <vector>
#include <functional>
#include <boost/multiprecision/cpp_int.hpp>
#include <boost/functional/hash.hpp>


namespace bofh {
namespace model {

struct IndexedObject {
    datatag_t tag;
    const address_t *address;
    IndexedObject(const address_t *address_): address(address_) {}
};


/**
 * @brief Define a potential swap from a token to another.
 *
 * The swap is operatoed via the referred pool.
 * This object is only necessary in order to clearly define graph
 * edge connectivity in an uni-directional way. This allows
 * nodes (tokens) to have a set of predecessors and successors.
 */
struct OperableSwap: Ref<OperableSwap> {
    const Token* tokenFrom;
    const Token* tokenTo;
    const LiquidityPool *pool;
    const std::size_t hashValue; // pre-computed on init for performance reasons

    std::size_t m_calcHash() const
    {
        std::size_t res = 0;
        boost::hash_combine(res, tokenFrom);
        boost::hash_combine(res, tokenTo);
        boost::hash_combine(res, pool);
        return res;
    }

    OperableSwap(const Token *tokenFrom_
                 , const Token *tokenTo_
                 , const LiquidityPool *pool_):
        tokenFrom(tokenFrom_),
        tokenTo(tokenTo_),
        pool(pool_),
        hashValue(m_calcHash())
    { }
    OperableSwap(const OperableSwap &) = default;

    bool operator==(const OperableSwap &o) const noexcept {
        return hashValue == o.hashValue;
    }
    bool operator<(const OperableSwap &o) const noexcept {
        return hashValue < o.hashValue;
    }
};


/**
 * @brief DeFi token identifier
 *
 * Identifies a tradable asset.
 *
 * @todo extend me.
 */
struct Token: Ref<Token>, IndexedObject
{
    const string name;
    const bool is_stable;
    const string symbol;
    const unsigned int decimals;

    /**
     * @brief Token ctor
     * @param name_ (may be null). name is copied and not referenced if non-null and non-empty
     * @param address_
     * @param is_stablecoin_
     */
    Token(const string &name_
          , const address_t *address_
          , const std::string &symbol_
          , unsigned int decimals_
          , bool is_stable_)
        : IndexedObject(address_)
        , name(name_)
        , is_stable(is_stable_)
        , symbol(symbol_)
        , decimals(decimals_)
    { }

    struct OperableSwaps: std::vector<OperableSwap*>
    {
        typedef std::vector<OperableSwap*> base_t;
        using base_t::vector;
    };

    OperableSwaps predecessors;
    OperableSwaps successors;
};


/**
 * @brief Models the identity of an Exchange entity, which is
 * basically relatable to a subset of Liquidity Pools.
 *
 * LP objects have an outgoing relation toward the exchange they
 * are part of.
 */
struct Exchange: Ref<Exchange>, IndexedObject {
    typedef std::string name_t;
    const name_t name;
    Exchange(const name_t &name_
             , const address_t *address_)
        : IndexedObject(address_)
        , name(name_)
        {}
};


/**
 * @brief A facility which swaps between two tokens.
 *
 * A LiquidityPool represents a possibility to execute a swap
 * between two tokens. It corresponds to a liquidity pool in the blockchain.
 *
 * For each affering token (token0, token1), it stores a certain amount
 * of balance (reserve0, reserve1).
 *
 * @todo This is of course ideal and needs to consider commissions and other costs.
 *       There's lots of real world stuff that belongs here.
 *
 * @todo consider to promote this to finite math instead of using double.
 *       There's no "double" in finance.
 *
 * @todo Missing defi exchange ref, contract id and stuff. All this to come later.
 */
struct LiquidityPool: Ref<LiquidityPool>, IndexedObject
{
    typedef double rate_t;

    const Exchange* exchange;
    Token* token0;
    Token* token1;
    balance_t reserve0;
    balance_t reserve1;

    void check()
    {
        assert(exchange != nullptr);
        assert(token0 != nullptr);
        assert(token1 != nullptr);
    }

    LiquidityPool(const Exchange* exchange_
             , const address_t *address_
             , Token* token0_
             , Token* token1_)
      : IndexedObject(address_),
        exchange(exchange_),
        token0(token0_),
        token1(token1_)
    {
        check();
    }
};


/**
 * @brief Graph of known tokens and liquidity pools
 *
 * Let's approach the problem with a graph model.
 * All possible swaps between tokens are modeled as edges of a graph.
 * This is seen as a directed graph btw.
 *
 * Lots of interesting graph algorithms can be conveyed in ASIC or
 * massively parallel form, and their implementation is already known.
 *
 * We want to be in that neighborhood.
 */
struct TheGraph: Ref<TheGraph> {

    // This is to clarify what in this graph is a node and and edge:
    typedef Token Node;
    typedef LiquidityPool Edge;

    typedef std::vector<Node*> NodeList;

    NodeList nodes;
    idx::EntityIndex *index;


    typedef std::unordered_map<Exchange::name_t, Exchange*> ExchangeList;
    ExchangeList exchanges;

    TheGraph();


    const Exchange *add_exchange(const Exchange::name_t &name
                                 , const char *address);

    /**
     * @brief fetch a known exchange node by tag id
     * @warning This takes O(n) time
     */
    const Exchange *lookup_exchange(datatag_t tag);


    /**
     * @brief Introduce a new token node into the graph, if not existing.
     * If the token already exists, do nothing and return its reference.
     * @param name
     * @param address
     * @param is_stablecoin
     * @return reference to the token graph node
     */
    const Token *add_token(const char *name
                           , const char *address
                           , const char *symbol
                           , unsigned int decimals
                           , bool is_stablecoin);

    /**
     * @brief Introduce a new LP edge into the graph, if not existing.
     * If the pair already exists, do nothing and return its reference.
     * @param exchange
     * @param address
     * @param token0
     * @param token1
     * @param rate
     * @return reference to the LP
     */
    const LiquidityPool *add_lp(const Exchange *exchange
                                , const char *address
                                , Token *token0
                                , Token *token1);

    /**
     * @brief fetch a known token node by address
     * @param address
     * @return reference to the token node, if existing. Otherwise nullptr
     */
    const Token *lookup_token(const address_t &address);
    /**
     * @brief fetch a known token node by tag id
     * @warning This takes O(n) time
     */
    const Token *lookup_token(datatag_t tag);

    /**
     * @brief fetch a known LP edge
     * @param address
     * @return reference to the LP, if existing. Otherwise nullptr
     */
    const LiquidityPool *lookup_lp(const address_t &address);
    const LiquidityPool *lookup_lp(const char *address) { return lookup_lp(address_t(address)); }
    /**
     * @brief fetch a known LP node by tag id
     * @warning This takes O(n) time
     */
    const LiquidityPool *lookup_lp(datatag_t tag);

    /**
     * @brief retrieve an address-indexed object from the graph knowledge
     * @param address
     * @return reference to the object, if found. NULL otherwise
     */
    const IndexedObject *lookup(const address_t &address);

    /**
     * @brief reindexes graph knowledge also for datatag id resolution
     */
    void reindex(void);
};



} // namespace model
} // namespace bofh

