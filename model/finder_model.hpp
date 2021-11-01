#pragma once

#include "finder_common.hpp"
#include "finder_model_fwd.hpp"
#include "main_index_fwd.hpp"
#include <vector>


namespace bofh {
namespace model {


typedef std::string address_t;

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

    Token(const string &name_): name(name_) {}

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
    const address_t address;

    Token::ref token0;
    Token::ref token1;

    typedef double rate_t;

    rate_t rate;

    void check()
    {
        assert(token0 != nullptr);
        assert(token1 != nullptr);
        assert(rate != 0.0f);
    }

    SwapPair(Token::ref token0_, Token::ref token1_, rate_t rate_):
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
        return SwapPair::make(token1, token0, 1.0/rate);
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
    MainIndex *index;

    TheGraph();
};



} // namespace model
} // namespace bofh
