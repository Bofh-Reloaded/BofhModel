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

static const uint32_t m_path_len_method_selector(unsigned path_len
                                                 , bool deflationary)
{
    static const uint32_t map_direct[] = {
        0, // len=0 unsupported
        0, // len=1 unsupported
        0, // len=2 unsupported
        0x86a99d4f, // LEN = 3
        0xdacdc381, // LEN = 4
        0xea704299, // LEN = 5
        0xa0a3d9d9, // LEN = 6
        0x0ef12bbe, // LEN = 7
        0xb4859ac7, // LEN = 8
        0x12558fb4, // LEN = 9
    };
    static const uint32_t map_deflationary[] = {
        0, // len=0 unsupported
        0, // len=1 unsupported
        0, // len=2 unsupported
        0x9141a63f, // LEN = 9
        0x077d03b7, // LEN = 8
        0x6b4bfa40, // LEN = 7
        0x96515533, // LEN = 6
        0xc377e1ee, // LEN = 5
        0x0885c5c5, // LEN = 4
        0xe7622831, // LEN = 3
    };
    const auto map_len = sizeof(map_direct) / sizeof(map_direct[0]);
    if (path_len < map_len)
    {
        return (deflationary ? map_deflationary : map_direct)[path_len];
    }
    return 0;
};

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
     , value_type v1
     , value_type v2
     , value_type v3)
    : base_t{v0, v1, v2, v3}
    , type(PATH_4WAY)
    , m_hash(m_calcPathHash(*this))
{ }


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

static bool m_raise_maybe(bool no_except, const std::string &msg)
{
    log_error("path consistency error: %1%", msg);
    if (no_except)
    {
        return false;
    }
    throw PathConsistencyError(msg);
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




PathResult Path::evaluate(const PathEvalutionConstraints &c
                          , bool observe_predicted_state) const
{
    TheGraph::PathResult result(this);
    try
    {
        check_consistency(false);

        if (c.initial_balance <= 0)
        {
            throw ContraintConsistencyError("initial_balance must be > 0");
        }


        // walk the swap path:
        result.balances[0] = initial_token()->transferResult(c.initial_balance);
        for (unsigned int i = 0; i < size(); ++i)
        {
            // excuse the following assert soup. They are only intended to
            // early catch of inconsistencies in debug builds. None is functional.
            auto swap = get(i);
            assert(swap != nullptr);
            auto pool = swap->pool;
            if (observe_predicted_state)
            {
                auto ppool = pool->get_predicted_state();
                if (ppool)
                {
                    pool = ppool;
                }
            }
            assert(pool != nullptr);
            assert(swap->tokenSrc != nullptr);

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
            const auto output_amount =
                    pool->SwapExactTokensForTokens(swap->tokenSrc
                                                   , result.balances[i]);
            result.balances[i+1] = swap->tokenDest->transferResult(output_amount);
        }
    }
    catch (...)
    {
        result.failed = true;
    }
    return result;
}

//static model::balance_t yield_with(const Path &path
//                                   , const PathEvalutionConstraints &c
//                                   , const auto &initial_amount
//                                   , bool observe_predicted_state)
//{
//    c.initial_balance = initial_amount;
//    auto res = path.evaluate(c, observe_predicted_state);
//    return res.final_balance().convert_to<double>()
//         - res.initial_balance().convert_to<double>();
//};


//model::balance_t bisect_search(const Path &path
//                               , const model::balance_t &min
//                               , const model::balance_t &max
//                               , const model::balance_t &gap_min)
//{
//    const auto mid = (min+max)/2;
//    const auto gap = max - min;
//    if (gap <= gap_min)
//    {
//        return mid;
//    }
//    const auto y0 = yield_with(min);
//    const auto y1 = yield_with(mid);
//    const auto y2 = yield_with(max);
//    const auto k = max_of_3(y0, y1, y2);
//    switch (k)
//    {
//    case 0: // max is at yield_with(min)
//        return cb(y0, y1, cb);
//    case 2: // max is at yield_with(max)
//        return cb(y1, y2, cb);
//    default:
//        const auto nmin = cb(y0, y1, cb);
//        const auto nmax = cb(y1, y2, cb);
//        return cb(nmin, nmax, cb);
//    }
//};


PathResult Path::evaluate2(const PathEvalutionConstraints &c
                    , bool observe_predicted_state) const
{
/*

amount_min
amount_max
amount_window = amount_max - amount_min

step = amount_window * 0.01
amount = amount_min

y0 = yield_with(amount)
if y0 < 0:
    return false // no go

step1 = amount+step
y1 = yield_with(step1)

if y0 > y1:
    return y0 // probably found

// case y0 < y1: increasing input amount also increases final yield.
// hypotesis: there is room for improvement

// let's recalc yield with twice the step
step2 *= step1 + step*2
y2 = yield_with(step2)

if (y1 > y2):
    // overshoot. Max is somewhere in [step1, step2]
    return bisect_search(step1, step2)

// hypotesis: there is room for improvement

// let's recalc yield with twice the step
step3 *= step2 + step*4
y3 = yield_with(step2)

if (y2 > y3):
    // overshoot. Max is somewhere in [step1, step2]
    return bisect_search(step2, step3)

--------------

def max_of_3(a, b, c):...

def bisect_search(min, max, gap_min):
    mid = (min+max)/2
    gap = max - min;
    if gap < gap_min:
        return mid
    ym = yield_with(min)
    yM = yield_with(max)
    yc = yield_with(mid)

    k = max_of_3(ym, yc, yM)
    switch (k)
    {
    case 0: // max is at yield_with(min)
        return bisect_search(ym, yc);
        break;
    case 2: // max is at yield_with(max)
        return bisect_search(yc, yM);
        break;
    case 1: // max is at yield_with(mid)
        min = bisect_search(ym, yc);
        max = bisect_search(yc, yM);
        return bisect_search(min, max);
        break;
    }
*/
    auto amount_min = c.initial_balance_min;
    auto amount_max = c.initial_balance_max;
    const auto gap_min = amount_min / 1000000;
    auto c0 = c;

    struct yield_result {
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
    auto yield_with = [&](const auto &initial_amount) {
        c0.initial_balance = initial_amount;
        const auto plan = evaluate(c0, observe_predicted_state);
        if (plan.final_balance() > plan.initial_balance())
        {
            return yield_result{false, plan.final_balance() - plan.initial_balance()};
        }
        return yield_result{true, plan.initial_balance() - plan.final_balance()};
    };

    auto max_of_3 = [](const auto &a, const auto &b, const auto &c) {
        if (b < a && c < a) return 0;
        if (a < b && c < b) return 1;
        return 2;
    };

    auto bisect_search = [&](const model::balance_t &min, const model::balance_t &max, auto cb)
    {
        const model::balance_t mid = (min+max)/2;
        const model::balance_t gap = max - min;
        if (gap <= gap_min)
        {
            return mid;
        }
        const auto y0 = yield_with(min);
        const auto y1 = yield_with(mid);
        const auto y2 = yield_with(max);
        const auto k = max_of_3(y0, y1, y2);
        switch (k)
        {
        case 0: // max is at yield_with(min)
            return cb(min, mid, cb);
        case 2: // max is at yield_with(max)
            return cb(mid, max, cb);
        default:
            const auto nmin = cb(min, mid, cb);
            const auto nmax = cb(mid, max, cb);
            return cb(nmin, nmax, cb);
        }
    };

    auto ideal = bisect_search(amount_min, amount_max, bisect_search);
    c0.initial_balance = ideal;
    return evaluate(c0, observe_predicted_state);


//    if (!amount_min) amount_min = c.initial_balance;
//    if (!amount_max) amount_max = c.initial_balance;
//    auto step = (amount_max - amount_min) / c.optimal_amount_search_sections;
//    auto c0 = c;
//    auto c1 = c;

//    auto gain = [](const auto &res) {
//        return res.final_balance().template convert_to<double>()
//                - res.initial_balance().template convert_to<double>();
//    };

//    c0.initial_balance = amount_min;
//    auto y0 = evaluate(c0, observe_predicted_state);
//    auto gy0 = gain(y0);

//    if (gy0 < 0)
//    {
//        log_info("with %1% y0 is already in loss. bail out :(", c0.initial_balance);
//        y0.failed = true;
//        return y0;
//    }

//    log_info("with %1% y0 is %2%", c0.initial_balance, gy0);
//    for (;;)
//    {
//        c1.initial_balance = c0.initial_balance+step;
//        auto y1 = evaluate(c1, observe_predicted_state);
//        auto gy1 = gain(y1);
//        log_info("with %1% y1 is %2%", c1.initial_balance, gy1);

//        if (gy0 > gy1 || c0.initial_balance >= amount_max)
//        {
//            break;
//        }

//        y0 = y1;
//        c0 = c1;
//    }

//    return y0;
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

balance_t PathResult::initial_balance() const { return balances[0]; }
balance_t PathResult::final_balance() const { return balances[path->size()]; }
balance_t PathResult::balance_before_step(unsigned idx) const { return balances[idx]; }
balance_t PathResult::balance_after_step(unsigned idx) const { return balances[idx+1]; }
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

std::string PathResult::get_calldata(bool deflationary) const
{
    enum { word_size = 256 };

    std::stringstream ss;
    ss
            << std::hex
            << std::noshowbase
            << std::uppercase
            << std::setfill('0');

    auto selector = m_path_len_method_selector(path->size()+1, deflationary);
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
    ss << expectedAmount;
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
        auto amount_in = balance_before_step(i);
        auto amount_out = balance_after_step(i);
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
        ss << "       |     \\___ and exchanges to "
                    << amount_hr(amount_out, token_out) << " ("<<amount_out<<" weis)"
                    << " of " << token_out->symbol << std::endl;
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


