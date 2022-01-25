#pragma GCC diagnostic ignored "-Wdeprecated-declarations" // Silencing GCC nagging me about std::auto_ptr somewhere in boost legacy snippets

#include <boost/python.hpp>
#include <boost/python/suite/indexing/vector_indexing_suite.hpp>
#include <boost/python/suite/indexing/map_indexing_suite.hpp>
#include "longobject.h"
#include "unicodeobject.h"
#include "bofh_model.hpp"
#include "bofh_entity_idx.hpp"
#include "../pathfinder/finder_3way.hpp"
#include "../pathfinder/swaps_idx.hpp"
#include "../commons/bofh_log.hpp"



using namespace boost::python;
using namespace bofh::model;
using namespace bofh::pathfinder;



#define PY_ABS_LONG_MIN         (0-(unsigned long)LONG_MIN)

/**
 * @brief PyLong_AsBalance
 *
 * Translate a CPython bigint into a boost::multiprecision bigint (balance_t).
 *
 * Used to provide transparent translation from Python to C++ data.
 *
 * @param vv
 * @return
 */
static balance_t PyLong_AsBalance(PyObject *vv)
{
    // it's complicated to efficiently transpose Python's internal bigint representation
    // into boost::multiprecision bigint object limbs. I'm using string serialization
    // and lexing of the uint number. The lexing of balance_t is very efficient, but
    // this is less than ideal.

    // TODO: avoid using string parsing. Perform more efficient bit banging translation.

    if (PyBytes_Check(vv))
    {
        try {
            return balance_t(PyBytes_AsString(vv));
        } catch (...) {
            PyErr_SetString(PyExc_ValueError, "bad uint representation");
            return -1;
        }
    }

    PyObject *str_repr = PyObject_Str(vv);
    PyObject *encodedString = PyUnicode_AsEncodedString(str_repr, "UTF-8", "strict");
    balance_t res = -1;
    if (encodedString)
    {
        char *repr = PyBytes_AsString(encodedString);
        try {
            res = balance_t(repr);
        }
        catch (...) {
            PyErr_SetString(PyExc_ValueError, "value error");
        }
        Py_DECREF(encodedString);
    }
    else {
        PyErr_SetString(PyExc_ValueError, "bad uint representation");
    }
    Py_DECREF(str_repr);

    return res;
}


/**
 * @brief Translator which executes transparent translation of Python unbounded "int" into
 *        balance_t objects, which are very big numbers, much larger than
 *        the largest CPU registry.
 *
 */
struct balance_from_python_long
{
    balance_from_python_long()
    {
        converter::registry::push_back(
                    &convertible,
                    &construct,
                    boost::python::type_id<balance_t>());

    }

    // Determine if obj_ptr can be converted
    static void* convertible(PyObject* obj_ptr)
    {
        if (PyLong_Check(obj_ptr) ||
                PyUnicode_Check(obj_ptr) ||
                PyBytes_Check(obj_ptr)
                ) return obj_ptr;
        return 0;
    }

    static void construct(
        PyObject* obj_ptr,
        converter::rvalue_from_python_stage1_data* data)
    {
        // Grab pointer to memory into which to construct the new QString
        balance_t* storage = reinterpret_cast<balance_t*>(((converter::rvalue_from_python_storage<balance_t>*)data)->storage.bytes);

        // in-place construct the new QString using the character data
        // extraced from the python object
        new (storage) balance_t(PyLong_AsBalance(obj_ptr));

        // Stash the memory chunk pointer for later use by boost.python
        data->convertible = storage;
    }

};


/**
 * @brief Export C++ model to Python.
 *
 * This is what is seen by "import" of this CPython extension.
 */
BOOST_PYTHON_MODULE(bofh_model_ext)
{
    using dont_make_copies = boost::noncopyable;
    using dont_manage_returned_pointer = return_internal_reference<>; // return_value_policy<reference_existing_object>;

    class_<balance_t>("balance_t")
            .def(init<const char *>())
            .def(init<unsigned long long int>())
            .def(self_ns::repr(self_ns::self))
            .def(self_ns::str(self_ns::self))
            ;
    balance_from_python_long();

    class_<address_t, dont_make_copies>("address_t")
            .def(init<const char *>())
            .def(self_ns::repr(self_ns::self))
            .def(self_ns::str(self_ns::self))
            ;
    register_ptr_to_python<const address_t*>();
    register_ptr_to_python<address_t*>();

    class_<Entity, dont_make_copies>("Entity", no_init)
            .def_readonly("tag" , &Entity::tag)
            .def_readonly("address", &Entity::address);
    register_ptr_to_python<const Entity*>();
    register_ptr_to_python<Entity*>();

    class_<OperableSwap, dont_make_copies>("OperableSwap", no_init)
            .def_readonly("tokenSrc", &OperableSwap::tokenSrc)
            .def_readonly("tokenDest", &OperableSwap::tokenDest)
            .def_readonly("pool", &OperableSwap::pool);
    register_ptr_to_python<const OperableSwap*>();
    register_ptr_to_python<OperableSwap*>();

    class_<std::vector<const OperableSwap*>>("OperableSwaps")
            .def(vector_indexing_suite<std::vector<const OperableSwap*>>());

    class_<Token, bases<Entity>, dont_make_copies>("Token", no_init)
            .def_readonly("name"       , &Token::name)
            .def_readonly("symbol"     , &Token::symbol)
            .def_readonly("decimals"   , &Token::decimals)
            .def_readonly("is_stable"  , &Token::is_stable)
            ;
    register_ptr_to_python<const Token*>();
    register_ptr_to_python<Token*>();

    class_<Exchange, bases<Entity>, dont_make_copies>("Exchange", no_init)
            .def_readonly("name"   , &Exchange::name)
            ;
    register_ptr_to_python<const Exchange*>();
    register_ptr_to_python<Exchange*>();

    class_<LiquidityPool, bases<Entity>, dont_make_copies>("LiquidityPool", no_init)
            .def_readonly("exchange"  , &LiquidityPool::exchange)
            .def_readonly("token0"    , &LiquidityPool::token0)
            .def_readonly("token1"    , &LiquidityPool::token1)
            .def_readwrite("reserve0" , &LiquidityPool::reserve0)
            .def_readwrite("reserve1" , &LiquidityPool::reserve1)
//            .def("setReserve", &LiquidityPool::setReserve)
            .def("setReserves", &LiquidityPool::setReserves)
//            .def("getReserve", &LiquidityPool::getReserve)
//            .def("simpleSwap", &LiquidityPool::simpleSwap)
            .def("swapRatio", &LiquidityPool::swapRatio)
            .def("fees", &LiquidityPool::fees)
            ;

    register_ptr_to_python<const LiquidityPool*>();
    register_ptr_to_python<LiquidityPool*>();


    class_<Path>("Path", init<Path::value_type, Path::value_type, Path::value_type>())
            .def(init<Path::value_type, Path::value_type, Path::value_type, Path::value_type>())
            .def("size"                 , &Path::size)
            .def("estimate_profit_ratio", &Path::estimate_profit_ratio)
            .def("get"                  , &Path::get, dont_manage_returned_pointer());
    register_ptr_to_python<const Path*>();
    register_ptr_to_python<Path*>();


    class_<TheGraph::PathEvalutionConstraints>("PathEvalutionConstraints")
            .def_readwrite("initial_token_wei_balance"  , &TheGraph::PathEvalutionConstraints::initial_token_wei_balance)
            .def_readwrite("max_lp_reserves_stress"     , &TheGraph::PathEvalutionConstraints::max_lp_reserves_stress)
            .def_readwrite("convenience_min_threshold"  , &TheGraph::PathEvalutionConstraints::convenience_min_threshold)
            .def_readwrite("convenience_max_threshold"  , &TheGraph::PathEvalutionConstraints::convenience_max_threshold)
            .def_readwrite("limit"                      , &TheGraph::PathEvalutionConstraints::limit)
            ;
    register_ptr_to_python<const TheGraph::PathEvalutionConstraints*>();
    register_ptr_to_python<TheGraph::PathEvalutionConstraints*>();


    class_<TheGraph, dont_make_copies>("TheGraph")
            .def_readwrite("start_token" , &TheGraph::start_token)
            .def("add_exchange"   , &TheGraph::add_exchange    , dont_manage_returned_pointer())
            .def("add_token"      , &TheGraph::add_token       , dont_manage_returned_pointer())
            .def("add_lp"         , &TheGraph::add_lp          , dont_manage_returned_pointer())
            .def("lookup_exchange", &TheGraph::lookup_exchange , dont_manage_returned_pointer())
            .def("lookup_token"   , static_cast<const Token    *(TheGraph::*)(const char *          )>(&TheGraph::lookup_token), dont_manage_returned_pointer())
            .def("lookup_token"   , static_cast<const Token    *(TheGraph::*)(datatag_t             )>(&TheGraph::lookup_token), dont_manage_returned_pointer())
            .def("lookup_lp"      , static_cast<const LiquidityPool *(TheGraph::*)(const address_t &)>(&TheGraph::lookup_lp)   , dont_manage_returned_pointer())
            .def("lookup_lp"      , static_cast<const LiquidityPool *(TheGraph::*)(const char *     )>(&TheGraph::lookup_lp)   , dont_manage_returned_pointer())
            .def("lookup_lp"      , static_cast<const LiquidityPool *(TheGraph::*)(datatag_t        )>(&TheGraph::lookup_lp)   , dont_manage_returned_pointer())
            .def("lookup_swap"    , &TheGraph::lookup_swap)
            .def("calculate_paths", &TheGraph::calculate_paths)
            .def("debug_evaluate_known_paths", &TheGraph::debug_evaluate_known_paths)
            ;

    enum_<log_level>("log_level")
            .value("trace"  , log_level_trace  )
            .value("debug"  , log_level_debug  )
            .value("info"   , log_level_info   )
            .value("warning", log_level_warning)
            .value("error"  , log_level_error  )
            .export_values()
            ;
    def("log_get_level", log_get_level);
    def("log_set_level", log_set_level);
    def("log_register_sink", log_register_sink);
}



