/**
 * @file bofh_log.hpp
 * @brief Logger facility with Python delegation
 *
 * Pretty standard logging with log_info(), log_debug() macros and so on.
 * The usual stuff.
 *
 * Features to mention:
 * - the output of the logging is delegated to a boost::python::object
 *   that is expected to be injected by the Python VM which loads this extension,
 *   using the function log_register_sink(python_callable)
 * - single-branch runtime triggering of log statements
 * - remove (not minimize) runtime impact of log statement parameter
 *   evaluation when log is not triggered
 * - uses boost::format in a more log-context friendly fashion
 *
 * @see bofh.model.misc.LogAdapter
 * @note The bofh.model.misc.LogAdapter class is designed to be injected
 *       into log_register_sink(). It redirects log events generated here to
 *       Python's standard logging framework
 */

#pragma once

#include <boost/format.hpp>
#include <boost/python/object_fwd.hpp>

typedef enum {
    log_level_trace,
    log_level_debug,
    log_level_info,
    log_level_warning,
    log_level_error,
} log_level;

/**
 * @brief returns true if the specified log @p lvl triggers the currently set log threshold
 */
bool log_trigger(log_level lvl);

/**
 * @brief returns the currently set log level threshold
 */
log_level log_get_level();

/**
 * @brief sets the log level threshold
 */
void log_set_level(log_level lvl);

/**
 * @brief Injects a Python callable delegate, as the log data sink
 */
void log_register_sink(boost::python::object sink);


void log_emit_ll(log_level lvl, const std::string &msg);

// some proper C preprocessor sht follows. feel free to look away

#define __NARG__(...)  __NARG_I_(__VA_ARGS__,__RSEQ_N())
#define __NARG_I_(...) __ARG_N(__VA_ARGS__)
#define __ARG_N( \
      _1, _2, _3, _4, _5, _6, _7, _8, _9,_10, \
     _11,_12,_13,_14,_15,_16,_17,_18,_19,_20, \
     _21,_22,_23,_24,_25,_26,_27,_28,_29,_30, \
     _31,_32,_33,_34,_35,_36,_37,_38,_39,_40, \
     _41,_42,_43,_44,_45,_46,_47,_48,_49,_50, \
     _51,_52,_53,_54,_55,_56,_57,_58,_59,_60, \
     _61,_62,_63,N,...) N
#define __RSEQ_N() \
     63,62,61,60,                   \
     59,58,57,56,55,54,53,52,51,50, \
     49,48,47,46,45,44,43,42,41,40, \
     39,38,37,36,35,34,33,32,31,30, \
     29,28,27,26,25,24,23,22,21,20, \
     19,18,17,16,15,14,13,12,11,10, \
     9,8,7,6,5,4,3,2,1,0

// general definition for any function name
#define _VFUNC_(name, n) name##n
#define _VFUNC(name, n) _VFUNC_(name, n)


#define log_emit_2(lvl, msg)                                                          if(log_trigger(lvl)) log_emit_ll(lvl, boost::str(boost::format(msg)))
#define log_emit_3(lvl, msg, a1)                                                      if(log_trigger(lvl)) log_emit_ll(lvl, boost::str(boost::format(msg) % a1))
#define log_emit_4(lvl, msg, a1, a2)                                                  if(log_trigger(lvl)) log_emit_ll(lvl, boost::str(boost::format(msg) % a1 % a2))
#define log_emit_5(lvl, msg, a1, a2, a3)                                              if(log_trigger(lvl)) log_emit_ll(lvl, boost::str(boost::format(msg) % a1 % a2 % a3))
#define log_emit_6(lvl, msg, a1, a2, a3, a4)                                          if(log_trigger(lvl)) log_emit_ll(lvl, boost::str(boost::format(msg) % a1 % a2 % a3 % a4))
#define log_emit_7(lvl, msg, a1, a2, a3, a4, a5)                                      if(log_trigger(lvl)) log_emit_ll(lvl, boost::str(boost::format(msg) % a1 % a2 % a3 % a4 % a5))
#define log_emit_8(lvl, msg, a1, a2, a3, a4, a5, a6)                                  if(log_trigger(lvl)) log_emit_ll(lvl, boost::str(boost::format(msg) % a1 % a2 % a3 % a4 % a5 % a6))
#define log_emit_9(lvl, msg, a1, a2, a3, a4, a5, a6, a7)                              if(log_trigger(lvl)) log_emit_ll(lvl, boost::str(boost::format(msg) % a1 % a2 % a3 % a4 % a5 % a6 % a7))
#define log_emit_10(lvl, msg, a1, a2, a3, a4, a5, a6, a7, a8)                         if(log_trigger(lvl)) log_emit_ll(lvl, boost::str(boost::format(msg) % a1 % a2 % a3 % a4 % a5 % a6 % a7 % a8))
#define log_emit_11(lvl, msg, a1, a2, a3, a4, a5, a6, a7, a8, a9)                     if(log_trigger(lvl)) log_emit_ll(lvl, boost::str(boost::format(msg) % a1 % a2 % a3 % a4 % a5 % a6 % a7 % a8 % a9))
#define log_emit_12(lvl, msg, a1, a2, a3, a4, a5, a6, a7, a8, a9, a10)                if(log_trigger(lvl)) log_emit_ll(lvl, boost::str(boost::format(msg) % a1 % a2 % a3 % a4 % a5 % a6 % a7 % a8 % a9 % a10))
#define log_emit_13(lvl, msg, a1, a2, a3, a4, a5, a6, a7, a8, a9, a10, a11)           if(log_trigger(lvl)) log_emit_ll(lvl, boost::str(boost::format(msg) % a1 % a2 % a3 % a4 % a5 % a6 % a7 % a8 % a9 % a10 % a11))
#define log_emit_14(lvl, msg, a1, a2, a3, a4, a5, a6, a7, a8, a9, a10, a11, a12)      if(log_trigger(lvl)) log_emit_ll(lvl, boost::str(boost::format(msg) % a1 % a2 % a3 % a4 % a5 % a6 % a7 % a8 % a9 % a10 % a11 % a12))
#define log_emit_15(lvl, msg, a1, a2, a3, a4, a5, a6, a7, a8, a9, a10, a11, a12, a13) if(log_trigger(lvl)) log_emit_ll(lvl, boost::str(boost::format(msg) % a1 % a2 % a3 % a4 % a5 % a6 % a7 % a8 % a9 % a10 % a11 % a12 % a13))
#define log_emit(...) _VFUNC(log_emit_, __NARG__(__VA_ARGS__)) (__VA_ARGS__)

// here, use these:
#define log_trace(...)   log_emit(log_level_trace  , __VA_ARGS__)
#define log_debug(...)   log_emit(log_level_debug  , __VA_ARGS__)
#define log_info(...)    log_emit(log_level_info   , __VA_ARGS__)
#define log_warning(...) log_emit(log_level_warning, __VA_ARGS__)
#define log_error(...)   log_emit(log_level_error  , __VA_ARGS__)

