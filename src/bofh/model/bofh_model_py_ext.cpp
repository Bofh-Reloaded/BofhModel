#pragma GCC diagnostic ignored "-Wdeprecated-declarations" // Silencing GCC nagging me about std::auto_ptr somewhere in boost legacy snippets

#include <boost/python.hpp>
#include "bofh_model.hpp"

using namespace boost::python;
using namespace bofh::model;



BOOST_PYTHON_MODULE(bofh_model)
{
    using dont_make_copies = boost::noncopyable;
    using dont_manage_returned_pointer = return_value_policy<reference_existing_object>;

    class_<Token, dont_make_copies>("Token", no_init)
            .def_readonly("name", &Token::name)
            .def_readonly("address", &Token::address)
            ;

    class_<SwapPair, dont_make_copies>("SwapPair", no_init)
            .def_readonly("address", &SwapPair::address)
            .def_readonly("token0", &SwapPair::token0)
            .def_readonly("token1", &SwapPair::token1)
            ;

    class_<TheGraph, dont_make_copies>("TheGraph")
            .def("add_token"       , &TheGraph::add_token       , dont_manage_returned_pointer())
            .def("add_swap_pair"   , &TheGraph::add_swap_pair   , dont_manage_returned_pointer())
            .def("lookup_token"    , &TheGraph::lookup_token    , dont_manage_returned_pointer())
            .def("lookup_swap_pair", &TheGraph::lookup_swap_pair, dont_manage_returned_pointer())
            ;
}



