#include "paths.hpp"
#include "../commons/bofh_log.hpp"
#include "../model/bofh_model.hpp"
#include <boost/functional/hash.hpp>
#include <assert.h>
#include <sstream>

namespace bofh {
namespace pathfinder {

using namespace model;

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
    check_consistency(false);

    if (c.initial_token_wei_balance <= 0)
    {
        throw ContraintConsistencyError("initial_token_wei_balance must be > 0");
    }

    TheGraph::PathResult result(this);

    // walk the swap path:
    result.balances[0] = c.initial_token_wei_balance;
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

        result.balances[i+1] =
                pool->SwapExactTokensForTokens(swap->tokenSrc
                                               , result.balances[i]);
    }

    return result;
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


