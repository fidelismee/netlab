import copy
import ipaddress
import unittest

import build_routed
import make_page3
import routers


GUIDED_ROUTES = {
    "r1": [
        {"to": "10.45.32.0/24", "via": "10.45.12.2"},
        {"to": "10.45.32.0/20", "via": "10.45.13.2"},
    ],
    "r3": [
        {"to": "10.45.32.0/20", "via": "10.45.23.2"},
        {"to": "10.45.1.0/24", "via": "10.45.13.1"},
    ],
    "r2": [{"to": "10.45.1.0/24", "via": "10.45.12.1"}],
}


def assignment_spec():
    return {
        "student_id_last4": "1945",
        "routers": ["r1", "r2", "r3"],
        "lans": [
            {"name": "lan-h1", "network": "10.45.16.0/24", "router": "r1", "host": "h1"},
            {"name": "lan-h2", "network": "10.45.17.0/24", "router": "r2", "host": "h2"},
            {"name": "lan-h3", "network": "10.45.32.0/24", "router": "r3", "host": "h3"},
        ],
        "links": [
            ["r1", "r2", "10.45.250.0/30"],
            ["r2", "r3", "10.45.250.4/30"],
            ["r3", "r1", "10.45.250.8/30"],
        ],
        "routes": {
            "r1": [
                {"to": "10.45.16.0/23", "via": "10.45.250.2"},
                {"to": "10.45.32.0/24", "via": "10.45.250.9"},
            ],
            "r2": [
                {"to": "10.45.16.0/23", "via": "10.45.250.1"},
                {"to": "10.45.32.0/24", "via": "10.45.250.6"},
            ],
            "r3": [{"to": "10.45.16.0/23", "via": "10.45.250.5"}],
        },
    }


class GuidedPathTests(unittest.TestCase):
    def test_valid_routes_reach_every_ordered_host_pair(self):
        self.assertEqual([], routers.check_paths(GUIDED_ROUTES, 45))

    def test_loop_reports_repeated_router_path(self):
        routes = copy.deepcopy(GUIDED_ROUTES)
        routes["r3"][0]["via"] = "10.45.13.1"
        self.assertIn("h1 to h3: loop r1 -> r3 -> r1", routers.check_paths(routes, 45))

    def test_missing_route_names_router_and_destination(self):
        routes = copy.deepcopy(GUIDED_ROUTES)
        routes["r2"] = []
        self.assertIn("h2 to h1: r2 has no route to 10.45.1.10", routers.check_paths(routes, 45))

    def test_lookup_uses_more_specific_route(self):
        kind, via = routers.lookup("r1", ipaddress.ip_address("10.45.32.10"), GUIDED_ROUTES, 45)
        self.assertEqual(("via", ipaddress.ip_address("10.45.12.2")), (kind, via))


class AssignmentPathTests(unittest.TestCase):
    def test_valid_routes_reach_every_ordered_host_pair(self):
        self.assertEqual([], build_routed.check_paths(assignment_spec()))

    def test_directly_connected_destinations_are_delivered(self):
        spec = {
            "student_id_last4": "1945",
            "routers": ["r1"],
            "lans": [
                {"name": "lan-a", "network": "10.45.1.0/24", "router": "r1", "host": "ha"},
                {"name": "lan-b", "network": "10.45.2.0/24", "router": "r1", "host": "hb"},
            ],
            "links": [],
            "routes": {},
        }
        self.assertEqual([], build_routed.check_paths(spec))

    def test_missing_route_names_router_and_destination(self):
        spec = assignment_spec()
        spec["routes"]["r1"] = [spec["routes"]["r1"][0]]
        self.assertIn("h1 to h3: r1 has no route to 10.45.32.10", build_routed.check_paths(spec))

    def test_loop_reports_repeated_router_path(self):
        spec = assignment_spec()
        spec["routes"]["r1"][1]["via"] = "10.45.250.2"
        spec["routes"]["r2"][1]["via"] = "10.45.250.1"
        self.assertIn("h1 to h3: loop r1 -> r2 -> r1", build_routed.check_paths(spec))

    def test_lookup_uses_more_specific_route_over_summary(self):
        spec = assignment_spec()
        spec["routes"]["r1"].append({"to": "10.45.17.0/24", "via": "10.45.250.9"})
        kind, via = build_routed.lookup(spec, "r1", ipaddress.ip_address("10.45.17.10"))
        self.assertEqual(("via", ipaddress.ip_address("10.45.250.9")), (kind, via))


class RoutingTablePageTests(unittest.TestCase):
    def test_tables_include_connected_and_static_entries_longest_prefix_first(self):
        html = make_page3.routing_tables_section(assignment_spec())
        self.assertIn("<h3>r1</h3>", html)
        self.assertIn("10.45.250.0/30", html)
        self.assertIn("directly connected", html)
        self.assertIn("10.45.32.0/24", html)
        self.assertIn("10.45.16.0/23", html)
        self.assertIn("10.45.250.9", html)
        self.assertLess(html.index("10.45.250.0/30"), html.index("10.45.32.0/24"))
        self.assertLess(html.index("10.45.32.0/24"), html.index("10.45.16.0/23"))


if __name__ == "__main__":
    unittest.main()
