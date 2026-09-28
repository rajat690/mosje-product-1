"""Outreach queue builder.

Two message types:
  QUEUE_FOR_OUTREACH            - MATCHED + >=1 eligible scheme (Eligibility Rule 7.13)
  QUEUE_FOR_DISCOVERY_OUTREACH  - PROBABLE band (Linkage Rules V3.0, 'PROBABLE band' section)

The Discovery template text is copied verbatim from the Linkage Rules V3.0 document.
NOTE: the Linkage doc does not contain an eligible-shortlist template (it only says one exists and is
different). ELIGIBLE_TEMPLATE_EN below is a PROTOTYPE DRAFT written for this demo and is clearly
labelled as such - it needs departmental / WhatsApp BSP approval.
"""
from __future__ import annotations

from .normalize import first_name, valid_mobile

DISCOVERY_TEMPLATE_NAME_EN = "scholarship_discovery_invite_en"
DISCOVERY_TEMPLATE_NAME_HI = "scholarship_discovery_invite_hi"
DISCOVERY_TEMPLATE_EN = """Namaste {{1}},

Congratulations on passing your CBSE Class {{2}} examination.

Many government scholarships support students who are continuing
their studies. Answer a few quick questions (about 2 minutes) and
we will show you scholarships you can explore.

[Button: Find scholarships for me]

Reply STOP to stop receiving these messages."""

DISCOVERY_TEMPLATE_HI = """नमस्ते {{1}},

CBSE कक्षा {{2}} की परीक्षा उत्तीर्ण करने पर बधाई।

आगे की पढ़ाई जारी रखने वाले विद्यार्थियों के लिए कई सरकारी
छात्रवृत्तियाँ उपलब्ध हैं। कुछ आसान सवालों के जवाब दीजिए
(लगभग 2 मिनट) और हम आपको वे छात्रवृत्तियाँ दिखाएँगे जिनके
बारे में आप जानकारी ले सकते हैं।

[बटन: मेरे लिए छात्रवृत्ति खोजें]

ये संदेश बंद करने के लिए STOP लिखें।"""

ELIGIBLE_TEMPLATE_NAME_EN = "scholarship_eligible_shortlist_en (PROTOTYPE DRAFT - not in spec)"
ELIGIBLE_TEMPLATE_EN = """Namaste {{1}},

Congratulations on passing your CBSE Class {{2}} examination.

Based on your details, you may be eligible for {{3}} government
scholarship(s), including: {{4}}.

Tap below to see the full list, documents needed and how to apply.

[Button: View my scholarships]

Reply STOP to stop receiving these messages."""


def render(template: str, *values) -> str:
    out = template
    for i, v in enumerate(values, start=1):
        out = out.replace("{{%d}}" % i, str(v))
    return out


def clean_mobile(m) -> str:
    import re
    s = re.sub(r"\D", "", str(m or ""))
    return s[-10:] if valid_mobile(s) else ""


def eligible_item(cbse: dict, member: dict, summary: dict, top_names: list[str]) -> dict:
    mob, src = clean_mobile(cbse.get("mobile")), "CBSE"
    if not mob:
        mob, src = clean_mobile(member.get("mobile")), "Jan Aadhaar"
    fn = first_name(cbse.get("candidate_name")) or first_name(member.get("nameEng"))
    cls = cbse.get("class_passed", "")
    msg = render(ELIGIBLE_TEMPLATE_EN, fn, cls, summary["Eligible_Scheme_Count"], "; ".join(top_names))
    return {
        "Outreach_Status": "QUEUE_FOR_OUTREACH", "Message_Type": "Eligible shortlist",
        "Template_Name": ELIGIBLE_TEMPLATE_NAME_EN, "Roll_No": cbse["roll_no"],
        "Candidate_Name": cbse.get("candidate_name"), "First_Name": fn, "Class_Passed": cls,
        "Linked_Member_ID": member.get("member_id"), "Mobile": mob, "Contact_Source": src if mob else "",
        "Sendable": "YES" if mob else "NO - no valid mobile on CBSE or Jan Aadhaar record",
        "Eligible_Scheme_Count": summary["Eligible_Scheme_Count"],
        "Top_Schemes_In_Message": "; ".join(top_names),
        "Eligible_Scheme_IDs": summary["Eligible_Scheme_IDs"],
        "Message_EN": msg, "Message_HI": "(Hindi eligible template not provided in spec)",
    }


def discovery_item(cbse: dict, decision: dict) -> dict:
    mob = clean_mobile(cbse.get("mobile"))
    fn = first_name(cbse.get("candidate_name"))
    cls = cbse.get("class_passed", "")
    return {
        "Outreach_Status": "QUEUE_FOR_DISCOVERY_OUTREACH", "Message_Type": "Discovery invite",
        "Template_Name": f"{DISCOVERY_TEMPLATE_NAME_EN} / {DISCOVERY_TEMPLATE_NAME_HI}",
        "Roll_No": cbse["roll_no"], "Candidate_Name": cbse.get("candidate_name"), "First_Name": fn,
        "Class_Passed": cls, "Linked_Member_ID": "", "Mobile": mob,
        "Contact_Source": "CBSE" if mob else "",
        "Sendable": "YES" if mob else "NO - no valid mobile on CBSE record (spec: no Discovery outreach sent)",
        "Eligible_Scheme_Count": "", "Top_Schemes_In_Message": "(none - no eligibility claim)",
        "Eligible_Scheme_IDs": "",
        "Best_Candidate_Score": decision.get("overall_score"), "Scenario": decision.get("scenario_label"),
        "Message_EN": render(DISCOVERY_TEMPLATE_EN, fn, cls),
        "Message_HI": render(DISCOVERY_TEMPLATE_HI, fn, cls),
    }
