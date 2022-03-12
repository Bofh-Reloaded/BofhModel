/**
 * @file bofh_fees.hpp
 * @brief Fees model. Applies to exchanges, pairs and tokens.
 */

#pragma once

#include "bofh_types.hpp"

namespace bofh {
namespace model {
namespace fees {


struct HasFees
{
    virtual ~HasFees() {}
    virtual int feesPPM() const = 0;
    virtual bool hasFees() const { return feesPPM() != 0; }
};


struct HasFixedFees: HasFees
{
    HasFixedFees() = default;
    HasFixedFees(const HasFixedFees &) = default;
    HasFixedFees(unsigned feesPPM);

    virtual int feesPPM() const;
    virtual bool hasFees() const;
    void setFeesPPM(unsigned val);
private:
    int m_feesPPM = 0;
};


struct HasParentFees: HasFixedFees
{
    using HasFixedFees::HasFixedFees;
    HasParentFees(const HasFees *parentFees);

    virtual int feesPPM() const;
    virtual bool hasFees() const;
private:
    const HasFees *m_parentFees = nullptr;
};


} // namespace fees
} // namespace model
} // namespace bofh

