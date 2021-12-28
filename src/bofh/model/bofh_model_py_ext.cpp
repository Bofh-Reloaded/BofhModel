#pragma GCC diagnostic ignored "-Wdeprecated-declarations" // Silencing GCC nagging me about std::auto_ptr somewhere in boost legacy snippets

#include <boost/python.hpp>
#include "bofh_model.hpp"

using namespace boost::python;
using namespace bofh::model;


BOOST_PYTHON_MODULE(bofh_model_ext)
{
    using dont_make_copies = boost::noncopyable;
    using dont_manage_returned_pointer = return_value_policy<reference_existing_object>;

    class_<address_t, dont_make_copies>("address_t")
            .def(init<const char *>())
            .def(self_ns::repr(self_ns::self))
            .def(self_ns::str(self_ns::self))
            ;

    class_<Token, dont_make_copies>("Token", no_init)
            .def_readonly("name"   , &Token::name)
            .def_readonly("address", &Token::address)
            .def("get_address" , &Token::get_address    , dont_manage_returned_pointer())
            ;

    class_<Exchange, dont_make_copies>("Exchange", no_init)
            .def_readonly("name"   , &Exchange::name)
            ;

    class_<SwapPair, dont_make_copies>("SwapPair", no_init)
            .def_readonly("address", &SwapPair::address)
            .def_readonly("token0" , &SwapPair::token0)
            .def_readonly("token1" , &SwapPair::token1)
            .def("get_address" , &SwapPair::get_address    , dont_manage_returned_pointer())
            ;

    class_<TheGraph, dont_make_copies>("TheGraph")
            .def("add_exchange"    , &TheGraph::add_exchange    , dont_manage_returned_pointer())
            .def("add_token"       , &TheGraph::add_token       , dont_manage_returned_pointer())
            .def("add_swap_pair"   , &TheGraph::add_swap_pair   , dont_manage_returned_pointer())
            .def("lookup_token"    , &TheGraph::lookup_token    , dont_manage_returned_pointer())
            .def("lookup_swap_pair", &TheGraph::lookup_swap_pair, dont_manage_returned_pointer())
            ;
}



