
#include "test_utils.hpp"


/**
 * @brief test (a populated) graph lifecycle
 *
 * This does nothing other than build and destroy a graph object.
 *
 * It's expected to crash bad or leak if the memory bookkeeping is borked.
 *
 * Basic sanity check.
 */
int main()
{
    using namespace bofh::model::test;
    {
        auto graph = make_random_graph();
    }
    return 0;
}
