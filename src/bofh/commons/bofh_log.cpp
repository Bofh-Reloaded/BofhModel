#include "bofh_log.hpp"
#include <boost/python.hpp>
#include <boost/python/object.hpp>

struct status_holder {
    // this is allocated on heap at runtime.
    // it avoids building boost::python::object statically:
    // It wouldn't be fair behaviour in a dynamically loadable module

    boost::python::object functor;
};

static status_holder *m_status = nullptr;
static log_level m_current_level = log_level_info;


bool log_trigger(log_level lvl)
{
    return lvl >= m_current_level;
}

log_level log_get_level()
{
    return m_current_level;
}

void log_set_level(log_level lvl)
{
    switch (lvl) {
    case log_level_trace:
    case log_level_debug:
    case log_level_info:
    case log_level_warning:
    case log_level_error:
        m_current_level = lvl;
        break;
    default:
        break;
    }
}


void log_register_sink(boost::python::object sink)
{
    if (m_status == nullptr) m_status = new status_holder;
    m_status->functor = sink;
}


void log_emit_ll(log_level lvl, const std::string &msg)
{
    if (!log_trigger(lvl)) return;
    if (m_status == nullptr) return;
    try {
        m_status->functor(lvl, msg.c_str());
    } catch (...) {
        // silence anything boost::python may rise during dispatch attempts
    }
}
