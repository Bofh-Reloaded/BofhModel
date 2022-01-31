#pragma once

#include <cstdlib>
#include <cinttypes>
#include <utility>
#include <assert.h>
#include <memory>

using std::string;


/**
 * This is our memory model. It's implemented similarly as an Aspect.
 *
 * We can use raw pointers, shared_ptr or unique_ptr.
 *
 * At the moment i'm using shared_ptr for safety and gc.
 * It's slower at startup time, but dereferences have no runtime impact
 * (with a decent compiler).
 * We don't plan to do many allocations and pointer copying around so this
 * shouldn't really have a core speed impact.
 *
 * Last resort, we can boost speed by switching to unique_ptr
 * or raw pointers, but this takes a some careful design legwork.
 *
 * In the meanwhile I am placing an hard requirement for the rest of the code
 * to observe this contract. Might come in handy later.
 */
template<typename T> struct Ref
{
//    // step 1 - slower, safe gc memory model:
//    typedef std::shared_ptr<T> ref;
//    template <typename ... Args>
//    static ref make(Args&& ... args)
//    {
//        return std::make_shared<T>(std::forward<Args>(args)...);
//    }

//    // step 2 - unique_ptr. Not really convinced this is ideal.
//    typedef std::unique_ptr<T> ptr;
//    typedef ptr               &ref;
//    template <typename ... Args> static ptr make(Args&& ... args)
//    {
//        return std::make_unique<T>(std::forward<Args>(args)...);
//    }

    // Screw it. More speed below.

    // step 3 - using raw pointers. Might become necessary if moving
    // over to CUDA, ASIC or other silicon booster.
    //typedef T *ref;
    template <typename ... Args> static T *make(Args&& ... args)
    {
        return new T(std::forward<Args>(args)...);
    }

};

/**
 * Idiomatically cast constness away from stuff
 */
template<typename T> T& nonconst(const T& o) { return const_cast<T&>(o); }

