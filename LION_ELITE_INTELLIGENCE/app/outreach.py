from dataclasses import dataclass


@dataclass
class OutreachMessage:
    subject: str
    body: str


SIGNATURE = """Best,
Alexander Ringfield
Lion Elite Beauty
440-348-9591
https://www.lionelitebeauty.com

To opt out of future outreach, reply with REMOVE.
"""


def build_partnership_email(lead) -> OutreachMessage:
    first_name = (lead.owner_name or "there").split()[0]
    business = lead.company_name
    category = lead.category.lower()
    city = lead.city or "your market"
    angle = lead.partnership_angle or "a referral and affiliate partnership"

    subject = f"Partnership idea for {business}"
    body = f"""Hi {first_name},

I came across {business} and wanted to reach out because your work in {category} looks aligned with the partnerships we are building through Lion Elite Beauty.

We help clients with personalized fitness and lifestyle coaching, accountability, recovery education, and long-term transformation systems. We are also building relationships with owner-operated gyms, trainers, coaches, recovery studios, and wellness businesses across the country.

For {business}, I believe there may be an opportunity around {angle.lower()} in {city}.

The goal is not to replace what you already do. It is to help your clients receive stronger ongoing support while giving your business another potential referral and revenue channel.

If you could create more value for your clients and add a new revenue opportunity without adding a large operational burden, how quickly would you want to explore it?

Would you be open to a short conversation?

{SIGNATURE}"""
    return OutreachMessage(subject=subject, body=body)


def build_follow_up_email(lead, follow_up_number: int) -> OutreachMessage:
    first_name = (lead.owner_name or "there").split()[0]
    business = lead.company_name

    if follow_up_number == 1:
        subject = f"Following up — {business}"
        body = f"""Hi {first_name},

I wanted to follow up in case my previous message got buried.

We are building a select network of coaches, trainers, gyms, recovery studios, and wellness businesses that want to improve client support while creating an additional referral or affiliate revenue opportunity.

Would a brief conversation be worth exploring for {business}?

{SIGNATURE}"""
    else:
        subject = f"Should I close the loop with {business}?"
        body = f"""Hi {first_name},

I have not heard back, so I wanted to close the loop respectfully.

If a Lion Elite Beauty coaching, referral, or affiliate partnership could be useful for {business}, reply with "LET'S TALK" and I will reach out personally.

Otherwise, no problem at all.

{SIGNATURE}"""

    return OutreachMessage(subject=subject, body=body)
