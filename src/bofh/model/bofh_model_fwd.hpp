#pragma once

#include <string>

namespace bofh {
namespace model {

struct Token;
struct Balance;
struct SwapPair;
struct TheGraph;

// TODO: for the love of all that is holy and fast running,
// change me in some derivation of a fixed size std::array<uint8_t>.
// ASAP please.
typedef std::string address_t;

} // namespace model
} // namespace bofh
