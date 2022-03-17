#include "bofh_model.hpp"
#include "../commons/bofh_log.hpp"
#include "bofh_entity_idx.hpp"
#include "../pathfinder/swaps_idx.hpp"
#include "../pathfinder/paths.hpp"
#include "../pathfinder/finder_3way.hpp"
#if !defined(NOPYTHON) || !NOPYTHON
#include <boost/python/extract.hpp>
#include <boost/python/str.hpp>
#include <boost/python/import.hpp>
#include <boost/stacktrace.hpp>
#endif
#include <sstream>
#include <exception>
#include <assert.h>


namespace bofh {
namespace model {

using namespace idx;
using namespace pathfinder::idx;

#if !defined(NOPYTHON) || !NOPYTHON
static std::string m_parse_python_exception()
{
    namespace py = boost::python;

    PyObject *type_ptr = NULL, *value_ptr = NULL, *traceback_ptr = NULL;
    // Fetch the exception info from the Python C API
    PyErr_Fetch(&type_ptr, &value_ptr, &traceback_ptr);

    // Fallback error
    std::string ret("Unfetchable Python error");
    // If the fetch got a type pointer, parse the type into the exception string
    if(type_ptr != NULL){
        py::handle<> h_type(type_ptr);
        py::str type_pstr(h_type);
        // Extract the string from the boost::python object
        py::extract<std::string> e_type_pstr(type_pstr);
        // If a valid string extraction is available, use it
        //  otherwise use fallback
        if(e_type_pstr.check())
            ret = e_type_pstr();
        else
            ret = "Unknown exception type";
    }
    // Do the same for the exception value (the stringification of the exception)
    if(value_ptr != NULL){
        py::handle<> h_val(value_ptr);
        py::str a(h_val);
        py::extract<std::string> returned(a);
        if(returned.check())
            ret +=  ": " + returned();
        else
            ret += std::string(": Unparseable Python error: ");
    }
    // Parse lines from the traceback using the Python traceback module
    if(traceback_ptr != NULL){
        py::handle<> h_tb(traceback_ptr);
        // Load the traceback module and the format_tb function
        py::object tb(py::import("traceback"));
        py::object fmt_tb(tb.attr("format_tb"));
        // Call format_tb to get a list of traceback strings
        py::object tb_list(fmt_tb(h_tb));
        // Join the traceback strings into a single string
        py::object tb_str(py::str("\n").join(tb_list));
        // Extract the string, check the extraction, and fallback in necessary
        py::extract<std::string> returned(tb_str);
        if(returned.check())
            ret += ": " + returned();
        else
            ret += std::string(": Unparseable Python traceback");
    }
    return ret;
}


template<typename ResType, typename T>
static ResType m_call_cb(const boost::python::object &cb, const T &arg)
{
    if (cb) try
    {
        return boost::python::extract<ResType>(cb(arg));
    }
    catch(boost::python::error_already_set const &){
        std::cout << "Error in Python: " << m_parse_python_exception() << std::endl;
    }
    return nullptr;
}
#endif


struct bad_argument: public std::runtime_error
{
    using std::runtime_error::runtime_error ;
};
#define check_not_null_arg(name) if (name == nullptr) throw bad_argument("can't be null: " #name);

int OperableSwap::feesPPM() const
{
    return pool->feesPPM();
}

bool OperableSwap::hasFees() const
{
    return pool->hasFees();
}

Token::Token(datatag_t tag_
      , const address_t &address_
      , TheGraph *parent_
      , const string &name_
      , const std::string &symbol_
      , unsigned int decimals_
      , bool is_stable_
      )
    : Entity(TYPE_TOKEN, tag_, address_, parent_)
    , name(name_)
    , is_stable(is_stable_)
    , symbol(symbol_)
    , decimals(decimals_)
{ }

double Token::fromWei(const balance_t &b) const
{
    return b.convert_to<double>() / std::pow(10, decimals);
}

balance_t Token::toWei(double amount) const
{
    return balance_t(amount * std::pow(10, decimals));
}

int Token::feesPPM() const
{
    return m_feesPPM;
}

bool Token::hasFees() const
{
    return m_hasFees;
}

void Token::set_feesPPM(int val)
{
    m_feesPPM = val;
    m_hasFees = true;
}

balance_t Token::transferResult(const balance_t &amount) const
{
    if (m_feesPPM == 0)
    {
        return amount;
    }
    return (amount * (1000000-m_feesPPM))/1000000;
}



Exchange::Exchange(datatag_t tag_
                   , const address_t &address_
                   , TheGraph *parent_
                   , const string &name_, int feesPPM_)
    : Entity(TYPE_EXCHANGE, tag_, address_, parent_)
    , name(name_)
    , estimator(new amm::EstimatorWithProportionalFees)
    , m_feesPPM(feesPPM_)
{}

const balance_t LiquidityPool::getReserve(const Token *token) const noexcept
{
    auto res = getReserves();
    assert(token == token1 || token == token0);
    return token == token0 ? std::get<1>(res) : std::get<2>(res);
}

LiquidityPool::reserves_ref LiquidityPool::getReserves() const noexcept
{
    if (!reserves_set)
    {
#if !defined(NOPYTHON) || !NOPYTHON
        auto &cb = parent->m_fetch_lp_reserves_tag_cb;
        if (cb) try
        {
            cb(boost::python::ptr(this));
        }
        catch(boost::python::error_already_set const &){
            std::cout << "Error in Python: " << m_parse_python_exception() << std::endl;
        }
#endif
    }

    return reserves_ref{reserves_set, reserve0, reserve1};
}


std::string LiquidityPool::get_name() const
{
    return strfmt("%1%-%2%", token0->symbol, token1->symbol);
}


void LiquidityPool::setReserves(const balance_t &reserve0_, const balance_t &reserve1_)
{
    reserves_set = true;
    reserve0 = reserve0_;
    reserve1 = reserve1_;
}

balance_t LiquidityPool::SwapTokensForExactTokens(const Token *wantedToken, const balance_t &wantedAmount) const
{
    assert(exchange != nullptr);
    assert(exchange->estimator != nullptr);
    return exchange->estimator->SwapTokensForExactTokens(this, wantedToken, wantedAmount);
}

balance_t LiquidityPool::SwapExactTokensForTokens(const Token *tokenSent, const balance_t &sentAmount) const
{
    assert(exchange != nullptr);
    assert(exchange->estimator != nullptr);
    return exchange->estimator->SwapExactTokensForTokens(this, tokenSent, sentAmount);
}

int LiquidityPool::feesPPM() const
{
    return m_hasFees
            ? m_feesPPM
            : exchange->feesPPM();
}

bool LiquidityPool::hasFees() const
{
    return m_hasFees || exchange->hasFees();
}

void LiquidityPool::set_feesPPM(int val)
{
    m_feesPPM = val;
    m_hasFees = true;
}


const LiquidityPool *LiquidityPool::get_predicted_state(unsigned key) const
{
    auto i = m_predicted_state.find(key);
    if (i == m_predicted_state.end())
    {
        return this;
    }
    return &i->second;
}

void LiquidityPool::set_predicted_reserves(unsigned key
                            , const balance_t &reserve0
                            , const balance_t &reserve1)
{
    auto i = m_predicted_state.find(key);
    if (i == m_predicted_state.end())
    {
        auto n = m_predicted_state.emplace(std::piecewise_construct
                                           , std::forward_as_tuple(key)
                                           , std::forward_as_tuple(tag
                                                                   , address
                                                                   , parent
                                                                   , exchange
                                                                   , token0
                                                                   , token1));
        i = n.first;
        parent->predicted_snapshot_idx.emplace(key, this);
    }
    i->second.reserve0 = reserve0;
    i->second.reserve1 = reserve1;
}

void LiquidityPool::leave_predicted_state(unsigned key)
{
    m_predicted_state.erase(key);
}

TheGraph::TheGraph()
    : entity_index(new EntityIndex)
    , swap_index(new SwapIndex)
    , paths_index(new SwapPathsIndex)
{
    log_trace("TheGraph created at 0x%p", this);
};

namespace {
// FIY: an unnamed namespace makes its content private to this code unit

/**
 * Use this to check the outcome of any cointainer emplace()
 * @return true if the emplace() was rejected and an existing
 *         duplicate was found in the container
 */
auto already_exists = [](const auto &i) { return !i.second; };

}; // unnamed namespace


const Exchange *TheGraph::add_exchange(datatag_t tag
                                       , const char *address
                                       , const string &name
                                       , int feesPPM)
{
    lock_guard_t lock_guard(m_update_mutex);
    auto ptr = std::make_unique<Exchange>(tag, address, this, name, feesPPM);
    auto item = entity_index->emplace(ptr.get());
    if (already_exists(item))
    {
        return nullptr;
    }
    exchanges_ctr++;
    return reinterpret_cast<Exchange*>(ptr.release());
}


const Exchange *TheGraph::lookup_exchange(datatag_t tag)
{
    return lookup_exchange(tag, true);
}

const Exchange *TheGraph::lookup_exchange(datatag_t tag, bool fetch_if_missing)
{
    const Exchange *res = entity_index->lookup<Exchange, TYPE_EXCHANGE>(tag);

    if (fetch_if_missing)
    {
#if !defined(NOPYTHON) || !NOPYTHON
        auto &cb = m_fetch_exchange_tag_cb;

        if (res == nullptr && cb)
        {
            res = m_call_cb<const Exchange *>(cb, tag);
            assert(res == nullptr || res->tag == tag);
        }

        if (res == nullptr)
        {
            log_error("lookup_exchange(%1%) failed", tag);
            static bool alerted = false;
            if (!cb && !alerted)
            {
                alerted = true;
                log_warning("TheGraph needs a way to fetch Exchange objects. "
                            "Please post a callback with set_fetch_exchange_tag_cb()");
            }
        }
#endif
    }

    return res;
}

bool TheGraph::has_exchange(datatag_t tag) const
{
    return entity_index->lookup<Exchange, TYPE_EXCHANGE>(tag) != nullptr;
}

bool TheGraph::has_exchange(const char *address) const
{
    return entity_index->lookup<Exchange, TYPE_EXCHANGE>(address) != nullptr;
}

bool TheGraph::has_token(datatag_t tag) const
{
    return entity_index->lookup<Token, TYPE_TOKEN>(tag) != nullptr;
}

bool TheGraph::has_token(const char *address) const
{
    return entity_index->lookup<Token, TYPE_TOKEN>(address) != nullptr;
}

bool TheGraph::has_lp(datatag_t tag) const
{
    return entity_index->lookup<LiquidityPool, TYPE_LP>(tag) != nullptr;
}

bool TheGraph::has_lp(const char *address) const
{
    return entity_index->lookup<LiquidityPool, TYPE_LP>(address) != nullptr;
}



const Token *TheGraph::add_token(datatag_t tag
                                 , const char *address
                                 , const char *name
                                 , const char *symbol
                                 , unsigned int decimals
                                 , bool is_stablecoin
                                 , bool hasFees
                                 , int feesPPM)
{
    lock_guard_t lock_guard(m_update_mutex);
    auto ptr = std::make_unique<Token>(tag
                                       , address
                                       , this
                                       , name
                                       , symbol
                                       , decimals
                                       , is_stablecoin);
    if (hasFees) ptr->set_feesPPM(feesPPM);
    auto item = entity_index->emplace(ptr.get());
    if (already_exists(item))
    {
        return nullptr;
    }
    tokens_ctr++;
    return reinterpret_cast<Token*>(ptr.release());
}

const Token *TheGraph::lookup_token(const char *address)
{
    return lookup_token(address, true);
}

const Token *TheGraph::lookup_token(const char *address, bool fetch_if_missing)
{
    auto res = entity_index->lookup<Token, TYPE_TOKEN>(address);

    if (fetch_if_missing)
    {
#if !defined(NOPYTHON) || !NOPYTHON
        auto &cb = m_fetch_token_addr_cb;

        if (res == nullptr && cb)
        {
            res = m_call_cb<const Token *>(cb, address);
            assert(res == nullptr || res->address == address_t(address));
        }

        if (res == nullptr)
        {
            log_error("lookup_token(%1%) failed", address);
            static bool alerted = false;
            if (!cb && !alerted)
            {
                alerted = true;
                log_warning("TheGraph needs a way to fetch Token objects. "
                            "Please post a callback with set_fetch_token_addr_cb()");
            }
        }
#endif
    }

    return res;
}


const Token *TheGraph::lookup_token(datatag_t tag)
{
    return lookup_token(tag, true);
}

const Token *TheGraph::lookup_token(datatag_t tag, bool fetch_if_missing)
{
    auto res = entity_index->lookup<Token, TYPE_TOKEN>(tag);

    if (fetch_if_missing)
    {
#if !defined(NOPYTHON) || !NOPYTHON
        auto &cb = m_fetch_token_tag_cb;

        if (res == nullptr && cb)
        {
            res = m_call_cb<const Token *>(cb, tag);
            assert(res == nullptr || res->tag == tag);
        }

        if (res == nullptr)
        {
            log_error("lookup_token(%1%) failed", tag);
            static bool alerted = false;
            if (!cb && !alerted)
            {
                alerted = true;
                log_warning("TheGraph needs a way to fetch Token objects. "
                            "Please post a callback with set_fetch_token_tag_cb()");
            }
        }
#endif
    }

    return res;
}


const LiquidityPool *TheGraph::add_lp_ll(datatag_t tag
                                         , const char *address
                                         , const Exchange* exchange
                                         , Token* token0
                                         , Token* token1
                                         , bool hasFees
                                         , int feesPPM)
{
    check_not_null_arg(exchange);
    check_not_null_arg(token0);
    check_not_null_arg(token1);
    auto ptr = std::make_unique<LiquidityPool>(tag
                                               , address
                                               , this
                                               , exchange
                                               , token0
                                               , token1);
    if (hasFees) ptr->set_feesPPM(feesPPM);
    lock_guard_t lock_guard(m_update_mutex);

    auto item = entity_index->emplace(ptr.get());
    if (already_exists(item))
    {
        return nullptr;
    }
    auto lp = reinterpret_cast<LiquidityPool*>(ptr.release());
    pools_ctr++;
    // create OperableSwap objects
    lp->swaps[0] = OperableSwap::make(token0, token1, lp);
    lp->swaps[1] = OperableSwap::make(token1, token0, lp);
    for (auto os: lp->swaps)
    {
        swap_index->emplace(os);
    }

    return lp;
}

const LiquidityPool *TheGraph::add_lp(datatag_t tag
                                      , const char *address
                                      , datatag_t exchange_
                                      , datatag_t token0_
                                      , datatag_t token1_
                                      , bool hasFees
                                      , int feesPPM)
{
    auto exchange = lookup_exchange(exchange_);
    auto token0 = const_cast<Token*>(lookup_token(token0_));
    auto token1 = const_cast<Token*>(lookup_token(token1_));
    if (exchange == nullptr || token0 == nullptr || token1 == nullptr)
    {
        return nullptr;
    }
    return add_lp_ll(tag, address, exchange, token0, token1, hasFees, feesPPM);
}


const LiquidityPool *TheGraph::lookup_lp(const address_t &address)
{
    return lookup_lp(address, true);
}

const LiquidityPool *TheGraph::lookup_lp(const char *address)
{
    return lookup_lp(address, true);
}

const LiquidityPool *TheGraph::lookup_lp(const char *address, bool fetch_if_missing)
{
    return lookup_lp(address_t(address), fetch_if_missing);
}

const LiquidityPool *TheGraph::lookup_lp(const address_t &address, bool fetch_if_missing)
{
    auto res = entity_index->lookup<LiquidityPool, TYPE_LP>(address);

    if (fetch_if_missing)
    {
#if !defined(NOPYTHON) || !NOPYTHON
        auto &cb = m_fetch_lp_addr_cb;

        if (res == nullptr && cb)
        {
            res = m_call_cb<const LiquidityPool *>(cb, boost::python::ptr(&address));
            assert(res == nullptr || res->address == address_t(address));
        }

        if (res == nullptr)
        {
            log_error("lookup_lp(%1%) failed", address);
            static bool alerted = false;
            if (!cb && !alerted)
            {
                alerted = true;
                log_warning("TheGraph needs a way to fetch LiquidityPool objects. "
                            "Please post a callback with set_fetch_lp_addr_cb()");
            }
        }
#endif
    }

    return res;
}

std::vector<const OperableSwap *> TheGraph::lookup_swap(datatag_t token0, datatag_t token1)
{
    std::vector<const OperableSwap *> res;
    auto t0 = lookup_token(token0);
    auto t1 = lookup_token(token1);

    if (t0 == nullptr)
    {
        log_error("token0 id %1% not found", token0);
        return res;
    }
    if (t1 == nullptr)
    {
        log_error("token1 id %1% not found", token1);
        return res;
    }

    return lookup_swap(t0, t1);
}

std::vector<const OperableSwap *> TheGraph::lookup_swap(const Token *t0, const Token *t1)
{
    assert(t0 != nullptr);
    assert(t1 != nullptr);
    std::vector<const OperableSwap *> res;

    auto range = swap_index->get<idx::by_src_and_dest_token>().equal_range(boost::make_tuple(t0, t1));
    for (auto i = range.first; i != range.second; ++i)
    {
        res.push_back(*i);
    }

    return res;
}


const LiquidityPool *TheGraph::lookup_lp(datatag_t tag)
{
    return lookup_lp(tag, true);
}

const LiquidityPool *TheGraph::lookup_lp(datatag_t tag, bool fetch_if_missing)
{
    auto res = entity_index->lookup<LiquidityPool, TYPE_LP>(tag);

    if (fetch_if_missing)
    {
#if !defined(NOPYTHON) || !NOPYTHON
        auto &cb = m_fetch_lp_tag_cb;

        if (res == nullptr && cb)
        {
            res = m_call_cb<const LiquidityPool *>(cb, tag);
            assert(res == nullptr || res->tag == tag);
        }

        if (res == nullptr)
        {
            log_error("lookup_lp(%1%) failed", tag);
            static bool alerted = false;
            if (!cb && !alerted)
            {
                alerted = true;
                log_warning("TheGraph needs a way to fetch LiquidityPool objects. "
                            "Please post a callback with set_fetch_lp_tag_cb()");
            }
        }
#endif
    }

    return res;
}

static auto clear_existing_paths_if_any = [](TheGraph *graph)
{
    assert(graph);
    assert(graph->paths_index);

    for (auto p: graph->paths_index->path_idx)
    {
        assert(p.second != nullptr);
        delete p.second;
    }

    graph->paths_index->path_by_lp_idx.clear();
    graph->paths_index->path_idx.clear();
};

void TheGraph::calculate_paths()
{
    lock_guard_t lock_guard(m_update_mutex);
    using Path = pathfinder::Path;

    clear_existing_paths_if_any(this);

    pathfinder::Finder f{this};

    if (start_token == nullptr)
    {
        log_error("calculate_paths(): start_token not set");
        return;
    }

    log_info("calculate_paths() considering start_token %s at %p"
             , start_token->symbol.c_str()
             , start_token);

    auto listener = [&](const Path *path)
    {
        log_trace("found path: [%1%, %2%, %3%, %4%]"
                  , (*path)[0]->tokenSrc->tag
                  , (*path)[1]->tokenSrc->tag
                  , (*path)[2]->tokenSrc->tag
                  , (*path)[2]->tokenDest->tag);
        paths_index->add_path(path);
    };

    f.find_all_paths_3way_var(listener, start_token);
    log_info("computed: %u paths, %u entries in hot swaps index"
             , paths_index->path_idx.size()
             , paths_index->path_by_lp_idx.size());
}

TheGraph::PathList TheGraph::find_paths_to_token(const Token *token) const
{
    PathList result;
    auto swaps = swap_index
            ->get<idx::by_dest_token>()
            .equal_range(token);
    for (auto i = swaps.first; i != swaps.second; ++i)
    {
        const LiquidityPool *pool = (*i)->pool;
        assert(pool != nullptr);
        auto paths = paths_index->path_by_lp_idx.equal_range(pool);
        for (auto j = paths.first; j != paths.second; ++j)
        {
            const pathfinder::Path *path = j->second;
            assert(path != nullptr);
            for (unsigned k = 0; k < path->size(); ++k)
            {
                const OperableSwap *swap = (*path)[k];
                assert(swap != nullptr);
                if (swap->tokenDest == token)
                {
                    result.emplace_back(path);
                    break;
                }
            }
        }
    }
    return result;
}

static void check_constrants_consistency(TheGraph *g, const PathEvalutionConstraints &c)
{
    assert(g != nullptr);
    if (g->start_token == nullptr)
    {
        throw std::runtime_error("TheGraph::start_token not set!!");
    }
    log_debug("evaluate_known_paths() seach of swap opportunities starting");
    log_debug(" \\__ start_token is %1% (%2%)", g->start_token->symbol, g->start_token->address);
    if (c.initial_balance > 0)
    {
        log_debug(" \\__ initial_balance is %1% (%2% Weis)"
                  , g->start_token->fromWei(c.initial_balance)
                  , c.initial_balance);
    }
    else {
        log_debug(" \\__ no balance provided. Please set "
                  "initial_balance to a meaningful Wei amount of start_token (%1%)"
                  , g->start_token->symbol);
        return;
    }
    if (c.max_lp_reserves_stress > 0)
    {
        log_debug(" \\__ max_lp_reserves_stress set at %1%", c.max_lp_reserves_stress);
    }
    if (c.convenience_min_threshold >= 0)
    {
        log_debug(" \\__ ignore yields < convenience_min_threshold (%1%)", c.convenience_min_threshold);
    }
    if (c.convenience_max_threshold >= 0)
    {
        log_debug(" \\__ ignore yields > convenience_max_threshold (%1%)", c.convenience_max_threshold);
    }
    if (c.match_limit)
    {
        log_debug(" \\__ match limit is set at %1%", c.match_limit);
    }
    if (c.limit)
    {
        log_debug(" \\__ loop limit is set at %1%", c.limit);
    }
}




// local functor: returns a string representation of the steps involved
// in the currently examined swap.  Only used for logging.
static std::string log_path_nodes(const pathfinder::Path *path, bool include_addesses=false, bool include_tags=true)
{
    std::stringstream ss;
    for (auto i = 0; i < path->size(); ++i)
    {
        auto swap = path->get(i);
        if (i > 0) ss << ", ";
        ss << swap->pool->exchange->name
           << "(" << swap->tokenSrc->symbol
           << "-" << swap->tokenDest->symbol;
        if (include_tags) ss << ", " << swap->pool->tag;
        if (include_addesses) ss << ", " << swap->pool->address;
        ss << ")";
    }
    return ss.str();
};


static void print_swap_candidate(TheGraph *g
                                 , const PathEvalutionConstraints &c
                                 , const pathfinder::Path *path
                                 , const TheGraph::PathResult &r)
{
    log_debug("candidate path %s would yield %0.5f%%"
             , log_path_nodes(path).c_str()
             , (r.yield_ratio()-1)*100);
    log_trace(" \\__ initial balance of %1% %2% (%3% Weis) "
             "turned in %4% %5% (%6% Weis)"
             , r.initial_token()->fromWei(r.initial_balance())
             , r.initial_token()->symbol
             , r.initial_balance()
             , r.final_token()->fromWei(r.final_balance())
             , r.final_token()->symbol
             , r.final_balance()
             );
};




struct ConstraintViolation {};



TheGraph::PathResultList TheGraph::debug_evaluate_known_paths(const PathEvalutionConstraints &c)
{
    lock_guard_t lock_guard(m_update_mutex);
    struct LimitReached {};
    TheGraph::PathResultList res;

    check_constrants_consistency(this, c);

    unsigned int ctr = 0;
    unsigned int matches = 0;
    for (auto i: paths_index->path_idx) try
    {
        // @note: loop body is a try block

        auto attack_plan = evaluate_path(c, i.second, false);
        if (attack_plan.failed) continue;
        assert(attack_plan.final_token() != nullptr);

        if (c.convenience_min_threshold >= 0 &&
            attack_plan.yield_ratio() < c.convenience_min_threshold)
        {
            throw ConstraintViolation();
        }

        if (c.convenience_max_threshold >= 0 &&
            attack_plan.yield_ratio() > c.convenience_max_threshold)
        {
            throw ConstraintViolation();
        }

        if (c.min_profit_target_amount > 0)
        {
            if (attack_plan.final_balance() <= attack_plan.initial_balance())
            {
                throw ConstraintViolation();
            }
            auto gain = attack_plan.final_balance() - attack_plan.initial_balance();
            if (gain < c.min_profit_target_amount)
            {
                throw ConstraintViolation();
            }
        }


        matches++;
        //print_swap_candidate(this, c, i.second, attack_plan);
        res.emplace_back(attack_plan);

        if (c.match_limit > 0 && matches >= c.match_limit)
        {
            log_trace("match limit reached (%1%)"
                      , c.match_limit);
            throw LimitReached();
        }

    }
    catch (ConstraintViolation&) { continue; }
    catch (LimitReached &) { break; }

    return res;
}

unsigned TheGraph::start_predicted_snapshot()
{
    lock_guard_t lock_guard(m_update_mutex);
    do {
        predicted_snapshot_key++;
    } while (predicted_snapshot_key == 0);
    return predicted_snapshot_key;
}

void TheGraph::terminate_predicted_snapshot(unsigned key)
{
    lock_guard_t lock_guard(m_update_mutex);
    auto range = predicted_snapshot_idx.equal_range(key);
    for (auto i = range.first; i != range.second; ++i)
    {
        i->second->leave_predicted_state(key);
    }
    predicted_snapshot_idx.erase(range.first, range.second);
}


TheGraph::PathResult TheGraph::evaluate_path(const PathEvalutionConstraints &c
                                             , const pathfinder::Path *path
                                             , unsigned prediction_snapshot_key) const
{
    assert(path != nullptr);
    auto result = path->evaluate_max_yield(c, prediction_snapshot_key);

    if (!result.failed)
    {
        auto token = path->initial_token();

        if (result.yield_ratio() > 1.0f)
        {
            log_trace(" \\__ after the final swap, the realized gain would be %0.5f%%"
                      , (result.yield_ratio()-1)*100.0);
        }
        else {
            log_trace(" \\__ after the final swap, the realized loss would be %0.5f%%"
                      , (1-result.yield_ratio())*100.0);
        }
        if (result.final_balance() > result.initial_balance())
        {
            auto gap = result.final_balance() - result.initial_balance();
            log_trace(" \\__ the operation gains %0.5f %s"
                      , token->fromWei(gap)
                      , token->symbol.c_str());
            log_trace("         \\__ or +%1% %2% Weis :)"
                      , gap
                      , token->symbol);
        }
        else {
            auto gap = result.initial_balance() - result.final_balance();
            log_trace(" \\__ the operation loses %0.5f %s"
                      , token->fromWei(gap)
                      , token->symbol.c_str());
            log_trace("         \\__ or -%1% %2% Weis :("
                      , gap
                      , token->symbol);
        }
        if (c.convenience_min_threshold >= 0 && result.yield_ratio() < c.convenience_min_threshold)
        {
            log_trace(" \\__ final yield is under the set convenience_min_threshold (path skipped)");
            throw ConstraintViolation();
        }

        if (c.convenience_max_threshold >= 0 && result.yield_ratio() > c.convenience_max_threshold)
        {
            log_trace(" \\__ final yield is under the set convenience_min_threshold (path skipped)");
            throw ConstraintViolation();
        }

        assert(token == start_token);
    }

    return result;
}

TheGraph::PathResultList TheGraph::evaluate_paths_of_interest(const PathEvalutionConstraints &c
                                                              , unsigned prediction_snapshot_key)
{
    lock_guard_t lock_guard(m_update_mutex);
    check_constrants_consistency(this, c);
    TheGraph::PathResultList res;


    auto range = predicted_snapshot_idx.equal_range(prediction_snapshot_key);
    for (auto iter = range.first; iter != range.second; ++iter)
    {
        auto pool = iter->second;
        auto r = paths_index->path_by_lp_idx.equal_range(pool);
        for (auto i = r.first; i != r.second; i++)
        {
            try {
                const pathfinder::Path *path = i->second;
                auto attack_plan = evaluate_path(c, path, prediction_snapshot_key);
                if (attack_plan.failed) continue;
                assert(attack_plan.final_token() != nullptr);

                if (c.convenience_min_threshold >= 0 &&
                    attack_plan.yield_ratio() < c.convenience_min_threshold)
                {
                    throw ConstraintViolation();
                }

                if (c.convenience_max_threshold >= 0 &&
                    attack_plan.yield_ratio() > c.convenience_max_threshold)
                {
                    throw ConstraintViolation();
                }
                if (c.min_profit_target_amount > 0)
                {
                    if (attack_plan.final_balance() <= attack_plan.initial_balance())
                    {
                        throw ConstraintViolation();
                    }
                    auto gain = attack_plan.final_balance() - attack_plan.initial_balance();
                    if (gain < c.min_profit_target_amount)
                    {
                        throw ConstraintViolation();
                    }
                }
                //print_swap_candidate(this, c, path, attack_plan);
                res.emplace_back(attack_plan);
            } catch (ConstraintViolation&) { continue; }

        }
    }
    return res;
}


const TheGraph::Path *TheGraph::lookup_path(std::size_t id) const
{
    return lookup_path(id, true);
}

const TheGraph::Path *TheGraph::lookup_path(std::size_t id, bool fetch_if_missing) const
{
    auto i = paths_index->path_idx.find(id);

    if (i != paths_index->path_idx.end())
    {
        return i->second;
    }

    const Path *res = nullptr;

    if (fetch_if_missing)
    {
#if !defined(NOPYTHON) || !NOPYTHON
        auto &cb = m_fetch_path_tag_cb;

        if (cb)
        {
            res = m_call_cb<const Path *>(cb, id);
        }

        if (res && res->id() != id)
        {
            log_error("fetch'd path object does not match requested hash_id "
                      "(expected %1%, obtained %2%)"
                      , id, res->id());
            return nullptr;
        }

        if (res == nullptr)
        {
            log_error("lookup_path(%1%) failed", id);
            static bool alerted = false;
            if (!cb && !alerted)
            {
                alerted = true;
                log_warning("TheGraph needs a way to fetch Path objects. "
                            "Please post a callback with set_fetch_path_tag_cb()");
            }
        }
#endif
    }

    return res;
}


static inline const OperableSwap *m_get_swap(const Token *enter_token
                                             , const LiquidityPool *pool)
{
    if (enter_token == pool->token0) return pool->swaps[0];
    assert(enter_token == pool->token1);
    return pool->swaps[1];
}

static const Token *m_find_start_token(const LiquidityPool *pools[])
{
    if (pools[0]->token0 == pools[1]->token0 ||
        pools[0]->token0 == pools[1]->token1)
    {
        return pools[0]->token1;
    }
    assert(pools[0]->token1 == pools[1]->token0 ||
           pools[0]->token1 == pools[1]->token1);
    return pools[0]->token0;
}


static const TheGraph::Path *m_add_path_ll(TheGraph *g
                                     , const LiquidityPool *pools[]
                                     , std::size_t size
                                     )
{
    using namespace pathfinder;
    const Token *token = m_find_start_token(pools);

    const OperableSwap *oswaps[MAX_PATHS];
    for (unsigned i = 0; i < size; ++i)
    {
        const OperableSwap *os;
        oswaps[i] = os = m_get_swap(token, pools[i]);
        assert(os->tokenSrc == token);
        token = os->tokenDest;
    }
    std::unique_ptr<TheGraph::Path> res;
    switch (PathLength(size))
    {
    case PATH_3WAY: res.reset(new TheGraph::Path(oswaps[0], oswaps[1], oswaps[2])); break;
    case PATH_4WAY: res.reset(new TheGraph::Path(oswaps[0], oswaps[1], oswaps[2], oswaps[3])); break;
    }
    assert(res != nullptr);

    auto &idx = g->paths_index->path_idx;
    auto found = idx.find(res->m_hash);
    if (found != idx.end())
    {
        return found->second;
    }

    return g->paths_index->add_path(res.release());
}

const TheGraph::Path *TheGraph::add_path(const LiquidityPool *p0
                                         , const LiquidityPool *p1
                                         , const LiquidityPool *p2)
{
    const LiquidityPool *pools[] = {p0, p1, p2};
    return m_add_path_ll(this, pools, sizeof(pools)/sizeof(pools[0]));
}
const TheGraph::Path *TheGraph::add_path(const LiquidityPool *p0
                                         , const LiquidityPool *p1
                                         , const LiquidityPool *p2
                                         , const LiquidityPool *p3)
{
    const LiquidityPool *pools[] = {p0, p1, p2, p3};
    return m_add_path_ll(this, pools, sizeof(pools)/sizeof(pools[0]));
}

const TheGraph::Path *TheGraph::add_path(datatag_t p0
                               , datatag_t p1
                               , datatag_t p2)
{
    return add_path(lookup_lp(p0)
                    , lookup_lp(p1)
                    , lookup_lp(p2)
                    );
}
const TheGraph::Path *TheGraph::add_path(datatag_t p0
                               , datatag_t p1
                               , datatag_t p2
                               , datatag_t p3)
{
    return add_path(lookup_lp(p0)
                    , lookup_lp(p1)
                    , lookup_lp(p2)
                    , lookup_lp(p3)
                    );
}

#if !defined(NOPYTHON) || !NOPYTHON
void TheGraph::set_fetch_exchange_tag_cb(boost::python::object cb)    { m_fetch_exchange_tag_cb = cb; }
void TheGraph::set_fetch_token_tag_cb(boost::python::object cb)       { m_fetch_token_tag_cb = cb; }
void TheGraph::set_fetch_lp_tag_cb(boost::python::object cb)          { m_fetch_lp_tag_cb = cb; }
void TheGraph::set_fetch_lp_reserves_tag_cb(boost::python::object cb) { m_fetch_lp_reserves_tag_cb = cb; }
void TheGraph::set_fetch_path_tag_cb(boost::python::object cb)        { m_fetch_path_tag_cb = cb; }
void TheGraph::set_fetch_token_addr_cb(boost::python::object cb)      { m_fetch_token_addr_cb = cb; }
void TheGraph::set_fetch_lp_addr_cb(boost::python::object cb)         { m_fetch_lp_addr_cb = cb; }
#endif

std::size_t TheGraph::exchanges_count() const
{
    return exchanges_ctr;
}

std::size_t TheGraph::tokens_count() const
{
    return tokens_ctr;
}

std::size_t TheGraph::pools_count() const
{
    return pools_ctr;
}

std::size_t TheGraph::paths_count() const
{
    return paths_index->path_idx.size();
}



} // namespace model
} // namespace bofh
