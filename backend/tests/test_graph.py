"""Structural analysis: topological sorting, cycle detection, shape metrics."""

import pytest
from conftest import chain, edge, node, ring

from app.core.graph import analyse, is_dag


class TestIsDag:
    def test_empty_graph_is_a_dag(self):
        assert is_dag([], []) is True

    def test_single_node_is_a_dag(self):
        assert is_dag([node('a')], []) is True

    def test_chain_is_a_dag(self):
        assert is_dag(*chain(5)) is True

    def test_diamond_is_a_dag(self):
        """Two paths that split and rejoin: acyclic despite the fan-in."""
        nodes = [node(n) for n in 'abcd']
        edges = [edge('a', 'b'), edge('a', 'c'), edge('b', 'd'), edge('c', 'd')]
        assert is_dag(nodes, edges) is True

    def test_self_loop_is_a_cycle(self):
        assert is_dag([node('a')], [edge('a', 'a')]) is False

    def test_two_node_cycle_is_a_cycle(self):
        assert is_dag([node('a'), node('b')], [edge('a', 'b'), edge('b', 'a')]) is False

    @pytest.mark.parametrize('length', [3, 4, 10, 50])
    def test_ring_of_any_length_is_a_cycle(self, length):
        assert is_dag(*ring(length)) is False

    def test_a_cycle_hidden_downstream_of_a_valid_prefix(self):
        """a -> b -> c -> d -> b: the prefix sorts fine, the tail does not."""
        nodes = [node(n) for n in 'abcd']
        edges = [edge('a', 'b'), edge('b', 'c'), edge('c', 'd'), edge('d', 'b')]
        assert is_dag(nodes, edges) is False

    def test_two_disconnected_components_both_acyclic(self):
        nodes = [node(n) for n in 'abcd']
        edges = [edge('a', 'b'), edge('c', 'd')]
        assert is_dag(nodes, edges) is True

    def test_one_cyclic_component_makes_the_whole_graph_cyclic(self):
        nodes = [node(n) for n in 'abcd']
        edges = [edge('a', 'b'), edge('c', 'd'), edge('d', 'c')]
        assert is_dag(nodes, edges) is False

    def test_parallel_edges_between_the_same_pair_stay_acyclic(self):
        """A double a->b is a multigraph edge, not a cycle."""
        nodes = [node('a'), node('b')]
        edges = [edge('a', 'b', edge_id='e1'), edge('a', 'b', edge_id='e2')]
        assert is_dag(nodes, edges) is True


class TestTopologicalOrder:
    def test_order_respects_every_edge(self):
        nodes = [node(n) for n in 'abcd']
        edges = [edge('a', 'b'), edge('a', 'c'), edge('b', 'd'), edge('c', 'd')]
        order = analyse(nodes, edges).topological_order

        position = {node_id: i for i, node_id in enumerate(order)}
        for e in edges:
            assert position[e.source] < position[e.target]

    def test_order_covers_every_node_exactly_once(self):
        nodes, edges = chain(6)
        order = analyse(nodes, edges).topological_order
        assert sorted(order) == sorted(n.id for n in nodes)
        assert len(order) == len(set(order))

    def test_cyclic_graph_yields_a_partial_order(self):
        """Kahn's algorithm places the acyclic prefix and stops there."""
        nodes = [node(n) for n in 'abcd']
        edges = [edge('a', 'b'), edge('b', 'c'), edge('c', 'd'), edge('d', 'b')]
        analysis = analyse(nodes, edges)
        assert analysis.topological_order == ['a']
        assert analysis.is_dag is False


class TestCycleReporting:
    def test_self_loop_is_reported_as_a_one_node_cycle(self):
        analysis = analyse([node('a')], [edge('a', 'a')])
        assert analysis.cycles == [['a']]

    def test_cycle_members_are_named(self):
        analysis = analyse(*ring(3))
        assert len(analysis.cycles) == 1
        assert set(analysis.cycles[0]) == {'n0', 'n1', 'n2'}

    def test_nodes_outside_the_cycle_are_not_named(self):
        """a feeds the ring b->c->b, but a is not part of it."""
        nodes = [node(n) for n in 'abc']
        edges = [edge('a', 'b'), edge('b', 'c'), edge('c', 'b')]
        analysis = analyse(nodes, edges)
        assert analysis.cyclic_nodes == {'b', 'c'}

    def test_two_independent_cycles_are_both_reported(self):
        nodes = [node(n) for n in 'abcd']
        edges = [edge('a', 'b'), edge('b', 'a'), edge('c', 'd'), edge('d', 'c')]
        analysis = analyse(nodes, edges)
        assert len(analysis.cycles) == 2
        assert {frozenset(c) for c in analysis.cycles} == {
            frozenset({'a', 'b'}), frozenset({'c', 'd'})}

    def test_acyclic_graph_reports_no_cycles(self):
        assert analyse(*chain(4)).cycles == []

    def test_long_cycle_does_not_exhaust_the_stack(self):
        """The DFS is iterative, so a 5000-node ring must not raise."""
        analysis = analyse(*ring(5000))
        assert analysis.is_dag is False
        assert len(analysis.cycles) == 1


class TestShapeMetrics:
    def test_entry_and_exit_points_of_a_chain(self):
        analysis = analyse(*chain(4))
        assert analysis.entry_points == ['n0']
        assert analysis.exit_points == ['n3']

    def test_fan_out_has_several_exit_points(self):
        nodes = [node(n) for n in 'abc']
        edges = [edge('a', 'b'), edge('a', 'c')]
        analysis = analyse(nodes, edges)
        assert analysis.entry_points == ['a']
        assert sorted(analysis.exit_points) == ['b', 'c']

    def test_isolated_nodes_are_listed(self):
        nodes = [node(n) for n in 'abc']
        analysis = analyse(nodes, [edge('a', 'b')])
        assert analysis.isolated_nodes == ['c']

    def test_depth_counts_the_longest_path(self):
        assert analyse(*chain(5)).depth == 5

    def test_depth_follows_the_longer_branch_of_a_diamond(self):
        """a -> b -> c -> d and a -> d: the depth is 4, not 2."""
        nodes = [node(n) for n in 'abcd']
        edges = [edge('a', 'b'), edge('b', 'c'), edge('c', 'd'), edge('a', 'd')]
        assert analyse(nodes, edges).depth == 4

    def test_parallel_nodes_share_a_level(self):
        nodes = [node(n) for n in 'abc']
        edges = [edge('a', 'b'), edge('a', 'c')]
        levels = analyse(nodes, edges).levels
        assert levels['a'] == 0
        assert levels['b'] == levels['c'] == 1

    def test_empty_graph_has_zero_depth(self):
        assert analyse([], []).depth == 0

    def test_cyclic_graph_reports_no_depth(self):
        """No finite longest path exists, so the levels are withheld."""
        analysis = analyse(*ring(3))
        assert analysis.levels == {}
        assert analysis.depth == 0

    def test_degrees_are_counted_per_node(self):
        nodes = [node(n) for n in 'abc']
        edges = [edge('a', 'c'), edge('b', 'c')]
        analysis = analyse(nodes, edges)
        assert analysis.in_degree == {'a': 0, 'b': 0, 'c': 2}
        assert analysis.out_degree == {'a': 1, 'b': 1, 'c': 0}


class TestMalformedInput:
    def test_edge_to_a_missing_node_is_dropped_and_reported(self):
        analysis = analyse([node('a')], [edge('a', 'ghost', edge_id='e1')])
        assert analysis.dangling_edges == ['e1']
        assert analysis.is_dag is True

    def test_edge_from_a_missing_node_is_dropped(self):
        analysis = analyse([node('a')], [edge('ghost', 'a', edge_id='e1')])
        assert analysis.dangling_edges == ['e1']
        assert analysis.in_degree['a'] == 0

    def test_duplicate_node_ids_collapse_to_one(self):
        analysis = analyse([node('a'), node('a')], [])
        assert analysis.node_ids == ['a']

    def test_a_dangling_edge_cannot_fake_a_cycle(self):
        nodes = [node('a'), node('b')]
        edges = [edge('a', 'b'), edge('ghost', 'a')]
        assert analyse(nodes, edges).is_dag is True
