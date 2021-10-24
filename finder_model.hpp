#pragma once

#include "finder_common.hpp"
#include <vector>
#include <set>


namespace bofh {
namespace model {

/**
 * @brief DeFi token identifier
 *
 * Identifies a tradable asset.
 *
 * @todo extend me.
 */
struct Token: Ref<Token>
{
    const string name;
    const string contract_id;

    Token(const string &name_): name(name_) {}
};




/**
 * An amount of value in one specific token
 */
struct Balance: Ref<Balance>
{
    typedef double amount_t; // TODO: needs reasonable fixed point math.
                             // I'm using double for simple testing of the overall machinery
                             // There is no "double" in finance.

    Token::ref token;
    amount_t amount;

    Balance(Token::ref token_, amount_t amount_):
        token(token_),
        amount(amount_)
    {
        assert(token != nullptr);
    }
};


/**
 * @brief A pair of tokens
 *
 * A pair represents a possibility to execute a swap
 * between two tokens. Either first->second, or second->first.
 * The swap between the two is subject to an exchange rate.
 *
 * @todo This of course ideal and needs to consider commissions and other costs.
 *       There's lots of real world stuff that belongs here.
 *
 * @todo consider to promote this to finite math instead of using double.
 *       There's no "double" in finance.
 *
 * @todo Missing defi exchange ref, contract id and stuff. All this to come later.
 */
struct Pair: std::pair<Token::ref, Token::ref>, Ref<Pair>
{
    typedef double rate_t;
    typedef std::pair<Token::ref, Token::ref> base_t;

    /// rate of change between tokens
    rate_t rate;

    void check()
    {
        assert(first != nullptr);
        assert(second != nullptr);
        assert(rate != 0.0f);
    }

    Pair(Token::ref first_, Token::ref second_, rate_t rate_):
        base_t(first_, second_),
        rate(rate_)
    {
        check();
    }

    Pair(const base_t &base_, rate_t rate_):
        base_t(base_),
        rate(rate_)
    {
        check();
    }

    /**
     * @brief execute a swap
     * @param in a balance in one of the tokens of the pair
     * @return a new balance object, in the *other* token, respective to @p src
     */
    Balance::ref swap(Balance::ref src) const
    {
        assert(src != nullptr);
        if (src->token == first)
        {
            // forward swap from first to second token
            return Balance::make(second, src->amount / rate);
        }
        else if (src->token == second)
        {
            return Balance::make(first, src->amount * rate);
        }
        else {
            // this is actually a bug. crash me ffs
            assert(src->token == first || src->token == second);
            return nullptr;
        }
    }

    /**
     * @brief construct a reciprocal pair
     */
    ref reciprocal(void) const
    {
        return Pair::make(second, first, 1.0/rate);
    }
};


/**
 * @brief a swap request
 *
 * It's a representation of the intent of swapping a balance of a
 * token toward a different wanted token.
 */
struct SwapRequest: Ref<SwapRequest>
{
    Balance::ref balance; ///< balance in a specific source token
    Token::ref wanted; ///< wanted token to swap to

    SwapRequest(Balance::ref balance_, Token::ref wanted_):
        balance(balance_),
        wanted(wanted_)
    {
        assert(balance != nullptr);
        assert(wanted != nullptr);
    }
};


/**
 * @brief Graph of possible swaps
 *
 * Let's approach the problem with a graph model.
 * All possible swaps between tokens are modeled as edges of a graph.
 * This is seen as a directed graph btw.
 *
 * Lots of interesting graph algorithms can be conveyed in ASIC or
 * massively parallel form, and their implementation is already known.
 *
 * We want to be in that neighborhood.
 */
struct TheGraph: Ref<TheGraph> {

    /**
     * The graph is modeled as a list of nodes.
     *
     * @rant Look, we all know the ritual textbook representation of a
     *       graph is list<Edge>. Yeah, we are not using that.
     *
     *       This model, it's not ideal, nor it is flexible.
     *       I'm paying the tradeoff of a cumbersome implementation
     *       but in exchange I aim at using this new fancy lookup table.
     *
     *       If does lookups in constant O(1), nanosecond-scale time.
     *       It's called RAM addressing.
     *
     *       So sue me.
     *
     * A node is *strongly identified* either by a token and carries a
     * number of possible exchange pairs.
     * (They can be redundant in their destination token).
     *
     * Each pair in a node represent an *outgoing* edge from the node.
     *
     * @runtime_guarantee foreach p in pairs: node.token == p.first
     * @runtime_guarantee foreach p in pairs: node.token != p.second
     */
    struct Node: Ref<Node>
    {
        Token::ref token; // for now let's just say that a graph node is 1:1 identified by token

        // one moves walks the graph by executing token swaps. Therefore an Edge is 1:1 with possible token swaps
        struct Edge: Ref<Edge>, std::vector<Pair::ref>
        {
            Node::ref landing; ///< next graph node we land to, if a swap is executed with using this pair
            Pair::ref pair; ///< the token pair swap represented by this graph edge

            Edge(Node::ref landing_, Pair::ref pair_):
                landing(landing_),
                pair(pair_)
            {
                assert(landing != nullptr);
                assert(pair != nullptr);
                assert(landing->token == pair->second);
            }
        };
        struct EdgeList: Ref<EdgeList>, std::vector<Edge::ref> {};

        Node(Token::ref token_): token(token_) {}

        EdgeList edges;
    };

    // this is used to instate a smarter than default RB-tree interal ordering for the NodeList set later
    // (it must be scanned by node token within O(log N) time).
    // @note Beware of a using lambdas. They have different anonymous typing across build domains.
    struct node_ordering
    {                                                                         // vvvv the only important bit
        template<typename A, typename B> bool operator()(A&& a, B&& b) const  { return a->token < b->token; }
    };

    /**
     * @brief a list of nodes
     *
     * This is a std::set in disguise. It has a special comparator
     * that allows it to perform O(log N) lookups when looking up
     * nodes by their associated node.
     *
     * @see node_ordering
     *
     * @todo promote this to std::unordered_set. It may bring an additional
     *       runtime boost and gets rid of node_ordering.
     *       This type of lookup shouldn't be used in time-critical
     *       graph traversals anyway.
     */
    struct NodeList: std::set<Node::ref, node_ordering>
    {
        std::shared_ptr<int> a;

        /**
         * @brief find a graph node by its token
         *
         * If the list does not contain a node for the said @p token, a new
         * one is created, introduced and returned
         *
         * @return node reference
         */
        Node::ref node_for_token(Token::ref token)
        {
            auto res = find(Node::make(token)); // FIXME: pissing away almost half usec, oh my unconcerned me
            if (res == cend())
            {
                auto res = Node::make(token);
                insert(res);
                return res;
            }
            return *res;
        }
    };


    NodeList nodes;


    /**
     * @brief add a possible pair swap, make it known to the graph
     * @note There can be multiple pairs for the same two tokens. It's legal and expected
     *
     * @todo This is wrong in a number of ways, but we need something to start from.
     *
     * @return reference to the graph node involved in this swap's starting token
     */
    Node::ref add_pair(Pair::ref pair)
    {
        assert(pair != nullptr);

        auto from_node = nodes.node_for_token(pair->first);
        auto to_node = nodes.node_for_token(pair->second);


        assert(from_node != nullptr);
        assert(to_node != nullptr);
        from_node->edges.emplace_back(Node::Edge::make(to_node, pair));

        return from_node;
    }
};


} // namespace model
} // namespace bofh
