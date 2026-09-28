from mosje.outreach import DISCOVERY_TEMPLATE_EN, discovery_item, eligible_item


def test_discovery_template_rendered_without_eligibility_claim():
    item = discovery_item({"roll_no": "1", "candidate_name": "KUMARI PRIYA", "class_passed": "X",
                           "mobile": "9876543210"}, {"overall_score": 84.2, "scenario_label": "31"})
    assert item["Outreach_Status"] == "QUEUE_FOR_DISCOVERY_OUTREACH"
    assert item["Message_EN"].startswith("Namaste Priya,")
    assert "CBSE Class X examination" in item["Message_EN"]
    assert "eligible" not in item["Message_EN"].lower()
    assert "{{" not in item["Message_EN"] + item["Message_HI"]
    assert "[Button: Find scholarships for me]" in DISCOVERY_TEMPLATE_EN


def test_discovery_needs_valid_cbse_mobile():
    item = discovery_item({"roll_no": "1", "candidate_name": "Aarav", "class_passed": "XII", "mobile": "123"}, {})
    assert item["Sendable"].startswith("NO")


def test_eligible_item_falls_back_to_jan_aadhaar_mobile():
    s = {"Eligible_Scheme_Count": 2, "Eligible_Scheme_IDs": "MSM-0001; MSM-0002"}
    item = eligible_item({"roll_no": "1", "candidate_name": "Aarav Sharma", "class_passed": "X", "mobile": ""},
                         {"member_id": "M1", "mobile": "9123456789"}, s, ["A", "B"])
    assert item["Mobile"] == "9123456789" and item["Contact_Source"] == "Jan Aadhaar"
    assert "2 government" in item["Message_EN"]
