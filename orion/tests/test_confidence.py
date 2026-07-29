# pylint: disable=missing-class-docstring,missing-function-docstring
"""Tests for confidence indicators module."""

from orion.confidence import ConfidenceResult, _map_label


class TestMapLabel:
    def test_likely_real_large_shift(self):
        assert _map_label(0.01, 1.0) == "Likely real (large shift)"

    def test_likely_real_moderate_shift(self):
        assert _map_label(0.01, 0.6) == "Likely real (moderate shift)"

    def test_possible_small_shift(self):
        assert _map_label(0.01, 0.3) == "Possible (small shift)"

    def test_significant_but_trivial(self):
        assert _map_label(0.01, 0.1) == "Statistically significant but trivial"

    def test_noise_high_p_value(self):
        assert _map_label(0.3, 1.5) == "Noise (trivial shift)"

    def test_boundary_p_value_at_005(self):
        assert _map_label(0.05, 1.0) == "Noise (trivial shift)"

    def test_boundary_cohens_d_at_08(self):
        assert _map_label(0.01, 0.8) == "Likely real (large shift)"

    def test_boundary_cohens_d_at_05(self):
        assert _map_label(0.01, 0.5) == "Likely real (moderate shift)"

    def test_boundary_cohens_d_at_02(self):
        assert _map_label(0.01, 0.2) == "Possible (small shift)"

    def test_infinity_cohens_d(self):
        assert _map_label(0.001, float("inf")) == "Likely real (large shift)"


class TestConfidenceResult:
    def test_dataclass_fields(self):
        result = ConfidenceResult(
            p_value=0.01,
            cohens_d=1.2,
            confidence_label="Likely real (large shift)",
            sufficient_data=True,
            sample_size_before=10,
            sample_size_after=5,
        )
        assert result.p_value == 0.01
        assert result.cohens_d == 1.2
        assert result.sufficient_data is True

    def test_insufficient_data_result(self):
        result = ConfidenceResult(
            p_value=None,
            cohens_d=None,
            confidence_label="Insufficient data",
            sufficient_data=False,
            sample_size_before=5,
            sample_size_after=1,
        )
        assert result.sufficient_data is False
        assert result.p_value is None
