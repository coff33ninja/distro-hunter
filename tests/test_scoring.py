import unittest

from distro_hunter.models import Candidate
from distro_hunter.scoring import choose_best, score_candidate


class ScoringTests(unittest.TestCase):
    def test_iso_candidate_beats_signature(self) -> None:
        iso = Candidate(
            url="https://example.org/ubuntu-24.04.4-desktop-amd64.iso",
            filename="ubuntu-24.04.4-desktop-amd64.iso",
            version="24.04.4",
        )
        sig = Candidate(
            url="https://example.org/ubuntu-24.04.4-desktop-amd64.iso.sig",
            filename="ubuntu-24.04.4-desktop-amd64.iso.sig",
            version="24.04.4",
        )
        self.assertGreater(score_candidate(iso), score_candidate(sig))
        self.assertEqual(choose_best([sig, iso]), iso)

    def test_newer_version_wins_when_scores_tie(self) -> None:
        older = Candidate(url="https://example.org/a.iso", filename="a.iso", version="24.04.3", priority=5)
        newer = Candidate(url="https://example.org/b.iso", filename="b.iso", version="24.04.4", priority=5)
        self.assertEqual(choose_best([older, newer]), newer)


if __name__ == "__main__":
    unittest.main()

