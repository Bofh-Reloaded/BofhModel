/**
 * @file bofh_model.hpp
 * @brief Models for entities which have a role in the blockchain.
 *
 * This includes:
 *
 *  - Exchange
 *  - Token
 *  - LiquidityPool
 *  - OperableSwap
 *  - TheGraph
 */

#pragma once

#include "bofh_common.hpp"
#include "bofh_model_fwd.hpp"
#include "bofh_types.hpp"
#include "bofh_entity_idx_fwd.hpp"
#include <boost/noncopyable.hpp>
#include <memory>
#include "../pathfinder/swaps_idx_fwd.hpp"


namespace bofh {
namespace model {

/**
 * @brief base object for all entities that are elected to be part of the main index.
 * @note We are not using language-provided RTTI, that's an explicit choice here.
 */

/**
 * @brief Enum for entity type.
 */
typedef enum {
    TYPE_EXCHANGE,  ///< Exchange object
    TYPE_TOKEN,     ///< Token object
    TYPE_LP,        ///< LiquidityPool object
} EntityType_e;


/**
 * @brief Base for all blockchain-addressable objects
 *
 * In our model, an entity in known by its blockchain address,
 * or (in alternative) by its arbitrary tag number.
 *
 * Multiple entities CAN have the same tag,
 * however two entities of the same type CAN'T.
 */
struct Entity: boost::noncopyable
{

    const EntityType_e type;    ///< type identifier
    const datatag_t    tag;     ///< model consumes attach their identifiers to this member. It will be indexed. Not that it's non-const.
    const address_t    address; ///< 320bit blockchain address of the thing. also indexed.

    Entity(const EntityType_e type_
           , datatag_t        tag_
           , const address_t &address_)
        : type(type_)
        , tag(tag_)
        , address(address_)
    {}
};



/**
 * @brief Define a potential swap from a source to a destination token.
 *
 * The swap is operated by the referred pool.
 * This object ties together a tuple made of:
 *
 *  - tokenSrc
 *  - tokenDest
 *  - pool
 *
 * This object is only necessary in order to clearly define graph
 * edge connectivity in an uni-directional way. This allows
 * nodes (tokens) to have a set of predecessors and successors.
 *
 * In principle, due to the fact that a LP opeates swaps both ways,
 * a token's predecessor set and successor set are the same, however
 * we model this relationship as a directional graph.
 * This grants us an easy way to mark bad or unwanted swaps
 * even in a single direction.
 */
struct OperableSwap: boost::noncopyable, Ref<OperableSwap>
{
    const Token* tokenSrc;
    const Token* tokenDest;
    const LiquidityPool *pool;

    OperableSwap(const Token* tokenSrc_
                 , const Token* tokenDest_
                 , const LiquidityPool *pool_)
        : tokenSrc(tokenSrc_)
        , tokenDest(tokenDest_)
        , pool(pool_)
    { }
};


/**
 * @brief DeFi token identifier
 *
 * Identifies a tradable asset.
 *
 * It corresponds to a token contract instance in the blockchain.
 *
 * @todo extend me.
 */
struct Token: Entity, Ref<Token>
{
    const string name;     ///< descriptive name (debug purposes only)
    const bool is_stable;  ///< true if this token is elected to be considered stable
    const string symbol;   ///< symbol, or ticker name. Ex: "wBNB", "USDT"
    const unsigned int decimals; ///< number of decimals to convert to/fromWei

    Token(datatag_t tag_
          , const address_t &address_
          , const string &name_
          , const std::string &symbol_
          , unsigned int decimals_
          , bool is_stable_)
        : Entity(TYPE_TOKEN, tag_, address_)
        , name(name_)
        , is_stable(is_stable_)
        , symbol(symbol_)
        , decimals(decimals_)
    { }
};


/**
 * @brief Models the identity of an Exchange entity, which is
 * basically relatable to a subset of Liquidity Pools.
 *
 * Exchanges tie LiquidityPool together under their hat.
 */
struct Exchange: Entity, Ref<Exchange> {
    const string name;
    Exchange(datatag_t tag_
             , const address_t &address_
             , const string &name_)
        : Entity(TYPE_EXCHANGE, tag_, address_)
        , name(name_)
        {}
    Exchange(const Exchange &) = delete;
};


/**
 * @brief A facility which swaps between two tokens.
 *
 * A LiquidityPool represents a possibility to execute a swap
 * between two tokens.
 * It corresponds to a liquidity pool contract instance in the blockchain.
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
struct LiquidityPool: Entity, Ref<LiquidityPool>
{
    typedef double rate_t;

    const Exchange* exchange;
    Token* token0;
    Token* token1;
    balance_t reserve0;
    balance_t reserve1;

    LiquidityPool(datatag_t tag_
                  , const address_t &address_
                  , const Exchange* exchange_
                  , Token* token0_
                  , Token* token1_)
      : Entity(TYPE_LP, tag_, address_),
        exchange(exchange_),
        token0(token0_),
        token1(token1_)
    { }

    void setReserve(const Token *token, const balance_t &reserve);
    void setReserves(const balance_t &reserve0, const balance_t &reserve1);
    const balance_t &getReserve(const Token *token);

    /**
     * @brief do the math and simulate a swap
     * @param tokenIn MUST be one of the two affering tokens: either token0 or token1
     * @param amountIn amount of @p tokenIn balance to be converted to the other token
     * @param updateReserves if true, makes the swap "happen" by updating the reserves. This updates the LP
     * @return the balance that the swap yields, for the counterpart of @p tokenIn
     * @note the implementation is LP dependent. Some pools apply fees. This methods attempts to simulate that.
     * @warning probably unnecessary code. Keeping this as a conceptual reference of what may happen inside a real LP
     */
    balance_t simpleSwap(const Token *tokenIn
                         , const balance_t &amountIn
                         , bool updateReserves=false);

    /**
     * @brief same as simpleSwap() but uses simplifies float-only maths, and doesn't update reserves
     */
    double simpleSwapF(const Token *tokenIn, double amountIn) const noexcept;

    /**
     * @brief calculate the current swap ratio
     *
     * 1 * units of tokenIn would result in <return> amount of tokenOut
     *
     * @param tokenIn MUST be one of the two affering tokens: either token0 or token1
     */
    double swapRatio(const Token *tokenIn) const noexcept;

    /**
     * @brief estimate would-be swap stress
     *
     * Returns a ratio estimate (result >= 0.0f) expressing how much
     * a swap execution would stress the pool's reserves.
     *
     * This call is intended help flagging dangerous unbalanced paths.
     */
    double estimateSwapStress(const Token *tokenIn, const balance_t &amountIn) const;

    /**
     * swap fees amount expressed in unitary value (1=100%, 0.03=3%, 0.0003=0.03%)
     */
    double fees() const noexcept { return 0.0003; }

private:
    balance_t k; // cached value of reserve0*reserve1. Updated by setReserve().
                 // in AAM compliant swaps this must remain constant in time

    // i'm keeping cache values in floating point format.
    // Don't really known which one is best for us. Keeping both for now.
    double fk;
    double freserve0;
    double freserve1;
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
struct TheGraph: boost::noncopyable, Ref<TheGraph> {

    //std::unique_ptr<idx::EntityIndex> entity_index;
    idx::EntityIndex *entity_index; // TODO: so, I'm purposefully leaking this
                                    // object because multi_index::detail::hashed_index
                                    // dtor has a bug in it and segfaults on program exit.
                                    // Postponing the problem because multi_index is supposed
                                    // to be used as a quick hack. It will be replaced
                                    // by more custom code if things develop more.
    std::unique_ptr<idx::SwapIndex>   swap_index;
    std::unique_ptr<pathfinder::idx::SwapPathsIndex> paths_index;
    Token *start_token = nullptr;

    TheGraph();

    /**
     * @brief create and index Exchange object
     * @return address of new object. null if already existing
     */
    const Exchange *add_exchange(datatag_t tag
                                 , const char *address
                                 , const string &name
                                 );

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
    const Token *add_token(datatag_t tag
                           , const char *address
                           , const char *name
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
    const LiquidityPool *add_lp(datatag_t tag
                                , const char *address
                                , const Exchange* exchange
                                , Token* token0
                                , Token* token1);

    /**
     * @brief fetch a known token node by address
     * @param address
     * @return reference to the token node, if existing. Otherwise nullptr
     */
    const Token *lookup_token(const char *address);
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
    std::vector<const OperableSwap *> lookup_swap(datatag_t token0, datatag_t token1);

    /**
     * @brief fetch a known LP node by tag id
     * @warning This takes O(n) time
     */
    const LiquidityPool *lookup_lp(datatag_t tag);

    /**
     * initially called (once) to pre-compute all useful swap paths,
     * and add them to an hot index
     */
    void calculate_paths();


    /**
     * @brief Constraints to be used in path opportunity searches
     *
     * @note using a struct because they can add up quickly during development,
     *       and I don't want to pass them as a bunch of individual parameters.
     */
    struct PathEvalutionConstraints {
        /**
         * @brief initial_token_wei_balance
         *
         * specifies the balance amount of start_token
         * weis that whole path MUST be able to handle
         * without inflicting unbalance in any of
         * the transit LPs
         *
         * @default 0 (no constraint)
         */
        balance_t    initial_token_wei_balance = 0;

        /**
         * @brief max_lp_reserves_stress
         *
         * specifies the maximum reserves stress that the path
         * can induce in each of the traversed pool. This accounts
         * for balance inflow and outflow of each executed swap.
         *
         * If any of the pools in the path would receive a reserve
         * shock > @p max_lp_reserves_stress, then the path is discarded
         *
         * @default 0.33 (about 1/3 of LP reserves)
         */
        double       max_lp_reserves_stress = 0.33;

        /**
         * @brief convenience_min_threshold
         *
         * specifies the minimum yield a path should
         * provide, including fees, in order to
         * be considered a candidate.
         * This is intended  to exclude paths that predictably don't yield
         * past a certain acceptable gain threshold.
         *
         * @default 1.0 (break-even or gain only)
         */
        double       convenience_min_threshold=1.0f;

        /**
         * @brief convenience_max_threshold
         *
         * specifies the maximum yield a path should
         * provide, including fees, in order to
         * be considered a candidate.
         *
         * This is intended to exclude the majority of paths that cross
         * one or more LPs which are simply broken in some way, whose
         * maths is completely unbalanced and for which
         * a real swap operation would probably perform unpredictably.
         *
         * @default: 2.0 (or 200% gain, which is way over the top)
         */
        double       convenience_max_threshold=2.0f;

        /**
         * @brief limit
         *
         * limit to the amount of matching paths
         * (does not sort for best or worst. It just stops the output
         * after a certain amount of random matches)
         *
         * @default 0 (no constraint)
         */
        unsigned int limit=0;
    };

    /**
     * Evaluate all known paths for convenience (debug usage. Just prints output)
     *
     * The function enumerates all known paths that match the specified constraints.
     */
    void debug_evaluate_known_paths(const PathEvalutionConstraints &constraints);


};



} // namespace model
} // namespace bofh

