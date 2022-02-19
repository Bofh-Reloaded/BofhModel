#include "paths.hpp"
#include "../commons/bofh_log.hpp"
#include "../model/bofh_model.hpp"
#include <boost/functional/hash.hpp>
#include <assert.h>
#include <sstream>

namespace bofh {
namespace pathfinder {

static std::size_t m_calcPathHash(const Path &p)
{
    std::size_t h = 0U;
    for (unsigned i = 0; i < p.size(); ++i)
    {
        boost::hash_combine(h, p[i]->pool->address);
    }
    return h;
}

Path::Path(value_type v0
     , value_type v1
     , value_type v2)
    : base_t{v0, v1, v2}
    , type(PATH_3WAY)
    , m_hash(m_calcPathHash(*this))
{ }

Path::Path(value_type v0
     , value_type v1
     , value_type v2
     , value_type v3)
    : base_t{v0, v1, v2, v3}
    , type(PATH_4WAY)
    , m_hash(m_calcPathHash(*this))
{ }


std::string Path::print_addr() const
{
    std::stringstream ss;
    for (auto i = 0; i < size(); ++i)
    {
        auto swap = get(i);
        if (i > 0) ss << ", ";
        ss << "\"" << swap->tokenSrc->address << "\"";
    }
    ss << ", " << get(size()-1)->tokenDest->address;
    return ss.str();
}

std::string Path::print_symbols() const
{
    std::stringstream ss;
    for (auto i = 0; i < size(); ++i)
    {
        auto swap = get(i);
        if (i > 0) ss << "-";
        ss << swap->tokenSrc->symbol;
    }
    ss << "-" << get(size()-1)->tokenDest->symbol;
    return ss.str();
}



std::string PathResult::infos() const
{
    std::stringstream ss;
    ss << path->size() << "-way path is " << path->print_symbols() << std::endl;
    ss << "  \\_ address vector is  " << path->print_addr() << std::endl;
    ss << "  \\_ initial balance is " << initial_balance() << std::endl;
    ss << "  \\_ final balance is   " << final_balance() << std::endl;
    ss << "  \\_ yield is           " << yieldRatio << std::endl;
    return ss.str();
}

std::ostream& operator<< (std::ostream& stream, const Path& o)
{
    stream << o.print_symbols();
    return stream;
}

std::ostream& operator<< (std::ostream& stream, const PathResult& o)
{
    stream << o.infos();
    return stream;
}

} // namespace pathfinder
} // namespace bofh


