#pragma GCC diagnostic ignored "-Wdeprecated-declarations" // Silencing GCC nagging me about std::auto_ptr somewhere in boost legacy snippets

#include <boost/python.hpp>
#include "longobject.h"
#include "bofh_model.hpp"


using namespace boost::python;
using namespace bofh::model;

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

    PyObject *str_repr = PyObject_Str(vv);
    PyObject *encodedString = PyUnicode_AsEncodedString(str_repr, "UTF-8", "strict");
    balance_t res = -1;
    if (encodedString)
    {
        char *repr = PyBytes_AsString(encodedString);
        try {
            res = repr;
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
        if (!PyLong_Check(obj_ptr)) return 0;
        return obj_ptr;
    }

    static void construct(
        PyObject* obj_ptr,
        converter::rvalue_from_python_stage1_data* data)
    {
        // Grab pointer to memory into which to construct the new QString
        balance_t* storage = reinterpret_cast<balance_t*>(((converter::rvalue_from_python_storage<balance_t>*)data)->storage.bytes);

        // in-place construct the new QString using the character data
        // extraced from the python object
        new (storage) balance_t();
        *storage = PyLong_AsBalance(obj_ptr);

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
    using dont_manage_returned_pointer = return_value_policy<reference_existing_object>;

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

    class_<Token, dont_make_copies>("Token", no_init)
            .def_readonly("name"   , &Token::name)
            .def_readonly("address", &Token::address)
            ;
    register_ptr_to_python<const Token*>();

    class_<Exchange, dont_make_copies>("Exchange", no_init)
            .def_readonly("name"   , &Exchange::name)
            ;
    register_ptr_to_python<const Exchange*>();

    class_<SwapPair, dont_make_copies>("SwapPair", no_init)
            .def_readonly("address", &SwapPair::address)
            .def_readonly("token0" , &SwapPair::token0)
            .def_readonly("token1" , &SwapPair::token1)
            .def_readwrite("reserve0" , &SwapPair::reserve0)
            .def_readwrite("reserve1" , &SwapPair::reserve1)
            ;
    register_ptr_to_python<const SwapPair*>();
    register_ptr_to_python<SwapPair*>();

    class_<TheGraph, dont_make_copies>("TheGraph")
            .def("add_exchange"    , &TheGraph::add_exchange    , dont_manage_returned_pointer())
            .def("add_token"       , &TheGraph::add_token       , dont_manage_returned_pointer())
            .def("add_swap_pair"   , &TheGraph::add_swap_pair   , dont_manage_returned_pointer())
            .def("lookup_token"    , &TheGraph::lookup_token    , dont_manage_returned_pointer())
            .def("lookup_swap_pair", static_cast<const SwapPair *(TheGraph::*)(const address_t &)>(&TheGraph::lookup_swap_pair), dont_manage_returned_pointer())
            .def("lookup_swap_pair", static_cast<const SwapPair *(TheGraph::*)(const char *     )>(&TheGraph::lookup_swap_pair), dont_manage_returned_pointer())
            ;
}



