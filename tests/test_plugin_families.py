import importlib
import unittest

from plugin_family_fixtures import API_CASES, FEDORA_CASES, FYDEOS_CASES, GARUDA_CASES, MINT_CASES, UBUNTU_CASES, FixtureContext


class PluginFamilyTests(unittest.TestCase):
    def _run_case(self, case) -> None:
        module = importlib.import_module(case.module_name)
        context = FixtureContext(
            link_pages=case.link_pages,
            text_pages=case.text_pages,
            final_urls=case.final_urls,
        )
        candidates = module.discover(context)

        self.assertEqual(len(candidates), len(case.expected))
        for candidate, expected in zip(candidates, case.expected, strict=True):
            self.assertEqual(candidate.url, expected.url)
            self.assertEqual(candidate.filename, expected.filename)
            self.assertEqual(candidate.version, expected.version)
            self.assertEqual(candidate.arch, expected.arch)
            self.assertEqual(candidate.source_page, expected.source_page)
            self.assertEqual(candidate.priority, expected.priority)
            self.assertEqual(candidate.torrent_url, expected.torrent_url)
            self.assertEqual(candidate.notes, expected.notes)

    def test_fedora_family_cases(self) -> None:
        for case in FEDORA_CASES:
            with self.subTest(case=case.label):
                self._run_case(case)

    def test_ubuntu_family_cases(self) -> None:
        for case in UBUNTU_CASES:
            with self.subTest(case=case.label):
                self._run_case(case)

    def test_mint_family_cases(self) -> None:
        for case in MINT_CASES:
            with self.subTest(case=case.label):
                self._run_case(case)

    def test_garuda_family_cases(self) -> None:
        for case in GARUDA_CASES:
            with self.subTest(case=case.label):
                self._run_case(case)

    def test_api_backed_family_cases(self) -> None:
        for case in API_CASES:
            with self.subTest(case=case.label):
                self._run_case(case)

    def test_fydeos_family_cases(self) -> None:
        for case in FYDEOS_CASES:
            with self.subTest(case=case.label):
                self._run_case(case)


if __name__ == "__main__":
    unittest.main()
