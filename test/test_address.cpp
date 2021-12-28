#include <bofh/model/bofh_types.hpp>
#include <ostream>
#include <sstream>

using namespace bofh::model;
using namespace std;

template<typename T> std::string to_string(const T& o) {
    std::stringstream ss;
    ss << o;
    return ss.str();
}

void test_ctor_def(void)
{
    address_t a;
    // expect this not to blow up
}

void test_ctor_fromstr(void)
{
    std::string input = "0x5369f69c74d1d7bf70d5d402b92e66551edd05e7";
    address_t a0(input.c_str());
    if (to_string(a0) != input)
    {
        throw std::runtime_error("test_ctor_fromstr");
    }
}

int main()
{
    test_ctor_def();
    test_ctor_fromstr();

}
