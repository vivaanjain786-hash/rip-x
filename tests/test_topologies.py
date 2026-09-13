from ripx.simulation.topologies import enterprise_like, iot_edge_like, mesh, random_connected, scale_free


def test_mesh_has_every_possible_link():
    network = mesh(5)
    assert len(network.links) == 10
    network.converge()
    assert network.routers["R1"].route("R5").metric == 1


def test_seeded_random_topology_repeats_exactly():
    first = random_connected(10, seed=7, edge_probability=0.2)
    second = random_connected(10, seed=7, edge_probability=0.2)
    assert first.links == second.links


# ── scale_free ─────────────────────────────────────────────────────────────

def test_scale_free_is_connected_after_convergence():
    """Every router must be reachable from R1 after convergence."""
    network = scale_free(10, seed=0)
    network.converge()
    for name in network.routers:
        if name != "R1":
            route = network.routers["R1"].route(name)
            assert route is not None and route.reachable, f"R1 cannot reach {name}"


def test_scale_free_is_reproducible():
    """Same seed must produce identical link sets."""
    first = scale_free(15, seed=99)
    second = scale_free(15, seed=99)
    assert first.links == second.links


def test_scale_free_different_seeds_differ():
    """Different seeds should (almost certainly) produce different topologies."""
    a = scale_free(15, seed=1)
    b = scale_free(15, seed=2)
    # Not guaranteed in theory but true in practice for any reasonable BA model
    assert a.links != b.links


# ── enterprise_like ─────────────────────────────────────────────────────────

def test_enterprise_like_has_correct_router_names():
    network = enterprise_like()
    expected = {"C1", "C2", "D1", "D2", "D3", "A1", "A2", "A3", "A4", "A5"}
    assert set(network.routers.keys()) == expected


def test_enterprise_like_link_count():
    """1 core-core + 6 dist-core + 5 access-dist = 12 links."""
    network = enterprise_like()
    assert len(network.links) == 12


def test_enterprise_like_access_routers_two_hops_from_core():
    """Access routers connect via one distribution layer → hop count from C1 is 2."""
    network = enterprise_like()
    network.converge()
    for access in ("A1", "A2", "A3", "A4", "A5"):
        route = network.routers["C1"].route(access)
        assert route is not None and route.reachable
        assert route.metric == 2, f"Expected 2 hops from C1 to {access}, got {route.metric}"


def test_enterprise_like_core_routers_one_hop_apart():
    network = enterprise_like()
    network.converge()
    assert network.routers["C1"].route("C2").metric == 1


# ── iot_edge_like ───────────────────────────────────────────────────────────

def test_iot_edge_like_total_router_count():
    """GW + 3 hubs + 12 leaves = 16 routers."""
    network = iot_edge_like(edge_hubs=3, devices_per_hub=4)
    assert len(network.routers) == 16


def test_iot_edge_like_gateway_is_hub_of_hubs():
    """GW must be adjacent to every hub, not to any leaf directly."""
    network = iot_edge_like(edge_hubs=3, devices_per_hub=4)
    gw_neighbors = set(network.neighbors("GW"))
    assert gw_neighbors == {"H1", "H2", "H3"}


def test_iot_edge_like_leaf_is_two_hops_from_gateway():
    """Leaf routers are one hop from their hub and two hops from GW."""
    network = iot_edge_like(edge_hubs=2, devices_per_hub=3)
    network.converge()
    route = network.routers["GW"].route("D1_1")
    assert route is not None and route.reachable
    assert route.metric == 2
