#include "bofh_model.hpp"
#include "bofh_entity_idx.hpp"
#include <exception>
#include <cstring>
#include <iostream>
#include "3rd-party/hash-library/keccak.h"

namespace bofh {
namespace model {

static unsigned hex2nib(unsigned c)
{
    switch (c) {
    case '0':           return 0x0;
    case '1':           return 0x1;
    case '2':           return 0x2;
    case '3':           return 0x3;
    case '4':           return 0x4;
    case '5':           return 0x5;
    case '6':           return 0x6;
    case '7':           return 0x7;
    case '8':           return 0x8;
    case '9':           return 0x9;
    case 'a': case 'A': return 0xA;
    case 'b': case 'B': return 0xB;
    case 'c': case 'C': return 0xC;
    case 'd': case 'D': return 0xD;
    case 'e': case 'E': return 0xE;
    case 'f': case 'F': return 0xF;
    default:
        throw std::bad_cast();
    }
};

static inline bool is_digit(unsigned c)
{
    switch (c) {
    case '0':
    case '1':
    case '2':
    case '3':
    case '4':
    case '5':
    case '6':
    case '7':
    case '8':
    case '9':
        return true;
    default:
        break;
    }
    return false;
}

static inline bool is_hex(unsigned c)
{
    switch (c) {
    case 'a': case 'A':
    case 'b': case 'B':
    case 'c': case 'C':
    case 'd': case 'D':
    case 'e': case 'E':
    case 'f': case 'F':
        return true;
    default:
        break;
    }
    return false;
}

static inline char hex_upcase(char c)
{
    switch (c) {
    case 'a': case 'A': return 'A';
    case 'b': case 'B': return 'B';
    case 'c': case 'C': return 'C';
    case 'd': case 'D': return 'D';
    case 'e': case 'E': return 'E';
    case 'f': case 'F': return 'F';
    default:
        break;
    }
    return c;
}

address_t::address_t()
{
    fill(0);
}

address_t::address_t(const char *s):
    address_t()
{
    auto s_read = s;
    if (s_read == nullptr)
    {
        return;
    }

    // skip leading "0x0.." prequel, if any

    const char *s_end = s_read + std::strlen(s_read);
    if (s_end - s_read < address_t::nibs)
    {
        throw std::bad_cast();
    }
    if (s_read[0] == '0' && s_read[1] == 'x') s_read += 2;
    auto w = begin();

    unsigned shl = address_t::word_size;
    unsigned nib = 0;
    for (; nib < address_t::nibs && s_read < s_end; ++nib, ++s_read)
    {
        if (shl == 0)
        {
            shl = address_t::word_size;
            w++;
        }
        shl -= 4;
        *w |= (hex2nib(*s_read) << shl);
    }
    if (nib != address_t::nibs)
    {
        throw std::bad_cast();
    }
    if (s_read != s_end)
    {
        throw std::overflow_error(s);
    }
}

struct addr_as_string {
    char buf[address_t::nibs+1] = {0};
};

static void m_serialize_addr(addr_as_string &s, const address_t &o)
{
    char *w = s.buf;
    static const char hex[] = "0123456789abcdef";

    unsigned rhl = address_t::word_size;
    auto r = o.cbegin();
    for (unsigned nib = 0; nib < address_t::nibs; ++nib, ++w)
    {
        if (rhl == 0)
        {
            rhl = address_t::word_size;
            r++;
        }
        rhl -= 4;
        *w = hex[((*r)>>rhl) & 0x0f];
    }
}

static void m_checksum_encode(addr_as_string &s)
{
    addr_as_string checksummed;

    constexpr auto bits = Keccak::Keccak256;
    char hashed_address[bits/4+1] = {0};

    Keccak hash(bits);
    hash.add(s.buf, address_t::nibs);
    hash.getHash(hashed_address, sizeof(hashed_address));

    // Iterate over each character in the hex address
    for (unsigned int nibble_index = 0
         ; nibble_index < address_t::nibs
         ; ++nibble_index)
    {
        const char character = s.buf[nibble_index];


        if (is_digit(character))
        {
            // We can't upper-case the decimal digits
            checksummed.buf[nibble_index] = character;
        }
        else if (is_hex(character))
        {
            // Check if the corresponding hex digit (nibble) in the hash is 8 or higher
            const unsigned hashed_address_nibble = hex2nib(hashed_address[nibble_index]);
            if (hashed_address_nibble > 7)
            {
                checksummed.buf[nibble_index] = hex_upcase(character);
            }
            else
            {
                checksummed.buf[nibble_index] = character;
            }
        }
    }
    s = checksummed;
}


std::ostream& operator<< (std::ostream& stream, const address_t& o)
{
    addr_as_string as_str;

    m_serialize_addr(as_str, o);
    m_checksum_encode(as_str);

    stream << "0x" << as_str.buf;

    return stream;
}



} // namespace model
} // namespace bofh


