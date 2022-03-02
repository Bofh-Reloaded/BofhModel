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
#include "bofh_constraints.hpp"
#include "bofh_amm_estimation.hpp"
#include <boost/noncopyable.hpp>
#include <boost/python/object.hpp>
#include <set>
#include <memory>
#include <mutex>
#include "../pathfinder/swaps_idx_fwd.hpp"
#include "../pathfinder/paths.hpp"


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
    TheGraph          *parent;

    Entity(const EntityType_e type_
           , datatag_t        tag_
           , const address_t &address_
           , TheGraph *parent_)
        : type(type_)
        , tag(tag_)
        , address(address_)
        , parent(parent_)
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

    /**
     * @brief accrued fees (parts per million). <0 means rebate
     */
    int feesPPM() const;
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
          , TheGraph *parent_
          , const string &name_
          , const std::string &symbol_
          , unsigned int decimals_
          , bool is_stable_)
        : Entity(TYPE_TOKEN, tag_, address_, parent_)
        , name(name_)
        , is_stable(is_stable_)
        , symbol(symbol_)
        , decimals(decimals_)
    { }

    double fromWei(const balance_t &b) const
    {
        return b.convert_to<double>() / std::pow(10, decimals);
    }

    balance_t toWei(double amount) const {
        return balance_t(amount * std::pow(10, decimals));
    }
};


/**
 * @brief Models the identity of an Exchange entity, which is
 * basically relatable to a subset of Liquidity Pools.
 *
 * Exchanges tie LiquidityPool together under their hat.
 */
struct Exchange: Entity, Ref<Exchange> {
    const string name;
    std::unique_ptr<amm::Estimator> estimator;

    Exchange(datatag_t tag_
             , const address_t &address_
             , TheGraph *parent_
             , const string &name_);
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
    struct MissingReservesError: std::runtime_error
    {
        using std::runtime_error::runtime_error;
    };

    typedef double rate_t;

    const Exchange* exchange;
    Token* token0;
    Token* token1;
    const OperableSwap *swaps[2];
    balance_t reserve0;
    balance_t reserve1;
    bool reserves_set = false;

    typedef std::tuple<bool, const balance_t&, const balance_t&> reserves_ref;

    LiquidityPool(datatag_t tag_
                  , const address_t &address_
                  , TheGraph *parent_
                  , const Exchange* exchange_
                  , Token* token0_
                  , Token* token1_)
      : Entity(TYPE_LP, tag_, address_, parent_),
        exchange(exchange_),
        token0(token0_),
        token1(token1_)
    { }

    void setReserves(const balance_t &reserve0, const balance_t &reserve1);
    const balance_t getReserve(const Token *token) const noexcept;
    reserves_ref getReserves() const noexcept;
    std::string get_name() const;


    /**
     * @brief calculates the cost to buy a given wantedAmount of wantedToken
     */
    balance_t SwapTokensForExactTokens(const Token *wantedToken, const balance_t &wantedAmount) const;

    /**
     * @brief calculates the token balance received for in return for selling sentAmount of tokenSent
     */
    balance_t SwapExactTokensForTokens(const Token *tokenSent, const balance_t &sentAmount) const;

    /**
     * @brief accrued fees (parts per million). <0 means rebate
     */
    int feesPPM() const;



    struct LPPredictedState {
        std::unique_ptr<LiquidityPool> pool;
        int ctr = 0;
        LPPredictedState(const LiquidityPool &);
    };
    std::unique_ptr<LPPredictedState> predicted_state;

    const LiquidityPool *enter_predicted_state();
    const LiquidityPool *get_predicted_state() const;
    void set_predicted_reserves(const balance_t &reserve0, const balance_t &reserve1);
    void leave_predicted_state(bool force=false);
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
struct TheGraph: boost::noncopyable, Ref<TheGraph>
{

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
    std::mutex m_update_mutex;
    typedef std::lock_guard<std::mutex> lock_guard_t;

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
     * @brief Introduce a new LP edge into the graph, if not existing. (low level)
     * If the pair already exists, do nothing and return its reference.
     * @param exchange
     * @param address
     * @param token0
     * @param token1
     * @param rate
     * @return reference to the LP, or NULL in case of error
     */
    const LiquidityPool *add_lp_ll(datatag_t tag
                                , const char *address
                                , const Exchange* exchange
                                , Token* token0
                                , Token* token1);
    /**
     * @brief Introduce a new LP edge into the graph, if not existing.
     *
     * All validations are done in-code. This saves some time at init time.
     * @param tag
     * @param address
     * @param exchange
     * @param token0
     * @param token1
     * @return reference to the LP, or NULL in case of error
     */
    const LiquidityPool *add_lp(datatag_t tag
                                , const char *address
                                , datatag_t exchange
                                , datatag_t token0
                                , datatag_t token1);


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
    std::vector<const OperableSwap *> lookup_swap(const Token *token0, const Token *token1);

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


    using Path = pathfinder::Path;
    using PathResult = pathfinder::PathResult;
    using PathResultList = pathfinder::PathResultList;



    /**
     * Evaluate all known paths for convenience (debug usage. Just prints output)
     *
     * The function enumerates all known paths that match the specified constraints.
     */
    PathResultList debug_evaluate_known_paths(const PathEvalutionConstraints &constraints);


    void add_lp_of_interest(const LiquidityPool *pool);
    void clear_lp_of_interest();
    PathResultList evaluate_paths_of_interest(const PathEvalutionConstraints &constraints
                                              , bool observe_predicted_state);
    PathResult evaluate_path(const PathEvalutionConstraints &constraints
                             , const pathfinder::Path *path
                             , bool observe_predicted_state) const;
    PathResult evaluate_path(const PathEvalutionConstraints &constraints, std::size_t path_hash) const;
    std::set<LiquidityPool*> lp_of_interest;

    const Path *lookup_path(std::size_t id) const;
    const Path *add_path(const LiquidityPool *p0
                         , const LiquidityPool *p1
                         , const LiquidityPool *p2);
    const Path *add_path(const LiquidityPool *p0
                         , const LiquidityPool *p1
                         , const LiquidityPool *p2
                         , const LiquidityPool *p3);
    const Path *add_path(datatag_t p0
                         , datatag_t p1
                         , datatag_t p2);
    const Path *add_path(datatag_t p0
                         , datatag_t p1
                         , datatag_t p2
                         , datatag_t p3);


    void set_fetch_exchange_tag_cb(boost::python::object cb);
    void set_fetch_token_tag_cb(boost::python::object cb);
    void set_fetch_lp_tag_cb(boost::python::object cb);
    void set_fetch_lp_reserves_tag_cb(boost::python::object cb);
    void set_fetch_path_tag_cb(boost::python::object cb);
    void set_fetch_token_addr_cb(boost::python::object cb);
    void set_fetch_lp_addr_cb(boost::python::object cb);

    boost::python::object m_fetch_exchange_tag_cb;
    boost::python::object m_fetch_token_tag_cb;
    boost::python::object m_fetch_lp_tag_cb;
    boost::python::object m_fetch_lp_reserves_tag_cb;
    boost::python::object m_fetch_path_tag_cb;
    boost::python::object m_fetch_token_addr_cb;
    boost::python::object m_fetch_lp_addr_cb;
};



} // namespace model
} // namespace bofh

