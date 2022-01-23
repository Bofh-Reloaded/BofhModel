#include "bofh_model.hpp"
#include "bofh_entity_idx.hpp"
#include <exception>
#include <cstring>

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


//balance_t::balance_t(const char *s)
//{
//    assert(s != nullptr);
//    *this = s;
//}

//const balance_t &balance_t::operator=(const char *s)
//{
//    assert(s != nullptr);
//    *this = 0u;
//    if (s != nullptr)
//    {
//        bool hex = false;
//        if (*s == '0') ++s;
//        if (*s == 'x' || *s == 'X') { ++s; hex = true; }
//        if (! hex) for (; *s; ++s)
//        {
//            *this *= 10;
//            switch (*s) {
//            case '0': *this += 0; break;
//            case '1': *this += 1; break;
//            case '2': *this += 2; break;
//            case '3': *this += 3; break;
//            case '4': *this += 4; break;
//            case '5': *this += 5; break;
//            case '6': *this += 6; break;
//            case '7': *this += 7; break;
//            case '8': *this += 8; break;
//            case '9': *this += 9; break;
//            default:
//                throw std::bad_cast();
//            }
//        }
//        else {
//            // hex
//            *this *= 16;
//            *this += hex2nib(*s);
//        }
//    }
//    return *this;
//}


address_t::address_t()
{
    fill(0);
}

address_t::address_t(const char *s):
    address_t()
{
    auto s_start = s;
    if (s_start == nullptr)
    {
        fill(0);
        return;
    }

    // skip leading "0x0.." prequel, if any
    if (*s_start == '0') ++s_start;
    if (*s_start == 'x') ++s_start;
    while (*s_start == '0') ++s_start;

    // fetch limits of readable string
    const char *s_read = s_start + std::strlen(s_start);
    const char *s_maxhead = s_read - nibs;
    if (s_maxhead < s_start) s_maxhead = s_start;

    // signal when to end loop: string read or array full
    auto end = [&](){ return s_read < s_maxhead; };

    // read string backward, one nib at a time
    // write values into the array backward, one word at a time
    for (auto w = rbegin(); !end(); ++w)
    {
        assert(w != rend());

        // init word
        *w = 0;
        unsigned shl = 0;

        // read word 1 nib at a time, backwards from string
        for (int i = 0; i < word_nibs; ++i)
        {
            s_read--;
            if (end()) break;
            *w |= (hex2nib(*s_read) << shl);
            shl += 4;
        }
    }

    //// make sure there is no overflow
    //if (s_read != s_start)
    //{
    //    throw std::overflow_error(s);
    //}
}


std::ostream& operator<< (std::ostream& stream, const address_t& o)
{
    char buf[address_t::nibs+1] = {0}; // +1 for EOL char
    char *w = buf + sizeof(buf) -1;

    auto *r = &o.back();
    auto write_nib = [&](unsigned b)
    {
        static const char hex[] = "0123456789abcdef";
        w--;
        *w = hex[b&0x0f];
    };

    for (unsigned nib = 0; nib < address_t::nibs; r--)
    {
        for (int i = 0; i < address_t::word_nibs; ++i, ++nib)
        {
            auto shr = i * 4;
            write_nib((*r) >> shr);
            nib++;
        }
    }

    stream << "0x" << w;

    return stream;
}



} // namespace model
} // namespace bofh


