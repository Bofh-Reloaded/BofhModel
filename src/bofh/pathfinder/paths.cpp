#include "paths.hpp"
#include "../commons/bofh_log.hpp"
#include "../model/bofh_model.hpp"
#include <assert.h>
#include <sstream>

namespace bofh {
namespace pathfinder {

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
    ss << "  \\_ initial balance is " << initial_balance << std::endl;
    ss << "  \\_ final balance is   " << balance << std::endl;
    ss << "  \\_ yield is           " << yieldPercent << std::endl;
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


