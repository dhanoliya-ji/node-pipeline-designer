"""The HTTP surface, exercised through FastAPI's test client."""

import pytest
from conftest import edge, node
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client():
    return TestClient(create_app())


def payload(nodes, edges):
    """Serialise the way the frontend does, dropping the canvas's view state."""
    return {
        'nodes': [n.model_dump() for n in nodes],
        'edges': [e.model_dump() for e in edges],
    }


class TestMeta:
    def test_root_describes_the_service(self, client):
        body = client.get('/').json()
        assert body['name'] == 'Node Pipeline Designer API'
        assert 'version' in body

    def test_health_is_ok(self, client):
        response = client.get('/health')
        assert response.status_code == 200
        assert response.json()['status'] == 'ok'

    def test_the_node_catalogue_lists_every_type(self, client):
        catalogue = client.get('/nodes').json()
        types = {entry['type'] for entry in catalogue}
        assert {'customInput', 'customOutput', 'text', 'llm', 'math',
                'filter', 'condition', 'merge', 'api'} <= types

    def test_every_catalogued_node_is_executable(self, client):
        assert all(entry['executable'] for entry in client.get('/nodes').json())

    def test_openapi_schema_is_served(self, client):
        assert client.get('/openapi.json').status_code == 200


class TestParse:
    def test_the_original_three_fields_are_unchanged(self, client, linear_pipeline):
        """The endpoint predates this rewrite; older clients must keep working."""
        body = client.post('/pipelines/parse', json=payload(*linear_pipeline)).json()
        assert body['num_nodes'] == 3
        assert body['num_edges'] == 2
        assert body['is_dag'] is True

    def test_an_empty_pipeline_parses(self, client):
        body = client.post('/pipelines/parse', json={'nodes': [], 'edges': []}).json()
        assert body == {
            'num_nodes': 0, 'num_edges': 0, 'is_dag': True,
            'cycles': [], 'topological_order': [], 'depth': 0,
            'entry_points': [], 'exit_points': [], 'isolated_nodes': [],
            'issues': [{
                'code': 'EMPTY_PIPELINE',
                'severity': 'info',
                'message': 'The pipeline is empty. Drag a node onto the canvas to begin.',
                'node_id': None,
                'edge_id': None,
            }],
        }

    def test_structure_is_reported(self, client, linear_pipeline):
        body = client.post('/pipelines/parse', json=payload(*linear_pipeline)).json()
        assert body['depth'] == 3
        assert body['entry_points'] == ['customInput-1']
        assert body['exit_points'] == ['customOutput-1']
        assert body['topological_order'] == [
            'customInput-1', 'text-1', 'customOutput-1']

    def test_a_cycle_is_reported_with_its_members(self, client):
        nodes = [node(n, 'text', text='{{in}}') for n in ('a', 'b')]
        edges = [edge('a', 'b', 'output', 'in'), edge('b', 'a', 'output', 'in')]
        body = client.post('/pipelines/parse', json=payload(nodes, edges)).json()
        assert body['is_dag'] is False
        assert set(body['cycles'][0]) == {'a', 'b'}

    def test_a_missing_body_is_rejected(self, client):
        assert client.post('/pipelines/parse', json={'nodes': 'nope'}).status_code == 422

    def test_unknown_fields_on_a_node_are_ignored(self, client):
        """React Flow sends position, width, selected and more; none are modelled."""
        body = client.post('/pipelines/parse', json={
            'nodes': [{'id': 'a', 'type': 'customInput', 'data': {},
                       'position': {'x': 1, 'y': 2}, 'selected': True}],
            'edges': [],
        })
        assert body.status_code == 200
        assert body.json()['num_nodes'] == 1


class TestValidate:
    def test_a_clean_pipeline_is_valid(self, client, linear_pipeline):
        body = client.post('/pipelines/validate', json=payload(*linear_pipeline)).json()
        assert body['is_valid'] is True
        assert body['is_dag'] is True

    def test_a_broken_pipeline_is_invalid_and_explains_why(self, client):
        nodes = [node('customInput-1', 'customInput'), node('math-1', 'math')]
        edges = [edge('customInput-1', 'math-1', 'value', 'a')]
        body = client.post('/pipelines/validate', json=payload(nodes, edges)).json()
        assert body['is_valid'] is False
        assert any(i['code'] == 'MISSING_REQUIRED_INPUT' for i in body['issues'])

    def test_each_issue_names_the_element_it_belongs_to(self, client):
        nodes = [node('text-1', 'text', text='{{x}}')]
        body = client.post('/pipelines/validate', json=payload(nodes, [])).json()
        issue = next(i for i in body['issues'] if i['code'] == 'UNCONNECTED_VARIABLE')
        assert issue['node_id'] == 'text-1'


class TestExecute:
    def test_a_pipeline_runs_and_returns_its_output(self, client, linear_pipeline):
        body = client.post('/pipelines/execute', json=payload(*linear_pipeline)).json()
        assert body['status'] == 'ok'
        assert body['outputs'] == {'greeting': 'Hello, Ada!'}

    def test_every_step_is_reported(self, client, linear_pipeline):
        body = client.post('/pipelines/execute', json=payload(*linear_pipeline)).json()
        assert [s['node_id'] for s in body['steps']] == [
            'customInput-1', 'text-1', 'customOutput-1']

    def test_an_invalid_pipeline_is_refused_with_its_issues(self, client):
        nodes = [node('customInput-1', 'customInput'), node('math-1', 'math')]
        edges = [edge('customInput-1', 'math-1', 'value', 'a')]
        body = client.post('/pipelines/execute', json=payload(nodes, edges)).json()
        assert body['status'] == 'error'
        assert body['steps'] == []
        assert body['issues']

    def test_strict_can_be_turned_off(self, client):
        """Math is missing its `b` input, which strict mode refuses outright."""
        nodes = [
            node('customInput-1', 'customInput', inputValue='5'),
            node('math-1', 'math', operation='add'),
        ]
        edges = [edge('customInput-1', 'math-1', 'value', 'a')]
        body = client.post('/pipelines/execute?strict=false',
                           json=payload(nodes, edges)).json()
        assert body['status'] == 'ok'
        assert len(body['steps']) == 2

    def test_a_branch_reports_the_skipped_side(self, client, branching_pipeline):
        body = client.post('/pipelines/execute',
                           json=payload(*branching_pipeline)).json()
        statuses = {s['node_id']: s['status'] for s in body['steps']}
        assert statuses['customOutput-1'] == 'ok'
        assert statuses['customOutput-2'] == 'skipped'

    def test_an_oversized_pipeline_is_rejected_with_413(self, client, monkeypatch):
        monkeypatch.setattr('app.core.engine.MAX_NODES', 1)
        response = client.post('/pipelines/execute',
                               json=payload([node('a'), node('b')], []))
        assert response.status_code == 413


class TestCors:
    def test_a_localhost_origin_is_allowed(self, client):
        response = client.options('/pipelines/parse', headers={
            'Origin': 'http://localhost:3001',
            'Access-Control-Request-Method': 'POST',
        })
        assert response.headers.get('access-control-allow-origin') == \
            'http://localhost:3001'

    def test_an_unrelated_origin_is_not_allowed(self, client):
        response = client.options('/pipelines/parse', headers={
            'Origin': 'https://evil.example.com',
            'Access-Control-Request-Method': 'POST',
        })
        assert 'access-control-allow-origin' not in response.headers
