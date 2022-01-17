#include <boost/multi_index_container.hpp>
#include <boost/multi_index/hashed_index.hpp>
#include <boost/multi_index/composite_key.hpp>
#include <boost/multi_index/member.hpp>
#include <boost/multi_index/ordered_index.hpp>
#include <boost/multi_index/mem_fun.hpp>
#include <boost/functional/hash.hpp>
#include <string>
#include <assert.h>
#include <iostream>

using namespace boost;
using namespace boost::multi_index;

// let's experiment with a more complex form of multiple indexing. It fits the
// application and is easy to use, but I've never stretched it this far.

struct Cat {
    // designed to be trivially indexable across different sets of its attributes:
    const unsigned int id;
    const unsigned int age;
    const std::string name;
    const Cat *parent;

    struct by_id{};
    struct by_age{};
    struct by_parent_and_name{};

    // this hash value combines age and parent in a repeatable way.
    // it is not meant to avoid duplicates
    std::size_t hashValue() const {
        std::size_t res = 0;
        hash_combine(res, age);
        hash_combine(res, parent);
        return res;
    }

    struct by_hash{};
};


// multi-index is heavily inspired by RDBMS indexes, and implements basically the same ideas
typedef multi_index_container<
  Cat,
  indexed_by<
          // this is how one primary key is elected (there can be more than one)
          // note that this is hashed, not ordered. Ordering is not preserved, but they run in O(1)
          hashed_unique     < tag<Cat::by_id>             ,  member       <Cat, const unsigned int, &Cat::id  > >
          // hashed indexes can also gain the benefit of supporting a multiples
        , hashed_non_unique < tag<Cat::by_age>            ,  member       <Cat, const unsigned int, &Cat::age > >
          // this is a composite key. Items can then be searched for one or more of the participating values,
          // but only in the appearing order (in this case it is impossible to seach by Cat::name only).
          // note: this can also be hashed_non_unique, which is good news. But in that case all key values
          //       must always be specified in every lookup. Partial lookups not supported, which is ok I guess.
        , ordered_non_unique< tag<Cat::by_parent_and_name>,  composite_key<Cat,
                 member<Cat, const Cat*, &Cat::parent>
               , member<Cat, const std::string, &Cat::name>               >
         >
          // index keys can also be computed on insertion by a member of global function. This is functionally
          // equivalent to having hashed_X_unique with a computed key.
        , hashed_non_unique< tag<Cat::by_hash>, const_mem_fun<Cat,std::size_t, &Cat::hashValue>
        >
  >
> Catorium;


int main()
{
    unsigned int id;
    const Cat mrow        {++id, 12, "mrow"     , nullptr };
    const Cat micigno     {++id, 8,  "micigno"  , &mrow   };
    const Cat santana     {++id, 10, "santana"  , &mrow   };
    const Cat sbocato     {++id, 8,  "sbocato"  , &santana};
    const Cat metricula   {++id, 8,  "metricula", &santana};
    const Cat efeso       {++id, 5,  "efeso"    , &mrow};
    Catorium registry;
    registry.emplace(mrow);
    registry.emplace(micigno);
    registry.emplace(santana);
    registry.emplace(sbocato);
    registry.emplace(metricula);
    registry.emplace(efeso);

    // some lookups by id
    {
        auto &idx = registry.get<Cat::by_id>();
        {
            auto i = idx.find(1); // mrow
            assert(i != idx.end());
            assert(i->id == 1);
        }
        {
            auto i = idx.find(5); // metricula
            assert(i != idx.end());
            assert(i->id == 5);
            assert(i->name == metricula.name);
        }
    }

    // lookup cats by age
    {
        auto &idx = registry.get<Cat::by_age>();
        {
            auto i = idx.equal_range(10); // santana
            assert(i.first != i.second);
            assert(i.first->name == "santana");
            i.first++;
            assert(i.first == i.second);
        }
        {
            auto i = idx.equal_range(8); // micigno, sbocato and metricula (random order)
            for (int j = 0; j < 3; ++j)
            {
                assert(i.first != i.second);
                assert(i.first->name == "micigno" || i.first->name == "sbocato" || i.first->name == "metricula");
                i.first++;
            }
            assert(i.first == i.second);
        }
    }

    // lookup cats composite index (parent, name)
    {
        auto &idx = registry.get<Cat::by_parent_and_name>();
        {
            auto i = idx.equal_range(boost::make_tuple(&santana, sbocato.name)); // sbocato
            assert(i.first != i.second);
            assert(i.first->name == "sbocato");
            i.first++;
            assert(i.first == i.second);
        }
        {
            auto i = idx.equal_range(&santana); // sbocato and metricula
            for (int j = 0; j < 2; ++j)
            {
                assert(i.first != i.second);
                assert(i.first->name == "sbocato" || i.first->name == "metricula");
                i.first++;
            }
            assert(i.first == i.second);
        }
    }

}
