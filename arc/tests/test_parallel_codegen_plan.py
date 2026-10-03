"""Planner grants exact source paths only for independent, explicit owners."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from parallel_codegen_plan import plan_parallel_tasks  # noqa: E402


def nodes(*ids):
    return [{"id": value, "dependencies": []} for value in ids]


def design(*modules):
    return {"modules": list(modules)}


def module(path, *owners):
    return {"path": path, "requirements": list(owners)}


class ParallelCodegenPlanTests(unittest.TestCase):
    def test_assigns_three_exact_paths_and_read_only_shared_files(self):
        packets = plan_parallel_tasks(
            nodes("REQ-A", "REQ-B", "REQ-C", "REQ-D"),
            design(module("frontend/src/pages/A.jsx", "REQ-A"),
                   module("backend/routes/b.js", "REQ-B"),
                   module("frontend/src/components/C.jsx", "REQ-C"),
                   module("backend/routes/d.js", "REQ-D"),
                   {"path": "frontend/src/App.jsx", "requirements": ["REQ-A", "REQ-B"]}),
            {"frontend/src/App.jsx", "backend/server.js", "frontend/package.json"},
        )
        self.assertEqual([packet.node_ids for packet in packets],
                         [("REQ-A",), ("REQ-B",), ("REQ-C",)])
        self.assertEqual([packet.allowed_paths for packet in packets],
                         [("frontend/src/pages/A.jsx",), ("backend/routes/b.js",),
                          ("frontend/src/components/C.jsx",)])
        self.assertEqual(packets[0].shared_paths,
                         ("backend/server.js", "frontend/package.json", "frontend/src/App.jsx"))
        self.assertEqual({path for packet in packets for path in packet.allowed_paths}
                         & set(packets[0].shared_paths), set())

    def test_joint_module_owners_are_one_packet_with_internal_dependency(self):
        ordered = nodes("REQ-A", "REQ-B", "REQ-C")
        ordered[1]["dependencies"] = ["REQ-A"]
        packets = plan_parallel_tasks(
            ordered,
            design(module("frontend/src/features/account.jsx", "REQ-A", "REQ-B"),
                   module("frontend/src/features/account.css", "REQ-B"),
                   module("backend/routes/c.js", "REQ-C")), set())
        self.assertEqual([packet.node_ids for packet in packets],
                         [("REQ-A", "REQ-B"), ("REQ-C",)])
        self.assertEqual(packets[0].dependencies, ("REQ-A",))
        self.assertEqual(packets[0].allowed_paths,
                         ("frontend/src/features/account.css", "frontend/src/features/account.jsx"))

    def test_cross_packet_dependency_is_left_to_serial_flow(self):
        ordered = nodes("REQ-A", "REQ-B", "REQ-C")
        ordered[1]["dependencies"] = ["REQ-A"]
        packets = plan_parallel_tasks(
            ordered,
            design(module("frontend/src/A.jsx", "REQ-A"),
                   module("frontend/src/B.jsx", "REQ-B"),
                   module("frontend/src/C.jsx", "REQ-C")), set())
        self.assertEqual([packet.node_ids for packet in packets], [("REQ-A",), ("REQ-C",)])

    def test_missing_ownership_or_unsafe_paths_fail_closed(self):
        base = [module("frontend/src/A.jsx", "REQ-A"),
                module("backend/routes/b.js", "REQ-B")]
        self.assertEqual(plan_parallel_tasks(nodes("REQ-A", "REQ-B"),
                                             design({"path": "frontend/src/unknown.jsx"}, *base), set()), [])
        for path in ("frontend/src/../bad.jsx", "backend/tests/b.js", "backend/Tests/b.js",
                     "backend/data/users.json",
                     "frontend/src/A.test.js", "/tmp/b.js", "frontend/src/C\\x.js"):
            with self.subTest(path=path):
                self.assertEqual(plan_parallel_tasks(nodes("REQ-A", "REQ-B"),
                                                     design(module(path, "REQ-A"), base[1]), set()), [])

    def test_shared_helpers_never_become_worker_owned(self):
        packets = plan_parallel_tasks(
            nodes("REQ-A", "REQ-B"),
            design(module("frontend/src/A.jsx", "REQ-A"),
                   module("backend/routes/b.js", "REQ-B"),
                   module("backend/lib/store.js", "REQ-A")),
            {"backend/lib/store.js", "frontend/src/Tests/App.jsx"})
        self.assertEqual(len(packets), 2)
        self.assertEqual(packets[0].shared_paths, ("backend/lib/store.js",))
        self.assertNotIn("backend/lib/store.js", packets[0].allowed_paths)

    def test_duplicate_path_with_conflicting_owners_and_case_collision_fail_closed(self):
        for other in (module("frontend/src/A.jsx", "REQ-B"),
                      module("frontend/src/a.jsx", "REQ-B")):
            with self.subTest(other=other):
                self.assertEqual(plan_parallel_tasks(nodes("REQ-A", "REQ-B"),
                                                     design(module("frontend/src/A.jsx", "REQ-A"),
                                                            other,
                                                            module("backend/routes/b.js", "REQ-B")), set()), [])

    def test_file_directory_path_overlap_fails_closed(self):
        self.assertEqual(plan_parallel_tasks(
            nodes("REQ-A", "REQ-B"),
            design(module("frontend/src/A.jsx", "REQ-A"),
                   module("frontend/src/A.jsx/part.js", "REQ-B")), set()), [])

    def test_requires_two_independent_tasks_and_honors_worker_cap(self):
        self.assertEqual(plan_parallel_tasks(nodes("REQ-A"),
                                             design(module("frontend/src/A.jsx", "REQ-A")), set()), [])
        packets = plan_parallel_tasks(
            nodes("REQ-A", "REQ-B", "REQ-C"),
            design(module("frontend/src/A.jsx", "REQ-A"),
                   module("frontend/src/B.jsx", "REQ-B"),
                   module("frontend/src/C.jsx", "REQ-C")), set(), max_workers=2)
        self.assertEqual(len(packets), 2)
        self.assertEqual([packet.task_id for packet in packets], ["parallel-1", "parallel-2"])


if __name__ == "__main__":
    unittest.main()
