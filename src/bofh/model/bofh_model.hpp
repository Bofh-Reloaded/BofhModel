#pragma once

#include "bofh_common.hpp"
#include "bofh_model_fwd.hpp"
#include "bofh_entity_idx_fwd.hpp"
#include <vector>


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
    const address_t address;

    Token(const string &name_, const address_t &address_): name(name_), address(address_) {}

    struct SwapList: std::vector<SwapPair*> {};

    SwapList swaps;
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
 * @brief A swap between two tokens
 *
 * A SwapPair represents a possibility to execute a swap
 * between two tokens. It corresponds to a liquidity pool in the blockchain.
 *
 * @todo This of course ideal and needs to consider commissions and other costs.
 *       There's lots of real world stuff that belongs here.
 *
 * @todo consider to promote this to finite math instead of using double.
 *       There's no "double" in finance.
 *
 * @todo Missing defi exchange ref, contract id and stuff. All this to come later.
 */
struct SwapPair: Ref<SwapPair> {
    typedef double rate_t;

    const address_t address;
    const Token::ref token0;
    const Token::ref token1;
    rate_t rate;

    void check()
    {
        assert(token0 != nullptr);
        assert(token1 != nullptr);
        assert(rate != 0.0f);
    }

    SwapPair(const address_t &address_
             , const Token::ref token0_
             , const Token::ref token1_
             , rate_t rate_):
        address(address_),
        token0(token0_),
        token1(token1_),
        rate(rate_)
    {
        check();
    }


    Balance::ref swap(const Balance::ref &src) const
    {
        assert(src != nullptr);
        assert(src->token == token0);
        enum { this_has_been_properly_investigated = false };
        assert(this_has_been_properly_investigated);

        return Balance::make(token1, swap(src->amount));
    }

    Balance::amount_t swap(Balance::amount_t in) const
    {
        return in / rate;
    }

    /**
     * @brief construct a reciprocal pair
     */
    ref reciprocal(void) const
    {
        return SwapPair::make(address, token1, token0, 1.0/rate);
    }
};





/**
 * @brief Graph of known tokens and swaps paths
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

    // This is to clarify what in this graph is a node and and edge:
    typedef Token Node;
    typedef SwapPair Edge;
    // ... nodes are tokens, edges connecting them are swap pairs. Note that
    //     swaps are not bidirectional at the moment. Therefore this is
    //     a directed graph.

    typedef std::vector<Node*> NodeList;

    NodeList nodes;
    idx::EntityIndex *index;

    TheGraph();

    /**
     * @brief Introduce a new token node into the graph, if not existing.
     * If the token already exists, do nothing and return its reference.
     * @param name
     * @param address
     * @return reference to the token graph node
     */
    const Token *add_token(const std::string &name, const address_t &address);

    /**
     * @brief Introduce a new swap pair edge into the graph, if not existing.
     * If the pair already exists, do nothing and return its reference.
     * @param address
     * @param token0
     * @param token1
     * @param rate
     * @return reference to the swap pair
     */
    const SwapPair *add_swap_pair(const address_t &address
                            , const Token::ref token0
                            , const Token::ref token1
                            , SwapPair::rate_t rate);

    /**
     * @brief fetch a known token node
     * @param address
     * @return reference to the token node, if existing. Otherwise nullptr
     */
    const Token *lookup_token(const address_t &address);

    /**
     * @brief fetch a known swap pair edge
     * @param address
     * @return reference to the swap pair, if existing. Otherwise nullptr
     */
    const SwapPair *lookup_swap_pair(const address_t &address);

};



} // namespace model
} // namespace bofh
