#pragma once

#include "bofh_common.hpp"
#include "bofh_types.hpp"
#include <exception>

namespace bofh {
namespace model {

struct ContraintConsistencyError: std::runtime_error
{
    using std::runtime_error::runtime_error;
};

/**
 * @brief Constraints to be used in path opportunity searches
 *
 * @note using a struct because they can add up quickly during development,
 *       and I don't want to pass them as a bunch of individual parameters.
 */
struct PathEvalutionConstraints {
    /**
     * @brief initial_balance
     *
     * specifies the balance amount of start_token
     * weis that whole path MUST be able to handle
     * without inflicting unbalance in any of
     * the transit LPs
     *
     * @default 0 (no constraint)
     */
    balance_t initial_balance = 0;

    /**
     * @brief initial_balance_min
     *
     * Initial balance amount, used to define a [min, max] range
     * of study to determine the optimal swap amount.
     *
     * @default 0 (no constraint)
     */
    balance_t initial_balance_min = 0;

    /**
     * @brief initial_balance_min
     *
     * Initial balance amount, used to define a [min, max] range
     * of study to determine the optimal swap amount.
     *
     * @default 0 (no constraint)
     */
    balance_t initial_balance_max = 0;

    /**
     * @brief optimal_amount_search_sections
     */
    unsigned int optimal_amount_search_sections = 1000;

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
    double max_lp_reserves_stress = 0.33;

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
    double convenience_min_threshold=-1;

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
    double convenience_max_threshold=-1;

    /**
     * @brief min_profit_target_amount
     *
     * min profit target (gain) to achieve. Absolute value on top
     * of break-event.
     *
     * @default 0 (no constraint)
     */
    balance_t min_profit_target_amount = 0;


    /**
     * @brief match limit
     *
     * limit to the amount of matching paths
     * (does not sort for best or worst. It just stops the output
     * after a certain amount of random matches)
     *
     * @default 0 (no constraint)
     */
    unsigned int match_limit=0;

    /**
     * @brief routine loop limit
     *
     * limit to the amount of examined paths
     * (does not sort for best or worst. It just stops the output
     * after a certain amount of examination loops are completed)
     *
     * @default 0 (no constraint)
     */
    unsigned int limit=0;

    void check_consistency() const;
};


} // namespace model
} // namespace bofh


