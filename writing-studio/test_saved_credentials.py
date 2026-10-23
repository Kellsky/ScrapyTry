"""Saved-credential HTTP regressions using isolated data and fake providers.

These tests deliberately send no keys in connection-test requests, just as the
browser does after it clears password inputs following a successful save.
"""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import httpx

import app as studio


ORIGINAL_ASYNC_CLIENT = httpx.AsyncClient
WRITER_KEY = 'dummy-saved-writer-token'
REVIEWER_KEY = 'dummy-saved-reviewer-token'


class SavedCredentialConnectionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='gaojian-saved-credentials-')
        self.previous_data = studio.DATA
        studio.DATA = Path(self.directory.name)
        self.environment = patch.dict(os.environ, {'WRITING_STUDIO_SEED': '0', 'WRITING_API_KEY': ''})
        self.environment.start()
        self.outbound = []

        def handle(request):
            body = json.loads(request.content)
            self.outbound.append({'host': request.url.host, 'path': request.url.path,
                                  'authorization': request.headers.get('authorization'),
                                  'model': body['model']})
            # Deliberately echo the authorization to ensure the endpoint never
            # exposes arbitrary provider output back to the frontend.
            return httpx.Response(200, json={
                'choices': [{'message': {'content': request.headers['authorization']},
                             'finish_reason': 'stop'}],
                'usage': {'prompt_tokens': 6, 'completion_tokens': 4, 'total_tokens': 10},
            })

        def async_client(**kwargs):
            return ORIGINAL_ASYNC_CLIENT(**kwargs, transport=httpx.MockTransport(handle), trust_env=False)

        self.transport = patch.object(httpx, 'AsyncClient', side_effect=async_client)
        self.transport.start()
        self.client = TestClient(studio.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.transport.stop()
        self.environment.stop()
        studio.DATA = self.previous_data
        self.directory.cleanup()

    def restart_server(self):
        self.client.__exit__(None, None, None)
        self.client = TestClient(studio.app)
        self.client.__enter__()

    def assert_no_secrets(self, response):
        self.assertNotIn(WRITER_KEY, response.text)
        self.assertNotIn(REVIEWER_KEY, response.text)

    def save(self, **overrides):
        payload = {'base_url': 'https://writer.example/v1', 'writer_model': 'writer-model',
                   'reviewer_base_url': '', 'reviewer_model': '', 'vision_model': '',
                   'daily_limit': 100000, **overrides}
        response = self.client.put('/api/settings', json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        self.assert_no_secrets(response)
        self.assertNotIn('api_key', response.json())
        self.assertNotIn('reviewer_api_key', response.json())
        return response.json()

    def bootstrap(self):
        response = self.client.get('/api/bootstrap')
        self.assertEqual(response.status_code, 200, response.text)
        self.assert_no_secrets(response)
        return response.json()['settings']

    def saved_status(self):
        before = len(self.outbound)
        response = self.client.get('/api/settings/status')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers.get('cache-control'), 'no-store')
        self.assert_no_secrets(response)
        data = response.json()
        self.assertNotIn('api_key', data)
        self.assertNotIn('reviewer_api_key', data)
        self.assertEqual(len(self.outbound), before, '读取保存状态不应触发模型调用')
        return data

    def check_connection(self, role, host, key, model):
        previous = len(self.outbound)
        # Password inputs have been cleared; only the role is submitted.
        response = self.client.post('/api/settings/test', json={'role': role})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()['ok'])
        self.assertEqual(response.json()['role'], role)
        self.assert_no_secrets(response)
        self.assertEqual(len(self.outbound), previous + 1)
        self.assertEqual(self.outbound[-1], {
            'host': host, 'path': '/v1/chat/completions',
            'authorization': 'Bearer ' + key, 'model': model,
        })

    def test_single_writer_key_is_used_for_both_roles_after_blank_resave_and_reload(self):
        saved = self.save(api_key=WRITER_KEY)
        self.assertTrue(saved['has_key'])
        self.assertFalse(saved['has_reviewer_key'])
        self.assertTrue(saved['configured'])
        self.assertEqual(saved['reviewer_model'], 'writer-model')
        writer_status = saved['role_status']['writer']
        reviewer_status = saved['role_status']['reviewer']
        self.assertTrue(writer_status['ready'])
        self.assertEqual(writer_status['key_source'], 'writer')
        self.assertTrue(reviewer_status['ready'])
        self.assertTrue(reviewer_status['has_key'])
        self.assertTrue(reviewer_status['key_inherited'])
        self.assertEqual(reviewer_status['key_source'], 'writer')
        self.check_connection('writer', 'writer.example', WRITER_KEY, 'writer-model')
        self.check_connection('reviewer', 'writer.example', WRITER_KEY, 'writer-model')
        # The fake model echoes its Authorization header; a later status read
        # still must never disclose either that text or the saved credential.
        self.assertEqual(self.saved_status()['role_status'], saved['role_status'])

        # Re-submit the ordinary settings form with both visible password fields
        # empty. This must preserve server-held credentials, not erase them.
        self.save(api_key='', reviewer_api_key='')
        reloaded = self.bootstrap()
        self.assertTrue(reloaded['has_key'])
        self.assertTrue(reloaded['configured'])
        self.assertEqual(self.saved_status()['role_status'], saved['role_status'])
        self.check_connection('writer', 'writer.example', WRITER_KEY, 'writer-model')
        self.check_connection('reviewer', 'writer.example', WRITER_KEY, 'writer-model')

    def test_separate_services_retain_each_key_after_blank_resave(self):
        review_settings = {'reviewer_base_url': 'https://reviewer.example/v1',
                           'reviewer_model': 'independent-review-model'}
        saved = self.save(api_key=WRITER_KEY, reviewer_api_key=REVIEWER_KEY, **review_settings)
        self.assertTrue(saved['has_key'])
        self.assertTrue(saved['has_reviewer_key'])
        self.assertTrue(saved['configured'])
        self.check_connection('writer', 'writer.example', WRITER_KEY, 'writer-model')
        self.check_connection('reviewer', 'reviewer.example', REVIEWER_KEY, 'independent-review-model')

        self.save(api_key='', reviewer_api_key='', **review_settings)
        self.assertTrue(self.bootstrap()['has_reviewer_key'])
        self.check_connection('writer', 'writer.example', WRITER_KEY, 'writer-model')
        self.check_connection('reviewer', 'reviewer.example', REVIEWER_KEY, 'independent-review-model')

    def test_explicit_review_key_with_blank_review_address_uses_shared_address(self):
        saved = self.save(api_key=WRITER_KEY, reviewer_api_key=REVIEWER_KEY,
                          reviewer_base_url='', reviewer_model='review-model')
        self.assertTrue(saved['has_reviewer_key'])
        self.check_connection('writer', 'writer.example', WRITER_KEY, 'writer-model')
        self.check_connection('reviewer', 'writer.example', REVIEWER_KEY, 'review-model')

        self.save(api_key='', reviewer_api_key='', reviewer_base_url='', reviewer_model='review-model')
        self.bootstrap()
        self.check_connection('reviewer', 'writer.example', REVIEWER_KEY, 'review-model')

    def test_both_server_held_keys_survive_restart_without_resubmission(self):
        review_settings = {'reviewer_base_url': 'https://reviewer.example/v1',
                           'reviewer_model': 'independent-review-model'}
        self.save(api_key=WRITER_KEY, reviewer_api_key=REVIEWER_KEY, **review_settings)
        self.save(api_key='', reviewer_api_key='', **review_settings)
        before_restart = self.saved_status()['role_status']
        self.assertTrue(before_restart['reviewer']['ready'])
        self.assertFalse(before_restart['reviewer']['key_inherited'])
        self.assertEqual(before_restart['reviewer']['key_source'], 'reviewer')
        self.restart_server()
        restored = self.bootstrap()
        self.assertTrue(restored['has_key'])
        self.assertTrue(restored['has_reviewer_key'])
        self.assertTrue(restored['configured'])
        self.assertEqual(self.saved_status()['role_status'], before_restart)
        self.check_connection('writer', 'writer.example', WRITER_KEY, 'writer-model')
        self.check_connection('reviewer', 'reviewer.example', REVIEWER_KEY, 'independent-review-model')

    def test_missing_writer_model_does_not_report_saved_key_missing(self):
        saved = self.save(api_key=WRITER_KEY, writer_model='', reviewer_model='')
        self.assertTrue(saved['has_key'])
        self.assertFalse(saved['configured'])
        self.assertIn('写作模型', saved['missing_fields'])
        self.assertNotIn('API密钥', saved['missing_fields'])
        before = len(self.outbound)
        response = self.client.post('/api/settings/test', json={'role': 'writer'})
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn('模型', response.json()['detail'])
        self.assertNotIn('请先保存你从官方平台领取的 Token', response.json()['detail'])
        self.assertEqual(len(self.outbound), before)
        self.assert_no_secrets(response)
        self.assertTrue(self.bootstrap()['has_key'])

        # Completing only the missing model field is enough; the key remains
        # server-side and does not have to be pasted a second time.
        corrected = self.save(api_key='', writer_model='writer-model', reviewer_model='')
        self.assertTrue(corrected['configured'])
        self.check_connection('writer', 'writer.example', WRITER_KEY, 'writer-model')

    def test_saved_keys_with_both_models_missing_report_only_missing_models(self):
        saved = self.save(api_key=WRITER_KEY, reviewer_api_key=REVIEWER_KEY,
                          writer_model='', reviewer_model='',
                          reviewer_base_url='https://reviewer.example/v1')
        self.assertFalse(saved['configured'])
        self.assertCountEqual(saved['missing_fields'], ['写作模型', '评审模型（独立评审服务）'])
        for role, label, source in [('writer', '写作模型', 'writer'),
                                    ('reviewer', '评审模型', 'reviewer')]:
            with self.subTest(role=role):
                status = saved['role_status'][role]
                self.assertTrue(status['has_key'])
                self.assertFalse(status['ready'])
                self.assertEqual(status['key_source'], source)
                self.assertEqual(status['missing_fields'], [label])
        actual = self.saved_status()
        self.assertEqual(actual['role_status'], saved['role_status'])
        self.assertEqual(self.outbound, [])

    def test_independent_reviewer_can_be_tested_when_writer_is_not_configured(self):
        saved = self.save(writer_model='', reviewer_api_key=REVIEWER_KEY,
                          reviewer_base_url='https://reviewer.example/v1',
                          reviewer_model='independent-review-model')
        self.assertFalse(saved['configured'])
        self.assertFalse(saved['has_key'])
        writer = saved['role_status']['writer']
        reviewer = saved['role_status']['reviewer']
        self.assertFalse(writer['has_key'])
        self.assertFalse(writer['ready'])
        self.assertCountEqual(writer['missing_fields'], ['API 密钥', '写作模型'])
        self.assertTrue(reviewer['has_key'])
        self.assertTrue(reviewer['ready'])
        self.assertFalse(reviewer['key_inherited'])
        self.assertEqual(reviewer['key_source'], 'reviewer')
        self.assertEqual(reviewer['missing_fields'], [])
        self.check_connection('reviewer', 'reviewer.example', REVIEWER_KEY, 'independent-review-model')
        # Independent role readiness is visible even while the complete writing
        # workflow is not configured, and checking it never needs a writer key.
        self.assertTrue(self.saved_status()['role_status']['reviewer']['ready'])


if __name__ == '__main__':
    unittest.main()
