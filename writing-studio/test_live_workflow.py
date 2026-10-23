"""Live-mode orchestration regressions using a deterministic fake provider.

The HTTP worker and engine execute normally. Only the external transport is
replaced; no account, real key, or external network is involved.
"""

import json
import os
from pathlib import Path
import re
import tempfile
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import httpx

import app as studio
import engine


SOURCE = '''征稿启事：城市里的微光
刊物：测试刊物
主题：一次陌生人的帮助
体裁：虚构短篇散文
字数：100—1000字
截止日期：2099年12月31日
投稿方式：demo@example.com
AI要求：允许使用AI创作。
征稿说明：请围绕陌生人之间一次具体的小小帮助展开，刻画人物动作和场景。语言朴素自然，避免空泛议论。正文应当是一篇完整的文学作品，而不是征稿信息说明或投稿要求的摘要。以上征稿内容用于本地测试，不会发给真实服务商，也不会进行实际投稿。'''

ARTICLE_A = '''门口的灯

入冬以后，巷口修鞋铺总比别家早亮灯。老人将灯拉到门外，光落在台阶上，正好照见路中那块松动的砖。

那天雨急，一个年轻人推着坏了轮子的箱子，走到灯下便停住了。老人放下鞋楦，从抽屉里找出一根细铁丝。两人蹲在檐下，不时换个位置躲雨，箱子的轮子终于重新转了起来。

年轻人摸出手机，老人却摆摆手，指了指脚边那只桶：帮我接点水就好。桶被搬到落雨的地方，空空的响声渐渐低了下来。

后来行人散去，巷子安静了。老人端着半桶水进屋，灯仍留在门外。那块松动的砖边上，多了一道从容绕过的车轮印。'''

ARTICLE_B = ARTICLE_A.replace('后来行人散去，巷子安静了。', '雨停之后，巷子慢慢安静了。')
ARTICLE_C = ARTICLE_B.replace('那块松动的砖边上，多了一道从容绕过的车轮印。',
                              '老人看见砖边的车轮印，便把灯向外又挪了一点。')
WRITER_KEY = 'dummy-live-writer-key'
REVIEW_KEY = 'dummy-live-reviewer-key'
ORIGINAL_CLIENT = httpx.AsyncClient


class Scenario:
    def __init__(self, writes=None, revisions=None, initial_issue=False):
        self.writes = writes or [ARTICLE_A]
        self.revisions = revisions or [ARTICLE_B]
        self.initial_issue = initial_issue
        self.calls = []
        self.write_calls = 0
        self.revision_calls = 0

    def handle(self, request):
        payload = json.loads(request.content)
        prompts = '\n'.join(message['content'] for message in payload['messages']
                            if message['role'] == 'user' and isinstance(message['content'], str))
        if '从资料中提取征稿要求' in prompts:
            stage = 'extract'
            content = json.dumps(engine.extract_local_requirements(SOURCE), ensure_ascii=False)
        elif '担任' in prompts and 'issues' in prompts:
            stage = 'review'
            issues = []
            if self.initial_issue and self.revision_calls == 0 and '你担任征稿编辑' in prompts:
                issues = [{'severity': 'medium', 'location': '结尾',
                           'problem': '结尾可以通过更具体的动作回应开头。',
                           'suggestion': '减少概括，补一个与灯呼应的动作。'}]
            content = json.dumps({'summary': '已按独立评审重点阅读稿件', 'issues': issues}, ensure_ascii=False)
        elif '请根据征稿硬性要求' in prompts:
            stage = 'revise'
            content = self.revisions[min(self.revision_calls, len(self.revisions) - 1)]
            self.revision_calls += 1
        elif '请根据以下资料生成' in prompts:
            stage = 'write'
            content = self.writes[min(self.write_calls, len(self.writes) - 1)]
            self.write_calls += 1
        else:
            raise AssertionError('Unexpected provider prompt in live workflow test')
        self.calls.append({'stage': stage, 'host': request.url.host,
                           'authorization': request.headers.get('authorization'),
                           'prompt': prompts})
        return httpx.Response(200, json={
            'choices': [{'message': {'content': content}, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 8, 'completion_tokens': 4, 'total_tokens': 12},
        })


class LiveWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='gaojian-live-flow-')
        self.old_data = studio.DATA
        studio.DATA = Path(self.directory.name)
        self.environment = patch.dict(os.environ, {'WRITING_STUDIO_SEED': '0', 'WRITING_API_KEY': ''})
        self.environment.start()
        self.scenario = Scenario()

        def client(**kwargs):
            return ORIGINAL_CLIENT(**kwargs, transport=httpx.MockTransport(self.scenario.handle), trust_env=False)

        self.transport = patch.object(httpx, 'AsyncClient', side_effect=client)
        self.transport.start()
        self.client = TestClient(studio.app)
        self.client.__enter__()
        saved = self.client.put('/api/settings', json={
            'base_url': 'https://writer.example/v1', 'api_key': WRITER_KEY,
            'writer_model': 'writer-model', 'reviewer_base_url': 'https://reviewer.example/v1',
            'reviewer_api_key': REVIEW_KEY, 'reviewer_model': 'review-model', 'daily_limit': 1000000,
        })
        self.assertEqual(saved.status_code, 200, saved.text)

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.transport.stop()
        self.environment.stop()
        studio.DATA = self.old_data
        self.directory.cleanup()

    def no_keys(self, response):
        self.assertNotIn(WRITER_KEY, response.text)
        self.assertNotIn(REVIEW_KEY, response.text)

    def create(self):
        response = self.client.post('/api/tasks', data={
            'source_type': 'text', 'content': SOURCE, 'mode': 'live',
            'fiction': 'true', 'max_rounds': '2',
        })
        self.assertEqual(response.status_code, 202, response.text)
        self.no_keys(response)
        return response.json()['id']

    def wait(self, task_id):
        timeout = time.monotonic() + 10
        while time.monotonic() < timeout:
            response = self.client.get('/api/tasks/' + task_id)
            self.assertEqual(response.status_code, 200, response.text)
            self.no_keys(response)
            task = response.json()
            if task['status'] not in {'queued', 'extracting', 'writing', 'reviewing', 'revising'}:
                return task
            time.sleep(.04)
        self.fail('Live-mode task did not reach a terminal state')

    def assert_article(self, task, expected):
        self.assertEqual(task['status'], 'needs_review', task['message'])
        self.assertEqual(task['mode'], 'live')
        self.assertEqual(task['draft'], expected)
        self.assertNotEqual(task['draft'], task['source_text'])
        self.assertEqual(task['source_text'], SOURCE)
        self.assertEqual(task['requirements']['topic'], '一次陌生人的帮助')
        self.assertEqual(task['requirements']['min_words'], 100)
        self.assertFalse([check for check in task['checks'] if check['status'] == 'fail'], task['checks'])

    def assert_no_notice_saved(self, task):
        self.assertEqual(task['status'], 'failed', task['message'])
        self.assertRegex(task['message'], '征稿原文|未生成')
        self.assertEqual(task['draft'], '')
        self.assertEqual(task['versions'], [])
        self.assertEqual(task['source_text'], SOURCE)
        self.assertEqual(self.scenario.write_calls, 2, '最多一次纠错重试，不能无限重复收费调用')
        self.assertFalse([call for call in self.scenario.calls if call['stage'] == 'review'])

    def test_complete_live_flow_produces_article_reviews_and_revised_versions(self):
        self.scenario = Scenario(initial_issue=True, revisions=[ARTICLE_B, ARTICLE_C])
        task = self.wait(self.create())
        self.assert_article(task, ARTICLE_B)
        self.assertEqual(task['round'], 1)
        self.assertEqual([version['content'] for version in task['versions']], [ARTICLE_A, ARTICLE_B])
        self.assertEqual([review['issues'] for review in task['reviews']], [[], []])
        stages = [call['stage'] for call in self.scenario.calls]
        self.assertEqual(stages, ['extract', 'write', 'review', 'review', 'revise', 'review', 'review'])
        self.assertTrue({'extracting', 'writing', 'reviewing', 'revising', 'needs_review'} <=
                        {event['stage'] for event in task['events']})
        for call in self.scenario.calls:
            if call['stage'] == 'review':
                self.assertEqual(call['host'], 'reviewer.example')
                self.assertEqual(call['authorization'], 'Bearer ' + REVIEW_KEY)
            else:
                self.assertEqual(call['host'], 'writer.example')
                self.assertEqual(call['authorization'], 'Bearer ' + WRITER_KEY)

        response = self.client.post(f"/api/tasks/{task['id']}/refine", json={'instruction': '请用挪灯的动作收尾。'})
        self.assertEqual(response.status_code, 202, response.text)
        revised = self.wait(task['id'])
        self.assert_article(revised, ARTICLE_C)
        self.assertEqual([version['content'] for version in revised['versions']], [ARTICLE_A, ARTICLE_B, ARTICLE_C])
        self.assertIn('请用挪灯的动作收尾。', next(call['prompt'] for call in reversed(self.scenario.calls) if call['stage'] == 'revise'))
        usage_response = self.client.get('/api/bootstrap')
        self.no_keys(usage_response)
        self.assertEqual(usage_response.json()['settings']['used_tokens'], len(self.scenario.calls) * 12)

    def test_persistent_verbatim_notice_is_rejected_before_becoming_a_draft(self):
        self.scenario = Scenario(writes=[SOURCE])
        self.assert_no_notice_saved(self.wait(self.create()))

    def test_notice_with_markdown_wrapper_or_changed_punctuation_is_rejected(self):
        variants = ['# 投稿文章\n\n' + SOURCE + '\n\n以上是本次作品。',
                    ''.join(re.findall(r'[\u3400-\u9fffA-Za-z0-9]', SOURCE)),
                    SOURCE[:len(SOURCE) // 2]]
        for copied in variants:
            with self.subTest(variant=copied[:20]):
                self.assertGreaterEqual(len(re.sub(r'[\W_]+', '', copied)), 40)
                self.scenario = Scenario(writes=[copied])
                self.assert_no_notice_saved(self.wait(self.create()))
        article_with_short_quote = ARTICLE_A + '\n\n它让我想起一句话：“一次陌生人的帮助”。'
        self.assertFalse(engine.repeats_notice(article_with_short_quote, SOURCE),
                         '新文章包含一小句与主题相关的引文，不应被认作征稿原文回显')

    def test_one_notice_echo_gets_one_corrective_retry_then_accepts_new_article(self):
        self.scenario = Scenario(writes=[SOURCE, ARTICLE_A])
        task = self.wait(self.create())
        self.assert_article(task, ARTICLE_A)
        self.assertEqual(self.scenario.write_calls, 2)
        self.assertEqual([version['content'] for version in task['versions']], [ARTICLE_A])

    def test_automatic_revision_echo_preserves_previous_valid_article(self):
        self.scenario = Scenario(initial_issue=True, revisions=[SOURCE])
        task = self.wait(self.create())
        self.assertEqual(task['status'], 'failed', task['message'])
        self.assertRegex(task['message'], '征稿原文|未生成')
        self.assertEqual(task['draft'], ARTICLE_A)
        self.assertEqual([version['content'] for version in task['versions']], [ARTICLE_A])
        self.assertEqual(self.scenario.revision_calls, 2)

    def test_author_requested_revision_echo_preserves_previous_valid_article(self):
        self.scenario = Scenario(revisions=[SOURCE])
        initial = self.wait(self.create())
        self.assert_article(initial, ARTICLE_A)
        response = self.client.post(f"/api/tasks/{initial['id']}/refine", json={'instruction': '请进一步压缩结尾。'})
        self.assertEqual(response.status_code, 202, response.text)
        task = self.wait(initial['id'])
        self.assertEqual(task['status'], 'failed', task['message'])
        self.assertRegex(task['message'], '征稿原文|未生成')
        self.assertEqual(task['draft'], ARTICLE_A)
        self.assertEqual([version['content'] for version in task['versions']], [ARTICLE_A])
        self.assertEqual(self.scenario.revision_calls, 2)

    def test_legacy_notice_cannot_be_approved_and_can_be_regenerated_without_losing_history(self):
        legacy = studio.new_task('旧任务的原文回显', 'text', SOURCE, mode='live')
        legacy.update(status='needs_review', stage='needs_review', requirements=engine.extract_local_requirements(SOURCE),
                      draft=SOURCE, word_count=engine.count_words(SOURCE), round=1, _action='complete',
                      _reviewed_version=0, versions=[{'round': 0, 'title': '旧版历史内容',
                                                    'content': SOURCE, 'created_at': studio.now()}])
        studio.store().save(legacy)
        approval = self.client.post(f"/api/tasks/{legacy['id']}/approve", json={'acknowledged': True})
        self.assertEqual(approval.status_code, 409, approval.text)
        self.assertEqual(self.scenario.calls, [], '旧错误稿件的批准检查不应触发远程调用')
        blocked = self.client.get(f"/api/tasks/{legacy['id']}")
        self.assertEqual(blocked.status_code, 200, blocked.text)
        self.no_keys(blocked)
        blocked_task = blocked.json()
        self.assertEqual(blocked_task['draft'], SOURCE)
        self.assertIn('尚未生成', ' '.join(blocked_task['blockers']))
        self.assertTrue(any(check['status'] == 'fail' and check['label'] == '投稿文章'
                            for check in blocked_task['checks']))

        response = self.client.post(f"/api/tasks/{legacy['id']}/retry", json={'regenerate': True})
        self.assertEqual(response.status_code, 202, response.text)
        self.no_keys(response)
        queued = response.json()
        self.assertEqual(queued['word_count'], 0)
        self.assertEqual(queued['draft'], '')
        self.assertEqual(queued['source_text'], SOURCE)
        self.assertEqual([version['content'] for version in queued['versions']], [SOURCE])
        regenerated = self.wait(legacy['id'])
        self.assert_article(regenerated, ARTICLE_A)
        self.assertEqual([version['content'] for version in regenerated['versions']], [SOURCE, ARTICLE_A])
        self.assertEqual(regenerated['round'], 0)
        self.assertEqual([call['stage'] for call in self.scenario.calls], ['extract', 'write', 'review', 'review'])


if __name__ == '__main__':
    unittest.main()
