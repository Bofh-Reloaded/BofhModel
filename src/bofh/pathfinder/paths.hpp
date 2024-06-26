#pragma once

#include <bofh/model/bofh_model_fwd.hpp>
#include <bofh/model/bofh_types.hpp>
#include <functional>
#include <exception>
#include <cstring>
#include <iostream>
#include <vector>

namespace bofh {
namespace pathfinder {

using OperableSwap = model::OperableSwap;
using PathEvalutionConstraints = model::PathEvalutionConstraints;

struct PathConsistencyError: std::runtime_error
{
    using std::runtime_error::runtime_error;
};


typedef enum {
    PATH_2WAY = 2,
    PATH_3WAY = 3,
    PATH_4WAY = 4,
} PathLength;
constexpr auto MIN_PATHS = PATH_2WAY;
constexpr auto MAX_PATHS = PATH_4WAY;

struct Path;

struct PathResult {
    explicit PathResult(const Path *p) : path(p) {}
    PathResult() = delete;
    PathResult(const PathResult &) = default;

    const Path                               *path;
    std::array<model::balance_t, MAX_PATHS+1> m_balances_issued;
    std::array<model::balance_t, MAX_PATHS+1> m_balances_measured;

    bool operator==(const PathResult &o) const noexcept
    {
        return id() == o.id();
    }

    bool failed = false;
    std::string infos() const;
    model::balance_t initial_balance() const;
    model::balance_t final_balance() const;
    void set_initial_balance(const model::balance_t &val);
    void set_final_balance(const model::balance_t &val);

    model::balance_t issued_balance_before_step(unsigned idx) const;
    model::balance_t issued_balance_after_step(unsigned idx) const;
    model::balance_t measured_balance_before_step(unsigned idx) const;
    model::balance_t measured_balance_after_step(unsigned idx) const;
    void set_issued_balance_before_step(unsigned idx, const model::balance_t &val);
    void set_issued_balance_after_step(unsigned idx, const model::balance_t &val);
    void set_measured_balance_before_step(unsigned idx, const model::balance_t &val);
    void set_measured_balance_after_step(unsigned idx, const model::balance_t &val);

    const model::Token *initial_token() const;
    const model::Token *final_token() const;
    const model::Token *token_before_step(unsigned idx) const;
    const model::Token *token_after_step(unsigned idx) const;
    double yield_ratio() const;
    std::size_t id() const;

    // some reference data can be externally attached here:
    model::datatag_t tag;
    std::string calldata;
    typedef std::array<model::balance_t, MAX_PATHS*2> pool_reserves_t;
    std::shared_ptr<pool_reserves_t> pool_reserves;
    model::balance_t pool_reserve(unsigned idx, unsigned reserve0_or_1) const;
    void set_pool_reserve(unsigned idx, unsigned reserve0_or_1, const model::balance_t &val);
    model::balance_t pool_token_reserve(unsigned idx, const model::Token *t) const;
    void set_pool_token_reserve(unsigned idx, const model::Token *t, const model::balance_t &val);
    std::string get_calldata(bool deflationary=false) const;
    std::string get_description() const;
};

typedef std::vector<PathResult> PathResultList;
typedef std::vector<const Path *> PathList;

std::ostream& operator<< (std::ostream& stream, const Path& o);
std::ostream& operator<< (std::ostream& stream, const PathResult& o);


/**
 * @brief The Path struct
 *
 * Describes a sequential chain of swaps.
 * The chain can accomodate various notable lengths. @see PathLength
 *
 * It extends std::array for improved usability. It's a POD,
 * trivially copyable and uses no heap.
 */
struct Path: std::array<const OperableSwap *, MAX_PATHS>
{
    typedef std::array<const OperableSwap *, MAX_PATHS> base_t;
    typedef const OperableSwap * value_type;
    typedef const model::LiquidityPool * alt_value_type;

    PathLength type;
    std::size_t m_hash; // cached id

    Path() = delete;

    Path(value_type v0, value_type v1);
    Path(value_type v0, value_type v1, value_type v2);
    Path(value_type v0, value_type v1, value_type v2, value_type v3);
    Path(const model::Token *start_token, const model::LiquidityPool *pools[], std::size_t size);

    // special API to build short, unconnected or non-circular paths.
    // This is only being used to generate partial paths that are necessary to quickly
    // evaluate exchangeability of an unknown token.
    struct unconnected_path {};
    Path(const unconnected_path &
         , const model::Token *start_token
         , const model::LiquidityPool *pools[]
         , std::size_t size);

    static const Path *reversed(const Path *p);

    /**
     * @brief returns number of swaps in the chain
     */
    unsigned int size() const noexcept { return static_cast<unsigned int>(type); }

    /**
     * @brief read element at position @p idx
     */
    value_type get(unsigned int idx) const noexcept { return operator[](idx); }

    /**
     * @brief callback type
     *
     * Algos that discover Path3Way objects don't simply add them to lists
     * to be passed arount.
     * They invoke a callback functor upon discovery of a valid path,
     * and whatever is at the other end gets the notification.
     *
     * This saves on memory and time.
     */
    typedef std::function<bool(const Path *)> listener_t;

    std::string print_addr() const;
    std::string get_symbols() const;

    /**
     * @brief identifier of a known path
     *
     * Two paths are assumed to be collimating if they have the same ID.
     *
     * This value is computed by hashing the addresses of the crossed pools,
     * in their appeareance order. Therefore is repeatable across
     * different sessions.
     */
    std::size_t id() const { return m_hash; };

    bool operator==(const Path &o) const noexcept
    {
        return id() == o.id();
    }

    const model::Token *initial_token() const;
    const model::Token *final_token() const;
    const model::Token *token_before_step(unsigned idx) const;
    const model::Token *token_after_step(unsigned idx) const;

    bool check_consistency(bool no_except=false) const;
    bool is_cross_exchange() const;

    PathResult evaluate(const PathEvalutionConstraints &
                        , unsigned prediction_snapshot_key) const;
    PathResult evaluate_max_yield(const PathEvalutionConstraints &
                        , unsigned prediction_snapshot_key) const;
};


} // namespace pathfinder
} // namespace bofh

