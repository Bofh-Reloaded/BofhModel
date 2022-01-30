/**
 * @file bofh_amm_estimation.hpp
 * @brief Uniswap's AMM (Automated Market Maker) estimator engine
 */

#pragma once

#include "bofh_entity_idx_fwd.hpp"
#include "bofh_types.hpp"

namespace bofh {
namespace model {
namespace amm {


struct swap_error: std::runtime_error
{
    using std::runtime_error::runtime_error;
};

/**
 * @brief The Estimator computes swaps across a LP
 *
 * Two forms of computations are provided, to match the Uniswap model.
 *
 * - "How much tokenB would I get if I sent X amount of tokenA to swap?" is answered by SwapExactTokensForTokens()
 * - "How much tokenA do I need to swap in order to get X amount of tokenB?" is answered by SwapTokensForExactTokens()
 */
struct Estimator
{
    virtual ~Estimator() {}

    // sorry about the horrid naming. These names match Uniswap's,
    // so the reades knows how cross-reference what they do.

    /**
     * @brief calculates the cost to buy a given wantedAmount of wantedToken
     */
    virtual balance_t SwapTokensForExactTokens(const LiquidityPool *pool, const Token *wantedToken, const balance_t &wantedAmount) const = 0;

    /**
     * @brief calculates the token balance received for in return for selling sentAmount of tokenSent
     */
    virtual balance_t SwapExactTokensForTokens(const LiquidityPool *pool, const Token *tokenSent, const balance_t &sentAmount) const = 0;
};


/**
 * @brief This estimator follows the recipe by the book, no fees and no commissions applied.
 */
struct IdealEstimator: Estimator
{
    using Estimator::Estimator;

    virtual balance_t SwapTokensForExactTokens(const LiquidityPool *pool, const Token *boughtToken, const balance_t &boughtAmount) const;
    virtual balance_t SwapExactTokensForTokens(const LiquidityPool *pool, const Token *soldToken, const balance_t &soldAmount) const;
};


/**
 * @brief This estimator attempts to account for proportional fees into the swap operation
 */
struct EstimatorWithProportionalFees: IdealEstimator
{
    using IdealEstimator::IdealEstimator;

    /**
     * @brief fees (part per 1000)
     *
     * Ex: 2 means 0.2%
     */
    virtual unsigned int feesPPK() const { return 2; }
    virtual balance_t SwapTokensForExactTokens(const LiquidityPool *pool, const Token *boughtToken, const balance_t &boughtAmount) const;
    virtual balance_t SwapExactTokensForTokens(const LiquidityPool *pool, const Token *soldToken, const balance_t &soldAmount) const;
};



} // namespace amm
} // namespace model
} // namespace bofh

