#include "bofh_amm_estimation.hpp"
#include "bofh_model.hpp"
#include <assert.h>
#include "../commons/bofh_log.hpp"

namespace bofh {
namespace model {
namespace amm {


/**
 * Our own AMM x*y=k implementation
 *
 * As specified by "Formal Specification of Constant Product
 * (x × y = k) Market Maker Model and Implementation"
 * (c) Yi Zhang, Xiaohong Chen, and Daejun Park
 *
 * @see docs/x-y-k.pdf
 *
 * Take it away from https://github.com/Uniswap/v2-periphery/blob/87edfdcaf49ccc52591502993db4c8c08ea9eec0/contracts/libraries/UniswapV2Library.sol#L42
 */

/**
 * given an input amount of an asset and pair reserves, returns the maximum output amount of the other asset
 */
static balance_t getAmountOut(const balance_t &amountIn
                              , const balance_t &reserveIn
                              , const balance_t &reserveOut
                              , unsigned int feePPM = 0)
{
    if (amountIn <= 0)
    {
        throw swap_error("INSUFFICIENT_INPUT_AMOUNT");
    }
    if (reserveIn <= 0 || reserveOut <= 0)
    {
        throw swap_error("INSUFFICIENT_LIQUIDITY");
    }

    const auto amountInWithFee = amountIn * (1000000-feePPM);
    const auto numerator = amountInWithFee * reserveOut;
    const auto denominator = (reserveIn * 1000000) + amountInWithFee;
    return numerator / denominator;
}

/**
 * given an output amount of an asset and pair reserves, returns a required input amount of the other asset
 */
static balance_t getAmountIn(const balance_t &amountOut
                              , const balance_t &reserveIn
                              , const balance_t &reserveOut
                              , unsigned int feePPM = 0)
{
    if (amountOut <= 0)
    {
        throw swap_error("INSUFFICIENT_INPUT_AMOUNT");
    }
    if (reserveIn <= 0 || reserveOut <= 0)
    {
        throw swap_error("INSUFFICIENT_LIQUIDITY");
    }

    const auto numerator = reserveIn * amountOut * 1000000;
    const auto denominator = (reserveOut - amountOut) * (1000000-feePPM);
    return (numerator / denominator) + 1;
}


balance_t IdealEstimator::SwapTokensForExactTokens(const LiquidityPool *pool, const Token *boughtToken, const balance_t &boughtAmount) const
{
    return getAmountIn(boughtAmount
                       , pool->getReserve(boughtToken == pool->token0 ? pool->token1 : pool->token0)
                       , pool->getReserve(boughtToken));
}

balance_t IdealEstimator::SwapExactTokensForTokens(const LiquidityPool *pool, const Token *soldToken, const balance_t &soldAmount) const
{
    return getAmountOut(soldAmount
                        , pool->getReserve(soldToken)
                        , pool->getReserve(soldToken == pool->token0 ? pool->token1 : pool->token0));
}

balance_t EstimatorWithProportionalFees::SwapTokensForExactTokens(const LiquidityPool *pool, const Token *boughtToken, const balance_t &boughtAmount) const
{
    auto res = pool->getReserves();
    bool available = std::get<0>(res);
    auto &reserve0 = std::get<1>(res);
    auto &reserve1 = std::get<2>(res);
    if (! available)
    {
        throw LiquidityPool::MissingReservesError(strfmt("missing pool reserves: id=%1%, %2%"
                                                         , pool->tag
                                                         , pool->address));
    }
    return getAmountIn(boughtAmount
                       , boughtToken == pool->token0 ? reserve1 : reserve0
                       , boughtToken == pool->token0 ? reserve0 : reserve1
                       , feesPPM());
}

balance_t EstimatorWithProportionalFees::SwapExactTokensForTokens(const LiquidityPool *pool, const Token *soldToken, const balance_t &soldAmount) const
{
    auto res = pool->getReserves();
    bool available = std::get<0>(res);
    auto &reserve0 = std::get<1>(res);
    auto &reserve1 = std::get<2>(res);
    if (! available)
    {
        throw LiquidityPool::MissingReservesError(strfmt("missing pool reserves: id=%1%, %2%"
                                                         , pool->tag
                                                         , pool->address));
    }
    return getAmountOut(soldAmount
                        , soldToken == pool->token0 ? reserve0 : reserve1
                        , soldToken == pool->token0 ? reserve1 : reserve0
                        , feesPPM());
}


} // namespace amm
} // namespace model
} // namespace bofh


