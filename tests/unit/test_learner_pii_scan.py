# EDU-C2-042 — Unit Tests: learner_pii_scan (BL-10..BL-15)

from src.services.learner_pii_scan import contains_learner_identifier, contains_learner_identifier_text


class TestContainsLearnerIdentifier:
    def test_clean_payload_not_flagged(self):
        """BL-10: an ordinary resource-metadata payload is not flagged."""
        assert contains_learner_identifier('[{"resource_id": "R1", "title": "Algebra Basics"}]') is False

    def test_forbidden_key_flagged(self):
        """BL-11: a payload embedding a forbidden learner-identifier key is flagged."""
        assert contains_learner_identifier('[{"student_id": "12345"}]') is True

    def test_email_pattern_flagged(self):
        """BL-12: an email address anywhere in the payload text is flagged."""
        assert contains_learner_identifier('{"creator": "taro.yamada@example.jp"}') is True

    def test_empty_input_not_flagged(self):
        assert contains_learner_identifier("") is False


class TestContainsLearnerIdentifierText:
    def test_clean_prose_not_flagged(self):
        """BL-13: ordinary remediation-hint prose is not flagged."""
        assert contains_learner_identifier_text("Add a valid licence field to this resource.") is False

    def test_cue_phrase_flagged(self):
        """BL-14: a free-text cue phrase (e.g. 'student ID') is flagged."""
        assert contains_learner_identifier_text("Contact the student ID owner for correction.") is True

    def test_email_in_text_flagged(self):
        """BL-15: an email address embedded in generated prose is flagged."""
        assert contains_learner_identifier_text("Reach out to admin@example.jp for details.") is True
