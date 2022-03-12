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
using int256_t =  boost::multiprecision::int256_t;
using int320_t =  boost::multiprecision::int512_t;
using uint160_t = number<cpp_int_backend<160, 160, unsigned_magnitude, unchecked, void> >;

}

/**
 * @brief Balance of any given token (currently unsigned)
 *
 * TODO: establish when and where this needs to be signed;
 */
typedef bignum::uint256_t balance_t;


/**
 * @brief Blockchain addresses are stored in 160 bit wide uints
 *
 * This type is constructible by string. It parses the
 * widespread Ethereum address hexstring format 0xhhhhhhhhhhhhh.
 * The constructor does not check for overflow, but will fail in case the
 * string is not a valid hexstring.
 *
 * This thing is indexable, does not make use of heap memory and
 * it's copy constructible.
 */

struct address_t: bignum::uint160_t
{
    typedef bignum::uint160_t base_type;
    static constexpr unsigned size_bits = 160;
    static constexpr unsigned nibs = size_bits / 4;
    using bignum::uint160_t::uint160_t;
    address_t();
    address_t(const char *hexstring);        ///< constructible via 0x... hexstring
};

inline bool operator==(const address_t &a, const address_t &b)
{
    return reinterpret_cast<const address_t::base_type &>(a) ==
            reinterpret_cast<const address_t::base_type &>(b);
}

std::ostream& operator<< (std::ostream& stream, const address_t& o);


typedef unsigned long int datatag_t;

} // namespace model
} // namespace bofh


