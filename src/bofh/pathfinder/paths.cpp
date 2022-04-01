#include "paths.hpp"
#include "../commons/bofh_log.hpp"
#include "../model/bofh_model.hpp"
#include <boost/functional/hash.hpp>
#include <boost/algorithm/string.hpp>
#include <assert.h>
#include <sstream>

namespace bofh {
namespace pathfinder {

using namespace model;

typedef enum {
    contract_call_multiswap,
    contract_call_multiswap_deflationary,
    contract_call_multiswap_debug,
    contract_call_swapinspect,
} contract_call_t;


static const uint32_t m_path_len_method_selector(contract_call_t contract_call
                                                 , unsigned path_len)
{
    static const uint32_t map_multiswap[] = {
        0, // len=0 unsupported
        0, // len=1 unsupported
        0, // len=2 unsupported
        0x86A99D4F, // multiswap(uint256[3]) --> PATH_LENGTH=2
        0xDACDC381, // multiswap(uint256[4]) --> PATH_LENGTH=3
        0xEA704299, // multiswap(uint256[5]) --> PATH_LENGTH=4
        0xA0A3D9D9, // multiswap(uint256[6]) --> PATH_LENGTH=5
        0x0EF12BBE, // multiswap(uint256[7]) --> PATH_LENGTH=6
        0xB4859AC7, // multiswap(uint256[8]) --> PATH_LENGTH=7
        0x12558FB4, // multiswap(uint256[9]) --> PATH_LENGTH=8
    };

    static const uint32_t map_multiswap_deflationary[] = {
        0, // len=0 unsupported
        0, // len=1 unsupported
        0, // len=2 unsupported
        0x9141A63F, // multiswapd(uint256[3]) --> PATH_LENGTH=2
        0x077D03B7, // multiswapd(uint256[4]) --> PATH_LENGTH=3
        0x6B4BFA40, // multiswapd(uint256[5]) --> PATH_LENGTH=4
        0x96515533, // multiswapd(uint256[6]) --> PATH_LENGTH=5
        0xC377E1EE, // multiswapd(uint256[7]) --> PATH_LENGTH=6
        0x0885C5C5, // multiswapd(uint256[8]) --> PATH_LENGTH=7
        0xE7622831, // multiswapd(uint256[9]) --> PATH_LENGTH=8
    };

    static const uint32_t map_multiswap_debug[] = {
        0, // len=0 unsupported
        0, // len=1 unsupported
        0, // len=2 unsupported
        0xECC7C407, // multiswap_debug(uint256[3]) --> PATH_LENGTH=2
        0x06C66286, // multiswap_debug(uint256[4]) --> PATH_LENGTH=3
        0xB7D23A89, // multiswap_debug(uint256[5]) --> PATH_LENGTH=4
        0x72EFC585, // multiswap_debug(uint256[6]) --> PATH_LENGTH=5
        0x5790A9E1, // multiswap_debug(uint256[7]) --> PATH_LENGTH=6
        0x96AE42A1, // multiswap_debug(uint256[8]) --> PATH_LENGTH=7
        0x61F6DDE2, // multiswap_debug(uint256[9]) --> PATH_LENGTH=8
    };

    static const uint32_t map_swapinspect[] = {
        0, // len=0 unsupported
        0, // len=1 unsupported
        0, // len=2 unsupported
        0xADF01A12, // swapinspect(uint256[3]) --> PATH_LENGTH=2
        0x7F366121, // swapinspect(uint256[4]) --> PATH_LENGTH=3
        0xD49A80D6, // swapinspect(uint256[5]) --> PATH_LENGTH=4
        0x468D2E8F, // swapinspect(uint256[6]) --> PATH_LENGTH=5
        0x4AF2DE3A, // swapinspect(uint256[7]) --> PATH_LENGTH=6
        0x57805D6B, // swapinspect(uint256[8]) --> PATH_LENGTH=7
        0x5126BCBA, // swapinspect(uint256[9]) --> PATH_LENGTH=8
    };


    const auto map_len = sizeof(map_multiswap) / sizeof(map_multiswap[0]);
    const uint32_t *map = nullptr;
    if (path_len < map_len)
    {
        switch (contract_call)
        {
        case contract_call_multiswap:
            map = map_multiswap;
            break;
        case contract_call_multiswap_deflationary:
            map = map_multiswap_deflationary;
            break;
        case contract_call_multiswap_debug:
            map = map_multiswap_debug;
            break;
        case contract_call_swapinspect:
            map = map_swapinspect;
            break;

        }
        if (map != nullptr) return map[path_len];
    }
    return 0;
};


static bool m_raise_maybe(bool no_except, const std::string &msg)
{
    log_error("path consistency error: %1%", msg);
    if (no_except)
    {
        return false;
    }
    throw PathConsistencyError(msg);
}



static std::size_t m_calcPathHash(const Path &p)
{
    std::size_t h = 0U;
    for (unsigned i = 0; i < p.size(); ++i)
    {
        boost::hash_combine(h, p[i]->pool->address);
    }
    return h;
}

Path::Path(value_type v0
     , value_type v1
     , value_type v2)
    : base_t{v0, v1, v2}
    , type(PATH_3WAY)
    , m_hash(m_calcPathHash(*this))
{ }

Path::Path(value_type v0
     , value_type v1)
    : base_t{v0, v1}
    , type(PATH_2WAY)
    , m_hash(m_calcPathHash(*this))
{ }

Path::Path(value_type v0
     , value_type v1
     , value_type v2
     , value_type v3)
    : base_t{v0, v1, v2, v3}
    , type(PATH_4WAY)
    , m_hash(m_calcPathHash(*this))
{ }

static PathLength m_connect_swaps_from_lp_sequence(Path::base_t &out
                                                   , const model::Token *start_token
                                                   , const model::LiquidityPool *pools[]
                                                   , std::size_t size)
{
    assert(pools != nullptr);
    if (size < MIN_PATHS || size > MAX_PATHS)
    {
        m_raise_maybe(false, "bad path length");
    }
    const model::LiquidityPool *prev, *next;
    const model::Token *token = start_token;
    unsigned i;

    for (i=0; i<size; ++i)
    {
        auto lp = pools[i];
        if (lp->token0 == token)
        {
            token = lp->token1;
            out[i] = lp->swaps[0];
        }
        else if (lp->token1 == token)
        {
            token = lp->token0;
            out[i] = lp->swaps[1];
        }
        else {
            m_raise_maybe(false, "unconnected path");
        }
    }

    if (token != start_token)
    {
        m_raise_maybe(false, "non-circular");
    }

    return static_cast<PathLength>(size);
}

Path::Path(const model::Token *start_token, const model::LiquidityPool *pools[], std::size_t size)
{
    type = m_connect_swaps_from_lp_sequence(*this, start_token, pools, size);
    m_hash = m_calcPathHash(*this);
}

const Path *Path::reversed(const Path *p)
{
    const model::LiquidityPool *data[MAX_PATHS];
    unsigned size = p->size();
    for (unsigned i=0; i<size; ++i)
    {
        data[i] = (*p)[size-1-i]->pool;
    }
    return new Path(p->get(0)->tokenSrc, data, size);
}

std::string Path::print_addr() const
{
    std::stringstream ss;
    for (auto i = 0; i < size(); ++i)
    {
        auto swap = get(i);
        if (i > 0) ss << ", ";
        ss << "\"" << swap->tokenSrc->address << "\"";
    }
    ss << ", " << get(size()-1)->tokenDest->address;
    return ss.str();
}

std::string Path::get_symbols() const
{
    std::stringstream ss;
    for (auto i = 0; i < size(); ++i)
    {
        auto swap = get(i);
        if (i > 0) ss << "-";
        ss << swap->tokenSrc->symbol;
    }
    ss << "-" << get(size()-1)->tokenDest->symbol;
    return ss.str();
}


bool Path::check_consistency(bool no_except) const
{
    if (size() < 3)
    {
        return m_raise_maybe(no_except
                             , "path too short. size must be >= 3");
    }
    if (initial_token() != final_token())
    {
        return m_raise_maybe(no_except
                             , "non-circular path. "
                               "initial_token must be == final_token");
    }
    for (unsigned int i = 0; i < size()-1; ++i)
    {
        auto swap = get(i);
        auto next = get(i+1);
        if (swap->tokenDest != next->tokenSrc)
        {
            return m_raise_maybe(no_except, strfmt("path chain is broken "
                                                   "at step %1%", i));
        }
    }
    for (unsigned int i = 0; i < size(); ++i)
    {
        auto swap = get(i);
        if (swap->pool == nullptr)
        {
            return m_raise_maybe(no_except, strfmt("path chain has a missing "
                                                   "pool pointer at step %1% "
                                                   "(MODEL BUG!)", i));
        }
        if (swap->tokenSrc == swap->tokenDest)
        {
            return m_raise_maybe(no_except, strfmt("path chain has a "
                                                   "self-referencing node at "
                                                   "step %1% (MODEL BUG!)", i));
        }
        if ((swap->tokenSrc != swap->pool->token0 &&
             swap->tokenSrc != swap->pool->token1) ||
            (swap->tokenDest != swap->pool->token0 &&
             swap->tokenDest != swap->pool->token1))
        {
            return m_raise_maybe(no_except, strfmt("path node is inconsistent "
                                                    "with its pool, "
                                                   "at step %1%", i));
        }
    }
    return true;
}


bool Path::is_cross_exchange() const
{
    auto addr0 = get(0)->pool->exchange->address;
    for (unsigned i = 1; i < size(); ++i)
    {
        if (addr0 != get(i)->pool->exchange->address)
        {
            return true;
        }
    }
    return false;
}



PathResult Path::evaluate(const PathEvalutionConstraints &c
                          , unsigned prediction_snapshot_key) const
{
    TheGraph::PathResult result(this);
    try
    {
        check_consistency(false);

        if (c.initial_balance <= 0)
        {
            throw ContraintConsistencyError("initial_balance must be > 0");
        }

        balance_t current_balance = c.initial_balance;
        unsigned int i = 0;
        auto swap = get(i);
        assert(swap != nullptr);
        result.set_issued_balance_before_step(i, current_balance);
        current_balance = swap->tokenSrc->transferResult(c.initial_balance);
        result.set_measured_balance_before_step(i, current_balance);

        // walk the swap path:
        for (; i < size(); ++i)
        {
            swap = get(i);
            assert(swap != nullptr);
            auto pool = swap->pool;
            if (prediction_snapshot_key)
            {
                auto ppool = pool->get_predicted_state(prediction_snapshot_key);
                if (ppool)
                {
                    pool = ppool;
                }
            }
            assert(pool != nullptr);
            assert(swap->tokenSrc != nullptr);

            result.set_issued_balance_before_step(i, current_balance);
            current_balance = swap->tokenSrc->transferResult(c.initial_balance);
            result.set_measured_balance_before_step(i, current_balance);

            auto reserves = pool->getReserves();
            auto has_reserves = std::get<0>(reserves);
            if (!has_reserves)
            {
                auto txt = strfmt("missing reserves for pool %1% (%2%)"
                                  , pool->tag
                                  , pool->address);
                log_error("%1%", txt);
                throw std::runtime_error(txt);
            }
            result.set_pool_reserve(i, 0, std::get<1>(reserves));
            result.set_pool_reserve(i, 1, std::get<2>(reserves));

            current_balance =
                    pool->SwapExactTokensForTokens(swap->tokenSrc
                                                   , current_balance);
            result.set_issued_balance_after_step(i, current_balance);
            current_balance = swap->tokenDest->transferResult(current_balance);
            result.set_measured_balance_after_step(i, current_balance);
        }
    }
    catch (...)
    {
        result.failed = true;
    }
    return result;
}


PathResult Path::evaluate_max_yield(const PathEvalutionConstraints &c
                    , unsigned prediction_snapshot_key) const
{
    auto amount_min = c.initial_balance_min;
    auto amount_max = c.initial_balance_max;
    const auto gap_min = amount_min / 1000000;
    auto c0 = c;

    // yield_result represents a gain or a loss if a certain balance amount.
    // Since model::balance_t is basically an unsigned 256 bit integer with
    // some speed optimizations,
    // we resort to using this compound type HERE and HERE ONLY
    // in order to also express negative yields.
    struct yield_result
    {
        const bool negative;
        const model::balance_t val;
        const bool operator<(const yield_result &o) const
        {
            if (!negative && !o.negative) return val<o.val;
            if (negative && !o.negative) return true;
            if (!negative && o.negative) return false;
            return val>o.val;
        }
        operator model::balance_t() const { return negative ? 0 : val; }
    };

    // evaluate the path with a specific initial_amount. return a yield_result
    auto yield_with = [&](const auto &initial_amount) {
        c0.initial_balance = initial_amount;
        const auto plan = evaluate(c0, prediction_snapshot_key);
        if (plan.final_balance() > plan.initial_balance())
        {
            return yield_result{false, plan.final_balance() - plan.initial_balance()};
        }
        return yield_result{true, plan.initial_balance() - plan.final_balance()};
    };

    // simplest compiler-optimizable form of the find-max-of-3 problem
    auto max_of_3 = [](const auto &a, const auto &b, const auto &c) {
        if (b < a && c < a) return 0;
        if (a < b && c < b) return 1;
        return 2;
    };

    // This is the recursive bisection search call (it calls itself).
    // TODO: implement stack depth protection
    auto bisect_search = [&](const model::balance_t &min
                             , const model::balance_t &max
                             , auto subcall)
    {
        const model::balance_t mid = (min+max)/2;
        const model::balance_t gap = max - min;
        if (gap <= gap_min)
        {
            // Let's assume it makes no sense to keep refining the search
            // with resolutions finer than gap_min.
            // If we are here, we kind of found what we were looking for.
            return mid;
        }
        const auto y0 = yield_with(min); // yield with min amount
        const auto y1 = yield_with(mid); // yield with midpoint amount
        const auto y2 = yield_with(max); // yield with max amount
        const auto k = max_of_3(y0, y1, y2); // who is the winner?

        switch (k)
        {
        case 0:
            // max yield was found with min amount.
            // Assume there is an even better amount in the
            // range [min, midpoint] and attempt a search there
            return subcall(min, mid, subcall);
        case 2:
            // max yield was found with max amount
            // Assume there is an even better amount in the
            // range [midpoint, max] and attempt a search there
            return subcall(mid, max, subcall);
        default:
            // max yield was found with midpoint amount
            // It's a little more complex:
            // - find the best yield in the bracket [min, midpoint] --> nmin
            // - find the best yield in the bracket [midpoint, max] --> nmax
            // - return the best-yielding of the two
            const auto nmin = subcall(min, mid, subcall);
            const auto nmax = subcall(mid, max, subcall);
            return yield_with(nmin) < yield_with(nmax) ? nmax : nmin;
        }
    };

    auto ideal = bisect_search(amount_min, amount_max, bisect_search);
    c0.initial_balance = ideal;
    return evaluate(c0, prediction_snapshot_key);

}


std::string PathResult::infos() const
{
    std::stringstream ss;
    ss << path->size() << "-way path is " << path->get_symbols() << std::endl;
    ss << "  \\_ address vector is  " << path->print_addr() << std::endl;
    ss << "  \\_ initial balance is " << initial_balance() << std::endl;
    ss << "  \\_ final balance is   " << final_balance() << std::endl;
    ss << "  \\_ yield is           " << yield_ratio() << std::endl;
    return ss.str();
}



model::balance_t PathResult::initial_balance() const
{
    return issued_balance_before_step(0);
}

model::balance_t PathResult::final_balance() const
{
    return measured_balance_after_step(path->size()-1);
}

void PathResult::set_initial_balance(const model::balance_t &val)
{
    set_issued_balance_before_step(0, val);
}

void PathResult::set_final_balance(const model::balance_t &val)
{
    set_measured_balance_after_step(path->size()-1, val);
}

model::balance_t PathResult::issued_balance_before_step(unsigned idx) const
{
    assert(idx < MAX_PATHS);
    return m_balances_issued[idx];
}

model::balance_t PathResult::issued_balance_after_step(unsigned idx) const
{
    assert(idx < MAX_PATHS);
    return m_balances_issued[idx+1];
}

model::balance_t PathResult::measured_balance_before_step(unsigned idx) const
{
    assert(idx < MAX_PATHS);
    return m_balances_measured[idx];
}

model::balance_t PathResult::measured_balance_after_step(unsigned idx) const
{
    assert(idx < MAX_PATHS);
    return m_balances_measured[idx+1];
}

void PathResult::set_issued_balance_before_step(unsigned idx, const model::balance_t &val)
{
    assert(idx < MAX_PATHS);
    m_balances_issued[idx] = val;
}

void PathResult::set_issued_balance_after_step(unsigned idx, const model::balance_t &val)
{
    assert(idx < MAX_PATHS);
    m_balances_issued[idx+1] = val;
}

void PathResult::set_measured_balance_before_step(unsigned idx, const model::balance_t &val)
{
    assert(idx < MAX_PATHS);
    m_balances_measured[idx] = val;
}

void PathResult::set_measured_balance_after_step(unsigned idx, const model::balance_t &val)
{
    assert(idx < MAX_PATHS);
    m_balances_measured[idx+1] = val;
}


const Token *PathResult::initial_token() const { return path->initial_token(); }
const Token *PathResult::final_token() const { return path->final_token(); }
const Token *PathResult::token_before_step(unsigned idx) const { return path->token_before_step(idx); }
const Token *PathResult::token_after_step(unsigned idx) const { return path->token_after_step(idx); }
double PathResult::yield_ratio() const
{
    auto init = initial_balance().convert_to<double>();
    auto fini = final_balance().convert_to<double>();
    return fini/init;
}

std::size_t PathResult::id() const { return path->id(); }

balance_t PathResult::pool_reserve(unsigned idx, unsigned reserve0_or_1) const
{
    if (pool_reserves == nullptr)
    {
        return 0;
    }
    const auto k = (idx*2) + (reserve0_or_1 ? 1 : 0);
    assert(k < pool_reserves->size());
    return (*pool_reserves)[k];
}

void PathResult::set_pool_reserve(unsigned idx, unsigned reserve0_or_1, const model::balance_t &val)
{
    if (pool_reserves == nullptr)
    {
        pool_reserves.reset(new pool_reserves_t);
    }
    const auto k = (idx*2) + (reserve0_or_1 ? 1 : 0);
    assert(k < pool_reserves->size());
    (*pool_reserves)[k] = val;
}

model::balance_t PathResult::pool_token_reserve(unsigned idx, const model::Token *t) const
{
    if (pool_reserves == nullptr)
    {
        return 0;
    }

    assert(idx < path->size());
    auto swap = path->get(idx);

    assert(t == swap->pool->token0 || t == swap->pool->token1);

    if (t == swap->pool->token0)
    {
        return pool_reserve(idx, 0);
    }
    return pool_reserve(idx, 1);
}

void PathResult::set_pool_token_reserve(unsigned idx, const model::Token *t, const model::balance_t &val)
{
    if (pool_reserves == nullptr)
    {
        pool_reserves.reset(new pool_reserves_t);
    }

    assert(idx < path->size());
    auto swap = path->get(idx);

    assert(t == swap->pool->token0 || t == swap->pool->token1);

    if (t == swap->pool->token0)
    {
        set_pool_reserve(idx, 0, val);
    }
    set_pool_reserve(idx, 1, val);
}

std::string PathResult::get_calldata(bool deflationary) const
{
    enum { word_size = 256 };

    std::stringstream ss;
    ss
            << std::hex
            << std::noshowbase
            << std::uppercase
            << std::setfill('0');

    auto selector = m_path_len_method_selector(deflationary
                                               ? contract_call_multiswap_deflationary
                                               : contract_call_multiswap
                                               , path->size()+1);
    if (!selector)
    {
        throw std::runtime_error(strfmt("unsupported path length: %1%", path->size()));
    }
    // add selector header
    ss      << "0x"
            << std::setw(sizeof(selector)*2)
            << selector;

    for (unsigned i = 0; i < path->size(); ++i)
    {
        auto pool = path->get(i)->pool;

        // add fees word
        ss  << std::setw((word_size - address_t::size_bits)/4)
            << pool->feesPPM();

        // add pool address
        ss  << std::setw(address_t::nibs)
            << reinterpret_cast<const address_t::base_type&>(pool->address);
    }
    // add expectedAmount, initialAmount
    ss << std::setw(word_size/8);
    ss << final_balance();
    ss << std::setw(word_size/8);
    ss << initial_balance();

    auto calldata = ss.str();
    assert(calldata.size() ==
           std::strlen("0x")
           + sizeof(selector)*2
           + (path->size() * word_size) / 4
           + (word_size) / 4);
    return calldata;
}

std::string PathResult::get_description() const
{
    std::stringstream ss;
    auto amount_hr = [](auto weis, auto token)
    {
        return strfmt("%0.4f", token->fromWei(weis));
    };

    auto fees = [](const auto &measured, const auto &issued)
    {
        if (issued == 0)
        {
            return strfmt("unknown");
        }
        const auto a = measured.template convert_to<double>();
        const auto b = issued.  template convert_to<double>();
        const auto fee = (1-(a/b))*100;
        return strfmt("%0.04f%%", fee);
    };

    ss << "Description of financial attack having path hash " << id() << std::endl;
    if (failed)
    {
        ss << "Internal consistency or logic error during evaluation of path" << id() << std::endl;
        return ss.str();
    }

    ss << "   \\___ attack estimation had "
                 << amount_hr(initial_balance(), initial_token()) << " "
                 << initial_token()->symbol << " of input balance "
                 << "(" << initial_balance() << " weis)" << std::endl;
    ss << "   \\___ estimated yield was "
                 << amount_hr(final_balance(), final_token()) << " "
                 << final_token()->symbol << " balance "
                 << "(" << final_balance() << " weis)" << std::endl;
    ss << "   \\___ detail of the path traversal:" << std::endl;

    const void *exc = nullptr;
    for (unsigned i = 0; i < path->size(); ++i)
    {
        auto swap = path->get(i);
        auto pool = swap->pool;
        auto exc_txt = exc == pool->exchange
                ? strfmt("stays on exchange %1%", pool->exchange->name)
                : strfmt("is sent to exchange %1%", pool->exchange->name);
        exc = pool->exchange;
        auto token_in = token_before_step(i);
        auto token_out = token_after_step(i);
        auto amount_in = issued_balance_before_step(i);
        auto amount_out = issued_balance_after_step(i);
        auto reserve_in = pool_token_reserve(i, token_in);
        auto reserve_out = pool_token_reserve(i, token_out);

        ss << "       \\___ amount "<<exc_txt<<" via pool "<<pool->get_name()
                    <<" ("<<pool->address<<")"<< std::endl;

        ss << "       |     \\___ this pool stores:"<< std::endl;
        ss << "       |     |     \\___ reserveIn is ~= "
                    << amount_hr(reserve_in, token_in)
                    << " " << token_in->symbol << std::endl;
        ss << "       |     |         \\___ or ~= " << reserve_in << " of token "
                                                    << token_in->address << std::endl;

        ss << "       |     |     \\___ reserveOut is ~= "
                    << amount_hr(reserve_out, token_out)
                    << " " << token_out->symbol << std::endl;
        ss << "       |     |         \\___ or ~= " << reserve_out << " of token "
                                                    << token_out->address << std::endl;


        ss << "       |     \\___ the swaps sends in "
                    << amount_hr(amount_in, token_in) << " ("<<amount_in<<" weis)"
                    << " of " << token_in->symbol << std::endl;
        auto meas_in = measured_balance_before_step(i);
        if (meas_in != amount_in)
        {
            ss << "       |     \\       \\___ " << fees(meas_in, amount_in)
               << " of funds are burned in transfer. Effective amount is "
               << amount_hr(meas_in, token_in) << " ("<<meas_in<<" weis)";
        }
        ss << "       |     \\___ and exchanges to "
                    << amount_hr(amount_out, token_out) << " ("<<amount_out<<" weis)"
                    << " of " << token_out->symbol << std::endl;
        auto meas_out = measured_balance_before_step(i);
        if (meas_out != amount_out)
        {
            ss << "       |     \\       \\___ " << fees(meas_out, amount_out)
               << " of funds are burned in transfer. Effective amount is "
               << amount_hr(meas_out, token_out) << " ("<<meas_out<<" weis)";
        }
        auto exchange_rate = amount_out.convert_to<double>() / amount_in.convert_to<double>();
        ss << strfmt("       |           \\___ effective rate of change is %0.5f %s"
                                            , exchange_rate
                                            , pool->get_name().c_str())
                    << std::endl;
        ss << strfmt("       |           \\___ this includes a %0.4f%% swap fee"
                     , (pool->feesPPM()/1000000.0)*100.0) << std::endl;
    }
    ss << "       \\___ final balance is "
          << amount_hr(final_balance(), final_token())
          << " of " << final_token()->symbol
          <<" (token "<< final_token()->address << ")" << std::endl;

    auto yieldPercent = (yield_ratio()-1)*100;
    if (final_balance() > initial_balance())
    {
        auto gap = final_balance() - initial_balance();
        auto hr_g = amount_hr(gap, final_token());
        auto gain = strfmt("net gain of %1% %2% (+%3% weis)"
                           , hr_g
                           , final_token()->symbol
                           , gap);
        ss << "           \\___ this results in a " << gain << std::endl;
    }
    else {
        auto gap = initial_balance() - final_balance();
        auto hr_g = amount_hr(gap, final_token());
        auto gain = strfmt("net loss of %1% %2% (+%3% weis)"
                           , hr_g
                           , final_token()->symbol
                           , gap);
        ss << "           \\___ this results in a " << gain << std::endl;
    }
    ss << strfmt("                 \\___ which is a %0.4f%% net yield", yieldPercent) << std::endl;
    return ss.str();
}


std::ostream& operator<< (std::ostream& stream, const Path& o)
{
    stream << o.get_symbols();
    return stream;
}

std::ostream& operator<< (std::ostream& stream, const PathResult& o)
{
    stream << o.infos();
    return stream;
}

const Token *Path::initial_token() const { return get(0)->tokenSrc; }
const Token *Path::final_token() const { return get(size()-1)->tokenDest; }
const Token *Path::token_before_step(unsigned idx) const { return get(idx)->tokenSrc; }
const Token *Path::token_after_step(unsigned idx) const { return get(idx)->tokenDest; }


} // namespace pathfinder
} // namespace bofh


