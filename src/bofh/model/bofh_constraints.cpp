#pragma once

#include "bofh_constraints.hpp"
#include "../commons/bofh_log.hpp"

namespace bofh {
namespace model {


void PathEvalutionConstraints::check_consistency() const
{
//    if (c.initial_token_wei_balance <= 0)
//    {
//        throw ContraintConsistencyError("initial_token_wei_balance must be > 0")
//    }
//    if (c.max_lp_reserves_stress > 0)
//    {
//        log_debug(" \\__ max_lp_reserves_stress set at %1%", c.max_lp_reserves_stress);
//    }
//    if (c.convenience_min_threshold >= 0)
//    {
//        log_debug(" \\__ ignore yields < convenience_min_threshold (%1%)", c.convenience_min_threshold);
//    }
//    if (c.convenience_max_threshold >= 0)
//    {
//        log_debug(" \\__ ignore yields > convenience_max_threshold (%1%)", c.convenience_max_threshold);
//    }
//    if (c.match_limit)
//    {
//        log_debug(" \\__ match limit is set at %1%", c.match_limit);
//    }
//    if (c.limit)
//    {
//        log_debug(" \\__ loop limit is set at %1%", c.limit);
//    }
}


} // namespace model
} // namespace bofh


