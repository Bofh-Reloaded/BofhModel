#pragma once

#include "bofh_common.hpp"
#include "bofh_model_fwd.hpp"
#include "bofh_types.hpp"
#include "bofh_entity_idx_fwd.hpp"
#include <vector>
#include <boost/multiprecision/cpp_int.hpp>


namespace bofh {
namespace model {

struct IndexedObject {
    datatag_t tag;
    const address_t *address;
    IndexedObject(const address_t *address_): address(address_) {}
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
    const string *name = nullptr;
    const bool is_stablecoin;

    /**
     * @brief Token ctor
     * @param name_ (may be null). name is copied and not referenced if non-null and non-empty
     * @param address_
     * @param is_stablecoin_
     */
    Token(const string *name_
          , const address_t *address_
          , bool is_stablecoin_)
        : IndexedObject(address_)
        , is_stablecoin(is_stablecoin_)
    {
        if (name_ != nullptr && !name_->empty())
        {
            name = new string(*name_);
        }
    }

    ~Token()
    {
        if (name != nullptr) delete name;
    }

    struct SwapList: std::vector<SwapPair*>
    {
        typedef std::vector<SwapPair*> base_t;
        using base_t::vector;
    };

    SwapList swaps;
};


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
 * @brief A swap between two tokens
 *
 * A SwapPair represents a possibility to execute a swap
 * between two tokens. It corresponds to a liquidity pool in the blockchain.
 *
 * @todo This is of course ideal and needs to consider commissions and other costs.
 *       There's lots of real world stuff that belongs here.
 *
 * @todo consider to promote this to finite math instead of using double.
 *       There's no "double" in finance.
 *
 * @todo Missing defi exchange ref, contract id and stuff. All this to come later.
 */
struct SwapPair: Ref<SwapPair>, IndexedObject
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

    SwapPair(const Exchange* exchange_
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
 * @brief Graph of known tokens and swaps paths
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
    typedef SwapPair Edge;
    // ... nodes are tokens, edges connecting them are swap pairs. Note that
    //     swaps are not bidirectional at the moment. Therefore this is
    //     a directed graph.

    typedef std::vector<Node*> NodeList;

    NodeList nodes;
    idx::EntityIndex *index;


    typedef std::unordered_map<Exchange::name_t, Exchange*> ExchangeList;
    ExchangeList exchanges;

    TheGraph();


    const Exchange *add_exchange(const Exchange::name_t &name
                                 , const char *address);


    /**
     * @brief Introduce a new token node into the graph, if not existing.
     * If the token already exists, do nothing and return its reference.
     * @param name
     * @param address
     * @param is_stablecoin
     * @return reference to the token graph node
     */
    const Token *add_token(const std::string &name
                           , const char *address
                           , bool is_stablecoin);

    /**
     * @brief Introduce a new swap pair edge into the graph, if not existing.
     * If the pair already exists, do nothing and return its reference.
     * @param exchange
     * @param address
     * @param token0
     * @param token1
     * @param rate
     * @return reference to the swap pair
     */
    const SwapPair *add_swap_pair(const Exchange *exchange
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
     * @brief fetch a known swap pair edge
     * @param address
     * @return reference to the swap pair, if existing. Otherwise nullptr
     */
    const SwapPair *lookup_swap_pair(const address_t &address);
    const SwapPair *lookup_swap_pair(const char *address) { return lookup_swap_pair(address_t(address)); }
    /**
     * @brief fetch a known swap pair node by tag id
     * @warning This takes O(n) time
     */
    const SwapPair *lookup_swap_pair(datatag_t tag);

    /**
     * @brief retrieve an address-indexed object from the graph knowledge
     * @param address
     * @return reference to the object, if found. NULL otherwise
     */
    const IndexedObject *lookup(const address_t &address);

    /**
     * @brief reindexes graph knowledge also for datatag id resolution
     */
    void reindex_tags(void);
};



} // namespace model
} // namespace bofh
