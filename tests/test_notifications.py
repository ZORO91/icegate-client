import pytest

from icegate_client.notifications import filing_events, parse_notification


def msg(text):
    return parse_notification(text)


def test_submitted_and_rejected_by_job():
    ok = msg("Dear Sir/Madam,\nYour bill of entry filing with job no. 113 dated 20261105 has been successfully submitted.\nRegards")
    assert (ok["outcome"], ok["doc"], ok["job"], ok["date"]) == ("submitted", "BE", "113", "2026-11-05")
    bad = msg('"Your bill of entry filing with job no. 112 dated 05112026 has been rejected. Error code: 820_SUPPDOCS\n-CBIC "')
    assert (bad["outcome"], bad["job"], bad["date"], bad["detail"]) == ("rejected", "112", "2026-11-05", "error code 820_SUPPDOCS")
    assert msg('"Your shipping bill filing with job no. 952 dated 07112026 has been rejected.')["detail"] == ""


def test_a_document_number_is_not_a_job_number():
    event = msg("Your bill of entry filing with be no. 4836195 dated 20261103 has been successfully submitted.")
    assert event["job"] is None and event["number"] == "4836195"


@pytest.mark.parametrize("stage", ["Header", "Field", "DSC"])
def test_validation_failures_carry_the_control_number_as_job(stage):
    event = msg(f"Dear Sir/Madam,\n{stage} validation failed for control no. 113, filing date 20261105, "
                "Receiver ID INHDD6, message ID CACHI01. Please use a valid input file.")
    assert (event["outcome"], event["job"], event["date"], event["location"]) == ("failed", "113", "2026-11-05", "INHDD6")
    assert event["detail"].startswith(stage.lower())


def test_field_errors_are_included():
    event = msg("Field validation failed for control no. 721, filing date 20261103, Receiver ID INTKD6, message ID X. "
                "Please use a valid input file.\n\n\nErrors: finalInvoiceModel[0].buyerAddress1: too long")
    assert "buyerAddress1" in event["detail"]


def test_unrelated_messages_are_ignored_and_order_is_kept():
    rows = [{"message": "Your shipping bill filing has been successfully generated with SB number 8536843.\n-CBIC"},
            {"message": "Your bill of entry filing with job no. 1 dated 20261105 has been rejected.", "createdDate": "09.11.2026"},
            {"message": "You have successfully changed your ICEGATE password."}]
    events = filing_events(rows)
    assert [e["job"] for e in events] == ["1"] and events[0]["created"] == "09.11.2026"


def test_unexpected_payload_is_an_error():
    with pytest.raises(Exception):
        filing_events({"error": "x"})


def test_greeting_signoff_and_quotes_are_removed():
    assert msg("Dear Sir/Madam,\nYour bill of entry filing with job no. 1 dated 20261105 has been successfully submitted.\n"
               "Regards,\nICEGATE Support Team")["message"] == \
        "Your bill of entry filing with job no. 1 dated 20261105 has been successfully submitted."
    assert msg('"Your bill of entry filing with job no. 1 dated 05112026 has been rejected. Error code: 820_SUPPDOCS\n-CBIC "')["message"] == \
        "Your bill of entry filing with job no. 1 dated 05112026 has been rejected. Error code: 820_SUPPDOCS"
