"""A page imports a name the shared module does not export.

v10.2 github 5d65674359a4: wave 6 wrote OrganizationPage.jsx importing
`getOrganization` from src/api.js while its api.js rewrite was refused; each
later api.js rewrite dropped another export (getRepository, getOrganizations,
createOrganization) and the frontend build stayed broken for every wave after.
"""
import unittest

from generation_checks import check_batch, missing_export_errors

API = ("import {requestJson} from './shared/request.js';\n"
       "export function getRepository(id) { return requestJson(`/api/repos/${id}`); }\n"
       "export const listRepos = () => requestJson('/api/repos');\n"
       "async function load() {}\nexport {load as loadAll};\n")


class MissingExportTests(unittest.TestCase):
    def test_should_flag_a_new_import_of_a_name_the_module_does_not_export(self):
        sources = {"frontend/src/api.js": API,
                   "frontend/src/pages/Org.jsx": "import {getOrganization, listRepos} from '../api.js';\n"}
        errors = missing_export_errors(sources, ["frontend/src/pages/Org.jsx"])
        self.assertEqual(len(errors), 1)
        self.assertIn("frontend/src/pages/Org.jsx imports getOrganization", errors[0])
        self.assertIn("frontend/src/api.js", errors[0])
        self.assertIn("getRepository", errors[0], "lists what the module does export")

    def test_should_flag_a_rewrite_that_drops_an_export_another_file_still_uses(self):
        sources = {"frontend/src/api.js": "export function listRepos() {}\n",
                   "frontend/src/pages/Repo.jsx": "import {getRepository as fetchRepo} from '../api';\n"}
        errors = missing_export_errors(sources, ["frontend/src/api.js"])
        self.assertEqual(len(errors), 1)
        self.assertIn("frontend/src/pages/Repo.jsx imports getRepository", errors[0])

    def test_should_accept_matching_aliases_extensionless_index_and_unknown_modules(self):
        sources = {"frontend/src/api.js": API,
                   "frontend/src/lib/index.js": "export default function x() {}\nexport const y = 1;\n",
                   "frontend/src/barrel.js": "export * from './api.js';\n",
                   "frontend/src/pages/A.jsx": ("import React, {useState} from 'react';\n"
                                                "import {getRepository, loadAll as all} from '../api';\n"
                                                "import x, {y} from '../lib';\n"
                                                "import {anything} from '../barrel.js';\n"
                                                "import {missing} from '../not-generated-yet.js';\n"
                                                "// import {commented} from '../api.js';\n")}
        self.assertEqual(missing_export_errors(sources, list(sources)), [])

    def test_check_batch_reports_it_without_running_a_build(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            result = check_batch(Path(folder), ["frontend/src/pages/Org.jsx"], budget=1, sources={
                "frontend/src/api.js": API,
                "frontend/src/pages/Org.jsx": "import {getOrganization} from '../api.js';\n"})
        self.assertTrue(any("imports getOrganization" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
