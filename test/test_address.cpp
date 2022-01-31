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
    std::string checksummed = "0x5369F69C74d1D7Bf70d5D402b92E66551Edd05e7";
    address_t a0(input.c_str());
    if (to_string(a0) != checksummed)
    {
        throw std::runtime_error("test_ctor_fromstr");
    }
}

int main()
{
    test_ctor_def();
    test_ctor_fromstr();

}
