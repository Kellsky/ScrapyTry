"""Official-provider integration checks with mocked HTTP, never real accounts."""

import base64
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import httpx
from PIL import Image

import app as studio
import engine
import providers


ORIGINAL_CLIENT = httpx.AsyncClient


def clients_with(handler):
    def client(**kwargs):
        return ORIGINAL_CLIENT(**kwargs, transport=httpx.MockTransport(handler), trust_env=False)
    return patch.object(httpx, 'AsyncClient', side_effect=client)


def configured(**overrides):
    return {'base_url': 'https://writer.example/v1', 'api_key': 'dummy-writer-key',
            'writer_model': 'writer-model', 'reviewer_model': 'reviewer-model',
            'vision_model': 'vision-model', 'reviewer_base_url': '',
            'reviewer_api_key': '', **overrides}


def completion(content='OK'):
    return httpx.Response(200, json={
        'choices': [{'message': {'content': content}, 'finish_reason': 'stop'}],
        'usage': {'prompt_tokens': 8, 'completion_tokens': 2, 'total_tokens': 10},
    })


class ProviderProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_model_listing_uses_saved_service_key_and_returns_ids_only(self):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(200, json={'data': [
                {'id': 'Qwen/Qwen3-8B', 'object': 'model', 'private': 'unneeded metadata'},
                {'id': 'Qwen/Qwen2.5-VL-72B-Instruct', 'object': 'model'},
            ]})

        with clients_with(handler):
            result = await providers.list_models(configured(), 'writer')
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].method, 'GET')
        self.assertEqual(str(calls[0].url), 'https://writer.example/v1/models')
        self.assertEqual(calls[0].headers['authorization'], 'Bearer dummy-writer-key')
        self.assertEqual(result['role'], 'writer')
        self.assertEqual({m['id'] for m in result['models']},
                         {'Qwen/Qwen3-8B', 'Qwen/Qwen2.5-VL-72B-Instruct'})
        self.assertNotIn('dummy-writer-key', json.dumps(result))
        self.assertNotIn('unneeded metadata', json.dumps(result))

    async def test_reviewer_model_list_uses_independent_endpoint_and_key(self):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(200, json={'data': [{'id': 'reviewer-model'}]})

        with clients_with(handler):
            result = await providers.list_models(configured(
                reviewer_base_url='https://reviewer.example/v1',
                reviewer_api_key='dummy-reviewer-key'), 'reviewer')
        self.assertEqual(calls[0].url.host, 'reviewer.example')
        self.assertEqual(calls[0].headers['authorization'], 'Bearer dummy-reviewer-key')
        self.assertEqual(result['role'], 'reviewer')

    async def test_distinct_reviewer_cannot_receive_writer_key(self):
        calls = []
        with clients_with(lambda request: calls.append(request) or completion()):
            with self.assertRaises(engine.EngineError):
                await providers.list_models(configured(
                    reviewer_base_url='https://reviewer.example/v1'), 'reviewer')
        self.assertEqual(calls, [])

    async def test_no_key_fails_without_remote_requests_or_demo_fallback(self):
        calls = []
        with clients_with(lambda request: calls.append(request) or completion()):
            for action in [providers.list_models, providers.test_connection]:
                with self.subTest(action=action.__name__), self.assertRaises(engine.EngineError):
                    await action(configured(api_key=''), 'writer')
        self.assertEqual(calls, [])

    async def test_missing_vision_model_fails_before_request(self):
        calls = []
        with clients_with(lambda request: calls.append(request) or completion()):
            with self.assertRaises(engine.EngineError):
                await providers.test_connection(configured(vision_model=''), 'vision')
        self.assertEqual(calls, [])

    async def test_text_connection_sends_bounded_real_protocol_request(self):
        calls = []

        def handler(request):
            calls.append(request)
            return completion()

        with clients_with(handler):
            result = await providers.test_connection(configured(), 'writer')
        self.assertTrue(result['ok'])
        self.assertEqual(result['role'], 'writer')
        self.assertEqual(result['model'], 'writer-model')
        self.assertEqual(len(calls), 1)
        payload = json.loads(calls[0].content)
        self.assertEqual(payload['model'], 'writer-model')
        self.assertLessEqual(payload['max_tokens'], 64)
        self.assertLess(len(json.dumps(payload['messages'])), 1000)
        self.assertNotIn('dummy-writer-key', json.dumps(result))

    async def test_vision_connection_actually_sends_image_part(self):
        calls = []

        def handler(request):
            calls.append(request)
            return completion()

        with clients_with(handler):
            result = await providers.test_connection(configured(), 'vision')
        self.assertTrue(result['ok'])
        payload = json.loads(calls[0].content)
        self.assertEqual(payload['model'], 'vision-model')
        self.assertLessEqual(payload['max_tokens'], 64)
        parts = [part for message in payload['messages'] if isinstance(message['content'], list)
                 for part in message['content']]
        images = [part for part in parts if part['type'] == 'image_url']
        self.assertEqual(len(images), 1)
        data_url = images[0]['image_url']['url']
        self.assertTrue(data_url.startswith('data:image/'))
        with Image.open(BytesIO(base64.b64decode(data_url.split(',', 1)[1]))) as image:
            self.assertLessEqual(max(image.size), 64)

    async def test_provider_errors_do_not_fall_back_or_echo_secrets(self):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(401, text='secret dummy-writer-key provider response')

        with clients_with(handler):
            for action in [providers.list_models, providers.test_connection]:
                with self.subTest(action=action.__name__):
                    with self.assertRaises(engine.EngineError) as caught:
                        await action(configured(), 'writer')
                    self.assertNotIn('dummy-writer-key', str(caught.exception))
                    self.assertNotIn('provider response', str(caught.exception))
        self.assertEqual(len(calls), 2)

    async def test_connection_budget_denial_never_sends_or_falls_back(self):
        calls = []

        def reserve(amount):
            raise engine.EngineError('测试预算不足')

        with clients_with(lambda request: calls.append(request) or completion()):
            with self.assertRaisesRegex(engine.EngineError, '预算不足'):
                await providers.test_connection(configured(_reserve_callback=reserve), 'writer')
        self.assertEqual(calls, [])

    async def test_oversized_model_list_rejected(self):
        with clients_with(lambda request: httpx.Response(200, content=b'x' * (1024 * 1024 + 1))):
            with self.assertRaises(engine.EngineError):
                await providers.list_models(configured(), 'writer')

    async def test_malformed_model_list_not_replaced_by_preset_guesses(self):
        for payload in [{'error': 'not a model list'}, {'data': 'wrong type'}]:
            with self.subTest(payload=payload), clients_with(lambda request: httpx.Response(200, json=payload)):
                with self.assertRaises(engine.EngineError):
                    await providers.list_models(configured(), 'writer')

    async def test_modelscope_qwen3_text_disables_thinking(self):
        calls = []

        def handler(request):
            calls.append(request)
            return completion()

        with clients_with(handler):
            await engine._call(configured(base_url='https://api-inference.modelscope.cn/v1'),
                               [{'role': 'user', 'content': '只回复OK'}], model='Qwen/Qwen3-8B', max_tokens=16)
        self.assertIs(json.loads(calls[0].content).get('enable_thinking'), False)

    async def test_modelscope_ocr_image_is_resized_to_provider_limit(self):
        source = BytesIO()
        Image.new('RGB', (3000, 1200), 'white').save(source, format='PNG')
        calls = []

        def handler(request):
            calls.append(request)
            return completion('识别到的征稿内容')

        with clients_with(handler):
            text = await engine.ocr_images([(source.getvalue(), 'image/png')], settings=configured(
                base_url='https://api-inference.modelscope.cn/v1'))
        self.assertEqual(text, '识别到的征稿内容')
        payload = json.loads(calls[0].content)
        parts = [part for message in payload['messages'] if isinstance(message['content'], list)
                 for part in message['content']]
        picture = next(part for part in parts if part['type'] == 'image_url')
        self.assertNotIn('detail', picture['image_url'])
        with Image.open(BytesIO(base64.b64decode(picture['image_url']['url'].split(',', 1)[1]))) as image:
            self.assertEqual(max(image.size), 2048)


class SavedSettingsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='gaojian-provider-tests-')
        self.previous_data = studio.DATA
        studio.DATA = Path(self.directory.name)
        self.environment = patch.dict(os.environ, {'WRITING_STUDIO_SEED': '0', 'WRITING_API_KEY': ''})
        self.environment.start()
        self.client = TestClient(studio.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        studio.DATA = self.previous_data
        self.environment.stop()
        self.directory.cleanup()

    def save(self, **updates):
        return self.client.put('/api/settings', json={
            'base_url': 'https://writer.example/v1', 'writer_model': 'writer-model',
            'reviewer_model': 'reviewer-model', 'vision_model': 'vision-model',
            'daily_limit': 100000, **updates})

    def test_saved_primary_key_preserved_for_same_host_but_not_new_host(self):
        first = self.save(api_key='dummy-writer-key')
        self.assertEqual(first.status_code, 200, first.text)
        preserved = self.save(base_url='https://writer.example/v2', api_key='')
        self.assertEqual(preserved.status_code, 200, preserved.text)
        self.assertTrue(preserved.json()['has_key'])
        blocked = self.save(base_url='https://different.example/v1', api_key='')
        self.assertEqual(blocked.status_code, 422, blocked.text)
        self.assertEqual(studio.settings()['base_url'], 'https://writer.example/v2')
        self.assertNotIn('dummy-writer-key', blocked.text)
        replaced = self.save(base_url='https://different.example/v1', api_key='dummy-new-key')
        self.assertEqual(replaced.status_code, 200, replaced.text)
        self.assertNotIn('dummy-new-key', replaced.text)

    def test_saved_reviewer_key_cannot_follow_changed_service_host(self):
        first = self.save(api_key='dummy-writer-key', reviewer_base_url='https://reviewer.example/v1',
                          reviewer_api_key='dummy-reviewer-key')
        self.assertEqual(first.status_code, 200, first.text)
        blocked = self.save(reviewer_base_url='https://other-reviewer.example/v1', reviewer_api_key='')
        self.assertEqual(blocked.status_code, 422, blocked.text)
        self.assertEqual(studio.settings()['reviewer_base_url'], 'https://reviewer.example/v1')
        self.assertNotIn('dummy-reviewer-key', blocked.text)

    def test_writing_service_alone_configures_shared_model_for_reviews(self):
        response = self.save(api_key='dummy-writer-key', writer_model='  writer-model  ',
                             reviewer_model='', reviewer_base_url='')
        self.assertEqual(response.status_code, 200, response.text)
        settings = response.json()
        self.assertTrue(settings['configured'], settings)
        self.assertEqual(settings['writer_model'], 'writer-model')
        self.assertEqual(settings['reviewer_model'], 'writer-model')
        self.assertEqual(settings['missing_fields'], [])
        self.assertEqual(studio.settings()['reviewer_model'], 'writer-model')
        self.assertEqual(self.client.get('/api/bootstrap').json()['settings']['reviewer_model'], 'writer-model')
        self.assertNotIn('dummy-writer-key', response.text)

    def test_missing_writer_model_reports_model_without_invalidating_saved_key(self):
        response = self.save(api_key='dummy-writer-key', writer_model='   ',
                             reviewer_model='', reviewer_base_url='')
        self.assertEqual(response.status_code, 200, response.text)
        settings = response.json()
        self.assertTrue(settings['has_key'])
        self.assertFalse(settings['configured'])
        self.assertIn('写作模型', settings['missing_fields'])
        self.assertNotIn('API密钥', settings['missing_fields'])
        self.assertNotIn('dummy-writer-key', response.text)

    def test_independent_review_service_requires_its_own_model(self):
        response = self.save(api_key='dummy-writer-key', reviewer_base_url='https://reviewer.example/v1',
                             reviewer_api_key='dummy-reviewer-key', reviewer_model='   ')
        self.assertEqual(response.status_code, 200, response.text)
        settings = response.json()
        self.assertFalse(settings['configured'])
        self.assertEqual(settings['reviewer_model'], '')
        self.assertEqual(studio.settings()['reviewer_model'], '')
        self.assertIn('评审模型（独立评审服务）', settings['missing_fields'])
        self.assertNotIn('API密钥', settings['missing_fields'])

    def test_masked_keys_rejected_without_changing_saved_configuration(self):
        saved = self.save(api_key='dummy-writer-key')
        self.assertEqual(saved.status_code, 200, saved.text)
        before = studio.settings()
        for field, masked in [('api_key', 'sk-test********tail'),
                              ('api_key', 'sk-••••1234'),
                              ('reviewer_api_key', 'ab●●●')]:
            with self.subTest(field=field, mask=masked):
                response = self.save(**{field: masked})
                self.assertEqual(response.status_code, 422, response.text)
                self.assertEqual(studio.settings(), before)
                self.assertNotIn(masked, response.text)
                self.assertNotIn('dummy-writer-key', response.text)

    def test_provider_catalog_is_public_and_credential_free(self):
        response = self.client.get('/api/providers')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn('modelscope', response.text.lower())
        self.assertNotIn('api_key', response.text)
        bootstrap = self.client.get('/api/bootstrap').json()
        self.assertIn('providers', bootstrap)


if __name__ == '__main__':
    unittest.main()
