#pragma once

#include <bofh/model/bofh_model_fwd.hpp>
#include <functional>
#include <cstring>

namespace bofh {
namespace pathfinder {

using OperableSwap = model::OperableSwap;


typedef enum {
    PATH_3WAY = 3,
    PATH_4WAY = 4,
} PathLength;
constexpr auto MAX_PATHS = PATH_4WAY;

/**
 * @brief The Path struct
 *
 * Describes a sequential chain of swaps.
 * The chain can accomodate various notable lengths. @see PathLength
 *
 * It extends std::array for improved usability. It's a POD,
 * trivially copyable and uses no heap.
 */
struct Path: std::array<const OperableSwap *, MAX_PATHS>
{
    typedef std::array<const OperableSwap *, MAX_PATHS> base_t;
    typedef const OperableSwap * value_type;

    PathLength type;

    Path() = delete;

    Path(value_type v0
         , value_type v1
         , value_type v2)
        : base_t{v0, v1, v2}
        , type(PATH_3WAY)
    { }

    Path(value_type v0
         , value_type v1
         , value_type v2
         , value_type v3)
        : base_t{v0, v1, v2, v3}
        , type(PATH_4WAY)
    { }

    /**
     * @brief returns number of swaps in the chain
     */
    unsigned int size() const noexcept { return static_cast<unsigned int>(type); }

    /**
     * @brief read element at position @p idx
     */
    value_type get(unsigned int idx) const noexcept { return operator[](idx); }

    /**
     * @brief callback type
     *
     * Algos that discover Path3Way objects don't simply add them to lists
     * to be passed arount.
     * They invoke a callback functor upon discovery of a valid path,
     * and whatever is at the other end gets the notification.
     *
     * This saves on memory and time.
     */
    typedef std::function<void(const Path *)> listener_t;
};




} // namespace pathfinder
} // namespace bofh

