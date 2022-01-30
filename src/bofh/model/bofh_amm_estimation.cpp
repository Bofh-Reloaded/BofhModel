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
                              , unsigned int feePPK = 0)
{
    if (amountIn <= 0)
    {
        throw swap_error("INSUFFICIENT_INPUT_AMOUNT");
    }
    if (reserveIn <= 0 || reserveOut <= 0)
    {
        throw swap_error("INSUFFICIENT_LIQUIDITY");
    }

    const auto amountInWithFee = amountIn * (1000-feePPK);
    const auto numerator = amountInWithFee * reserveOut;
    const auto denominator = (reserveIn * 1000) + amountInWithFee;
    return numerator / denominator;
}

/**
 * given an output amount of an asset and pair reserves, returns a required input amount of the other asset
 */
static balance_t getAmountIn(const balance_t &amountOut
                              , const balance_t &reserveIn
                              , const balance_t &reserveOut
                              , unsigned int feePPK = 0)
{
    if (amountOut <= 0)
    {
        throw swap_error("INSUFFICIENT_INPUT_AMOUNT");
    }
    if (reserveIn <= 0 || reserveOut <= 0)
    {
        throw swap_error("INSUFFICIENT_LIQUIDITY");
    }

    const auto numerator = reserveIn * amountOut * 1000;
    const auto denominator = (reserveOut - amountOut) * (1000-feePPK);
    return (numerator / denominator) + 1;
}


#if 0
// OBSOLETE CODE: uses floating point. It's not ideal (sometimes error >0.1%)
typedef balance_t DeltaX; // amount of token sold
typedef balance_t DeltaY; // amount of token bought
typedef double Beta;  // output token reserve impact
typedef double Alpha; // input token reserve impact
typedef double Gamma; // fees


static auto the_other_token = [](auto pool, auto token)
{
    assert(token == pool->token0 || token == pool->token1);
    return token == pool->token0 ? pool->token1 : pool->token0;
};

static DeltaX calcRequiredToBuy(const LiquidityPool *pool
                                , const Token *wantedToken
                                , const DeltaY &dy
                                , Gamma gamma = 1.0f)
{
    const auto soldToken = the_other_token(pool, wantedToken);
    const auto x = pool->getReserve(wantedToken).convert_to<double>();
    const auto y = pool->getReserve(soldToken);
    const Beta beta = dy.convert_to<double>() / y.convert_to<double>();
    return DeltaX(((beta * x) / gamma) / (1 - beta));
}


static DeltaY calcBoughtPerAmountSold(const LiquidityPool *pool
                                      , const Token *soldToken
                                      , const DeltaX &dx
                                      , Gamma gamma = 1.0f)
{
    const auto wantedToken = the_other_token(pool, soldToken);
    const auto x = pool->getReserve(soldToken);
    const auto y = pool->getReserve(wantedToken).convert_to<double>();
    const Alpha alpha = (dx.convert_to<Alpha>() / x.convert_to<Alpha>()) * gamma;
    return DeltaY((alpha * y) / (1 - alpha));
}
#endif


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
    return getAmountIn(boughtAmount
                       , pool->getReserve(boughtToken == pool->token0 ? pool->token1 : pool->token0)
                       , pool->getReserve(boughtToken)
                       , feesPPK());
}

balance_t EstimatorWithProportionalFees::SwapExactTokensForTokens(const LiquidityPool *pool, const Token *soldToken, const balance_t &soldAmount) const
{
    return getAmountOut(soldAmount
                        , pool->getReserve(soldToken)
                        , pool->getReserve(soldToken == pool->token0 ? pool->token1 : pool->token0)
                        , feesPPK());
}


} // namespace amm
} // namespace model
} // namespace bofh


