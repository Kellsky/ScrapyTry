"""Provider protocol and trust-boundary tests; no external model calls."""

import json
import unittest
from unittest.mock import patch

import httpx

import engine


ORIGINAL_CLIENT = httpx.AsyncClient


def reply(content='完整的模型答复', *, usage=True, finish='stop'):
    payload = {'choices': [{'message': {'content': content}, 'finish_reason': finish}]}
    if usage:
        payload['usage'] = {'prompt_tokens': 17, 'completion_tokens': 23, 'total_tokens': 40}
    return httpx.Response(200, json=payload)


def clients_with(handler):
    def client(**kwargs):
        return ORIGINAL_CLIENT(**kwargs, transport=httpx.MockTransport(handler), trust_env=False)
    return patch.object(engine.httpx, 'AsyncClient', side_effect=client)


def configured(**overrides):
    return {'base_url': 'https://writer.example/v1', 'api_key': 'dummy-writer-key',
            'writer_model': 'test-writer', 'reviewer_model': 'test-reviewer', **overrides}


class ModelProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_call_payload_usage_and_reservations(self):
        calls, reservations, releases, usage = [], [], [], []

        def handler(request):
            calls.append(request)
            return reply()

        settings = configured(_reserve_callback=reservations.append,
                              _release_callback=releases.append, _usage_callback=usage.append)
        with clients_with(handler):
            content = await engine._call(settings, [{'role': 'user', 'content': '测试中文'}],
                                         model='test-writer', max_tokens=500)
        self.assertEqual(content, '完整的模型答复')
        self.assertEqual(str(calls[0].url), 'https://writer.example/v1/chat/completions')
        self.assertEqual(calls[0].headers['authorization'], 'Bearer dummy-writer-key')
        self.assertEqual(json.loads(calls[0].content)['model'], 'test-writer')
        self.assertEqual(json.loads(calls[0].content)['max_tokens'], 500)
        self.assertEqual(reservations, releases)
        self.assertEqual(usage, [{'prompt_tokens': 17, 'completion_tokens': 23,
                                  'total_tokens': 40, 'estimated': False}])

    async def test_missing_usage_is_charged_conservatively(self):
        reservations, releases, usage = [], [], []
        settings = configured(_reserve_callback=reservations.append,
                              _release_callback=releases.append, _usage_callback=usage.append)
        with clients_with(lambda request: reply(usage=False)):
            await engine._call(settings, [{'role': 'user', 'content': '一条请求'}], model='test')
        self.assertEqual(reservations, releases)
        self.assertEqual(usage[0]['total_tokens'], reservations[0])
        self.assertTrue(usage[0]['estimated'])

    async def test_truncated_output_rejected_but_usage_retained(self):
        reservations, releases, usage = [], [], []
        settings = configured(_reserve_callback=reservations.append,
                              _release_callback=releases.append, _usage_callback=usage.append)
        with clients_with(lambda request: reply('未完成的文章', finish='length')):
            with self.assertRaisesRegex(engine.EngineError, '截断|长度上限'):
                await engine._call(settings, [{'role': 'user', 'content': '写作'}], model='test')
        self.assertEqual(reservations, releases)
        self.assertEqual(usage[0]['total_tokens'], 40)

    async def test_oversized_response_rejected_and_reservation_released(self):
        reservations, releases, usage = [], [], []
        settings = configured(_reserve_callback=reservations.append,
                              _release_callback=releases.append, _usage_callback=usage.append)
        with clients_with(lambda request: httpx.Response(200, content=b'x' * (1024 * 1024 + 1))):
            with self.assertRaisesRegex(engine.EngineError, '大小上限'):
                await engine._call(settings, [{'role': 'user', 'content': '写作'}], model='test')
        self.assertEqual(reservations, releases)
        self.assertTrue(usage[0]['estimated'])

    async def test_api_errors_do_not_echo_credentials_or_raw_response(self):
        with clients_with(lambda request: httpx.Response(401, text='dummy-writer-key secret response')):
            with self.assertRaises(engine.EngineError) as caught:
                await engine._call(configured(), [{'role': 'user', 'content': '写作'}], model='test')
        self.assertNotIn('dummy-writer-key', str(caught.exception))
        self.assertNotIn('secret response', str(caught.exception))

    async def test_budget_denial_prevents_remote_request(self):
        calls = []

        def reserve(amount):
            raise engine.EngineError('每日预算不足')

        with clients_with(lambda request: calls.append(request) or reply()):
            with self.assertRaisesRegex(engine.EngineError, '预算不足'):
                await engine._call(configured(_reserve_callback=reserve),
                                   [{'role': 'user', 'content': '写作'}], model='test')
        self.assertEqual(calls, [])

    async def test_live_json_and_explicit_source_ban_take_priority(self):
        source = '刊物：测试刊物\n主题：城市生活\n字数：600—900字\nAI要求：禁止使用 AI 创作。'
        result = engine.extract_local_requirements(source)
        result.update(ai_policy='allowed', min_words=100, max_words=5000)
        with clients_with(lambda request: reply('```json\n' + json.dumps(result) + '\n```')):
            requirements = await engine.extract_requirements(source, settings=configured(), mode='live',
                                                              fiction=True, author_notes='')
        self.assertEqual(requirements['ai_policy'], 'forbidden')
        self.assertEqual((requirements['min_words'], requirements['max_words']), (600, 900))
        self.assertEqual(requirements['source_excerpt'], source)

    async def test_invalid_model_json_is_not_accepted_as_requirements(self):
        with clients_with(lambda request: reply('模型输出了一段散文，而不是 JSON')):
            with self.assertRaisesRegex(engine.EngineError, '结构化'):
                await engine.extract_requirements(engine.demo_source(), settings=configured(),
                                                  mode='live', fiction=True, author_notes='')

    async def test_ambiguous_deadline_year_is_not_inferred_by_model(self):
        source = '刊物：测试刊物\n主题：城市生活\n字数：600—900字\n截止日期：10月31日。'
        result = engine.extract_local_requirements(source)
        result['deadline'] = '2027-10-31'
        with clients_with(lambda request: reply(json.dumps(result))):
            requirements = await engine.extract_requirements(source, settings=configured(), mode='live',
                                                              fiction=True, author_notes='')
        self.assertEqual(requirements['deadline'], '', '模型不能自行给无年份的截止日期补上年份')

    async def test_two_independent_reviews_use_reviewer_service_and_key(self):
        calls = []

        def handler(request):
            calls.append(request)
            return reply(json.dumps({'summary': '结构与表达已检查', 'issues': []}))

        settings = configured(reviewer_base_url='https://reviewer.example/v1',
                              reviewer_api_key='dummy-reviewer-key')
        with clients_with(handler):
            reviews = await engine.review_draft('一篇文章', engine.extract_local_requirements(engine.demo_source()),
                                                 settings=settings, mode='live')
        self.assertEqual(len(reviews), 2)
        self.assertEqual({review['role'] for review in reviews}, {'征稿编辑', '文字编辑'})
        self.assertEqual(len(calls), 2)
        for call in calls:
            self.assertEqual(call.url.host, 'reviewer.example')
            self.assertEqual(call.headers['authorization'], 'Bearer dummy-reviewer-key')
            self.assertEqual(json.loads(call.content)['model'], 'test-reviewer')
        self.assertNotEqual(json.loads(calls[0].content)['messages'], json.loads(calls[1].content)['messages'])

    async def test_distinct_reviewer_service_cannot_receive_writer_key(self):
        calls = []

        def handler(request):
            calls.append(request)
            return reply(json.dumps({'summary': '不应发送这次请求', 'issues': []}))

        with clients_with(handler):
            with self.assertRaises(engine.EngineError):
                await engine.review_draft('文章', {}, settings=configured(
                    reviewer_base_url='https://reviewer.example/v1'), mode='live')
        self.assertEqual(calls, [], '没有单独的评审凭据时不得向另一个服务商发送写作服务密钥')


class SourceBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_unknown_and_local_source_urls_never_issue_network_requests(self):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(200, text='should not be requested')

        with clients_with(handler):
            for url in ['http://127.0.0.1/private', 'http://localhost/admin',
                        'http://169.254.169.254/latest/meta-data/', 'https://example.com/article']:
                with self.subTest(url=url), self.assertRaises(engine.EngineError):
                    await engine.fetch_source(url)
        self.assertEqual(calls, [])

    async def test_article_redirect_cannot_reach_private_destination(self):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(302, headers={'location': 'http://127.0.0.1/internal'})

        # Simulate successful public DNS validation only for the initial host.
        async def public_only(url):
            self.assertEqual(httpx.URL(url).host, 'mp.weixin.qq.com')

        with clients_with(handler), patch.object(engine, '_validate_public_url', side_effect=public_only):
            with self.assertRaisesRegex(engine.EngineError, '重定向'):
                await engine.fetch_source('https://mp.weixin.qq.com/s/example')
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].url.host, 'mp.weixin.qq.com')

    def test_bans_and_limited_ai_permissions(self):
        for text in ['本刊禁止使用AI创作。', '我们不接受人工智能生成作品。', 'AI稿件谢绝投稿。']:
            with self.subTest(text=text):
                self.assertEqual(engine.extract_local_requirements(text)['ai_policy'], 'forbidden')
        self.assertEqual(engine.extract_local_requirements('允许AI辅助润色。')['ai_policy'], 'unknown')
        self.assertEqual(engine.extract_local_requirements('本刊不禁止AI创作。')['ai_policy'], 'allowed')

    def test_missing_year_stays_unknown_and_compilation_is_flagged(self):
        result = engine.extract_local_requirements('刊物：甲\n截止日期：10月31日\n刊物：乙\n字数：500—800字')
        self.assertEqual(result['deadline'], '')
        self.assertTrue(result['multiple_notices'])


if __name__ == '__main__':
    unittest.main()
