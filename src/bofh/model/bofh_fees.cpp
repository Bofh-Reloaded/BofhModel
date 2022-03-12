#include "bofh_fees.hpp"
namespace bofh {
namespace model {
namespace fees {


HasFixedFees::HasFixedFees(unsigned feesPPM)
    : m_feesPPM(feesPPM)
{}

int HasFixedFees::feesPPM() const
{
    return m_feesPPM;
}

bool HasFixedFees::hasFees() const
{
    return m_feesPPM > 0;
}

void HasFixedFees::setFeesPPM(unsigned val)
{
    m_feesPPM = val;
}

HasParentFees::HasParentFees(const HasFees *parentFees)
    : m_parentFees(parentFees)
{}


int HasParentFees::feesPPM() const
{
    if (HasFixedFees::hasFees())
    {
        return HasFixedFees::feesPPM();
    }
    if (m_parentFees != nullptr)
    {
        return m_parentFees->feesPPM();
    }
    return 0;
}

bool HasParentFees::hasFees() const
{
    return HasFixedFees::hasFees() ||
            (m_parentFees != nullptr && m_parentFees->hasFees());
}



} // namespace fees
} // namespace model
} // namespace bofh

