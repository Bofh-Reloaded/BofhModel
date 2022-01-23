#pragma once

#include "bofh_common.hpp"
#include "bofh_model_fwd.hpp"
#include "bofh_entity_idx_fwd.hpp"
#include <vector>
#include <array>
#include <boost/multiprecision/cpp_int.hpp>
#include <ostream>


namespace bofh {
namespace model {

namespace bignum {

using namespace boost::multiprecision;
using uint256_t = boost::multiprecision::uint256_t;
using uint320_t = boost::multiprecision::uint512_t;
}

/**
 * @brief Balance of any given token (currently unsigned)
 *
 * TODO: establish when and where this needs to be signed;
 */
typedef bignum::uint256_t balance_t;


/**
 * @brief Blockchain addresses are stored in 320 bit wide uints
 *
 * This type is constructible by string. It parses the
 * widespread Ethereum address hexstring format [0x]hhhhhhhhhhhhh.
 * The constructor does not check for overflow, but will fail in case the
 * string is not a valid hexstring.
 *
 * This thing is indexable, does not make use of heap memory and
 * it's copy constructible.
 */
struct address_size {
    typedef uint32_t word;
    static constexpr unsigned size_bits = 320;
    static constexpr unsigned nibs = size_bits / 4;
    static constexpr unsigned word_size = sizeof(word)*8;
    static constexpr unsigned word_nibs = word_size / 4;
    static constexpr unsigned words = (size_bits+word_size-1) / word_size ;

    static_assert (nibs*4 == size_bits
        , "Weird size -_-'' address_size_bits expected to be a multiple of 4");
};

typedef std::array<address_size::word, address_size::words> address_base;

struct address_t: address_base, address_size
{
    address_t();
    address_t(const char *hexstring);        ///< constructible via 0x... hexstring
    using address_base::array; ///< plus the usual constructors
};

std::ostream& operator<< (std::ostream& stream, const address_t& o);


typedef unsigned long int datatag_t;

} // namespace model
} // namespace bofh


