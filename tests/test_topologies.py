from ripx.simulation.topologies import mesh, random_connected


def test_mesh_has_every_possible_link():
    network = mesh(5)
    assert len(network.links) == 10
    network.converge()
    assert network.routers["R1"].route("R5").metric == 1


def test_seeded_random_topology_repeats_exactly():
    first = random_connected(10, seed=7, edge_probability=0.2)
    second = random_connected(10, seed=7, edge_probability=0.2)
    assert first.links == second.links
