"""Integration checks for the actual durable demo workflow.

Run: python3 -m unittest -v test_app
No live model credentials, provider calls, or external network are required.
"""
from io import BytesIO
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from docx import Document
from fastapi.testclient import TestClient
from PIL import Image

import app as studio
import engine


TERMINAL = {'needs_input', 'needs_review', 'approved', 'failed'}


class WorkflowIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='gaojian-integration-')
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

    def create(self, source=None, **overrides):
        data = {'title': '集成测试征稿', 'source_type': 'text',
                'content': source or engine.demo_source(), 'mode': 'demo',
                'max_rounds': '2', 'fiction': 'true'}
        data.update(overrides)
        response = self.client.post('/api/tasks', data=data)
        self.assertEqual(response.status_code, 202, response.text)
        return response.json()['id']

    def wait(self, task_id):
        deadline = time.monotonic() + 20
        last = None
        while time.monotonic() < deadline:
            response = self.client.get(f'/api/tasks/{task_id}')
            self.assertEqual(response.status_code, 200, response.text)
            last = response.json()
            if last['status'] in TERMINAL:
                return last
            time.sleep(0.08)
        self.fail(f'Task did not reach a terminal state: {last!r}')

    def ready(self):
        task = self.wait(self.create())
        self.assertEqual(task['status'], 'needs_review', task)
        self.assertTrue(task['draft'].strip())
        self.assertFalse([c for c in task['checks'] if c['status'] == 'fail'], task['checks'])
        return task

    def test_demo_runs_original_pipeline_and_exports_real_documents(self):
        task = self.ready()
        self.assertEqual(task['mode'], 'demo')
        self.assertGreater(task['word_count'], 100)
        self.assertGreaterEqual(len(task['reviews']), 2)
        self.assertTrue(task['versions'])
        self.assertLessEqual(task['round'], task['max_rounds'])
        self.assertGreaterEqual(len(task['events']), 4)
        self.assertFalse(any(key.startswith('_') for key in task))
        self.assertTrue(any(c['status'] == 'warn' and '演示' in c['detail'] for c in task['checks']))

        prefix = f"/api/tasks/{task['id']}/export"
        plain = self.client.get(prefix, params={'format': 'txt'})
        self.assertEqual(plain.status_code, 200)
        text = plain.content.decode('utf-8-sig')
        self.assertIn(task['draft'], text)
        self.assertIn('演示', text)
        self.assertIn('attachment;', plain.headers['content-disposition'])

        word = self.client.get(prefix, params={'format': 'docx'})
        self.assertEqual(word.status_code, 200)
        document = Document(BytesIO(word.content))
        body = '\n'.join(paragraph.text for paragraph in document.paragraphs)
        self.assertIn(task['title'], body)
        self.assertIn(task['draft'].splitlines()[-1], body)
        self.assertIn('演示', body)

        email = self.client.get(prefix, params={'format': 'email'})
        self.assertEqual(email.status_code, 200)
        email_text = email.content.decode('utf-8-sig')
        self.assertIn(task['draft'], email_text)
        self.assertIn('未执行发送', email_text)
        self.assertEqual(self.client.get(f"/api/tasks/{task['id']}").json()['status'], 'needs_review')
        self.assertEqual(self.client.get('/api/bootstrap').json()['settings']['used_tokens'], 0)

    def test_generation_gates_forbidden_expired_and_missing_real_material(self):
        cases = [
            ('AI ban', engine.demo_source() + '\n严禁使用AI创作，禁止AI生成稿件。', {}, 'AI'),
            ('expired', '征稿主题：生活中的微光\n体裁：虚构散文\n字数：500-1000字\n'
             '截止日期：2020-01-01\n允许使用AI辅助写作。', {}, '截止'),
            ('nonfiction', '征稿主题：我与父亲的真实故事\n体裁：纪实散文\n字数：500-1000字\n'
             '必须根据作者真实亲身经历创作，不得虚构。允许AI辅助润色。', {'fiction': 'false'}, '真实'),
            ('multiple notices', '刊物：示例甲刊\n主题：日常生活\n字数：800-1200字\n'
             '刊物：示例乙刊\n主题：自然观察\n字数：1500-2000字\n允许AI创作。', {}, '多'),
        ]
        for name, source, options, expected in cases:
            with self.subTest(name=name):
                task = self.wait(self.create(source, **options))
                self.assertEqual(task['status'], 'needs_input', task)
                self.assertEqual(task['draft'], '')
                self.assertEqual(task['versions'], [])
                self.assertIn(expected, ' '.join(task['blockers']))

    def test_screenshot_waits_for_real_ocr_then_accepts_text_fallback(self):
        buffer = BytesIO()
        Image.new('RGB', (12, 12), 'white').save(buffer, format='PNG')
        response = self.client.post('/api/tasks', data={
            'source_type': 'images', 'mode': 'demo', 'fiction': 'true',
        }, files=[('images', ('source.png', buffer.getvalue(), 'image/png'))])
        self.assertEqual(response.status_code, 202, response.text)
        task = self.wait(response.json()['id'])
        self.assertEqual(task['status'], 'needs_input', task)
        self.assertFalse(task['source_text'])
        self.assertFalse(task['draft'])
        self.assertTrue(list((studio.DATA / 'uploads' / task['id']).iterdir()))

        retry = self.client.post(f"/api/tasks/{task['id']}/retry", json={'content': engine.demo_source()})
        self.assertEqual(retry.status_code, 202, retry.text)
        completed = self.wait(task['id'])
        self.assertEqual(completed['status'], 'needs_review', completed)
        self.assertEqual(completed['source_type'], 'text')
        self.assertTrue(completed['draft'])

    def test_manual_edit_invalidates_reviews_and_approval_enforces_hard_checks(self):
        task = self.ready()
        task_id = task['id']
        self.assertEqual(self.client.post(f'/api/tasks/{task_id}/approve', json={}).status_code, 422)
        short = self.client.post(f'/api/tasks/{task_id}/edit', json={'draft': '太短。'})
        self.assertEqual(short.status_code, 200, short.text)
        edited = short.json()
        self.assertEqual(edited['reviews'], [])
        self.assertEqual(len(edited['versions']), len(task['versions']) + 1)
        self.assertTrue(any(c['status'] == 'fail' for c in edited['checks']))
        blocked = self.client.post(f'/api/tasks/{task_id}/approve', json={'acknowledged': True})
        self.assertEqual(blocked.status_code, 409, blocked.text)

        restored = self.client.post(f'/api/tasks/{task_id}/edit', json={'draft': task['draft']})
        self.assertEqual(restored.status_code, 200, restored.text)
        approved = self.client.post(f'/api/tasks/{task_id}/approve', json={'acknowledged': True})
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()['status'], 'approved')
        self.assertIn('尚未发送', approved.json()['message'])

    def test_refinement_creates_a_new_version_and_rechecks_it(self):
        task = self.ready()
        response = self.client.post(f"/api/tasks/{task['id']}/refine", json={
            'instruction': '请缩短开头，加入雨后街角的细节，结尾更克制。',
        })
        self.assertEqual(response.status_code, 202, response.text)
        changed = self.wait(task['id'])
        self.assertEqual(changed['status'], 'needs_review', changed)
        self.assertEqual(len(changed['versions']), len(task['versions']) + 1)
        self.assertNotEqual(changed['draft'], task['draft'])
        self.assertEqual(changed['versions'][-1]['title'], '按作者意见修改')
        self.assertGreaterEqual(len(changed['reviews']), 2)
        self.assertTrue(changed['checks'])

    def test_source_replacement_clears_stale_drafts_and_checks(self):
        task = self.ready()
        source = '新征稿：请以日常细节为主题撰写散文，字数800至1200字。明确禁止AI创作和AI生成稿件。'
        response = self.client.post(f"/api/tasks/{task['id']}/retry", json={'content': source})
        self.assertEqual(response.status_code, 202, response.text)
        changed = self.wait(task['id'])
        self.assertEqual(changed['status'], 'needs_input', changed)
        self.assertEqual(changed['source_text'], source)
        self.assertEqual(changed['draft'], '')
        self.assertEqual(changed['versions'], [])
        self.assertEqual(changed['reviews'], [])

    def test_configuration_never_returns_keys_and_unconfigured_live_is_rejected(self):
        response = self.client.post('/api/tasks', data={
            'source_type': 'text', 'mode': 'live', 'content': engine.demo_source(),
        })
        self.assertEqual(response.status_code, 400, response.text)
        key = 'test-key-never-use-over-network'
        reviewer_key = 'test-reviewer-key-never-use-over-network'
        settings = {'base_url': 'https://example.com/v1', 'api_key': key,
                    'reviewer_base_url': 'https://reviewer.example/v1', 'reviewer_api_key': reviewer_key,
                    'writer_model': 'test-writer', 'reviewer_model': 'test-reviewer',
                    'vision_model': '', 'daily_limit': 100000}
        no_reviewer_key = {**settings, 'reviewer_api_key': ''}
        rejected = self.client.put('/api/settings', json=no_reviewer_key)
        self.assertEqual(rejected.status_code, 422, rejected.text)
        saved = self.client.put('/api/settings', json=settings)
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertNotIn(key, saved.text)
        self.assertNotIn(reviewer_key, saved.text)
        self.assertNotIn('api_key', saved.json())
        self.assertNotIn('reviewer_api_key', saved.json())
        self.assertTrue(saved.json()['has_key'])
        self.assertTrue(saved.json()['has_reviewer_key'])
        settings['api_key'] = ''
        settings['reviewer_api_key'] = ''
        preserved = self.client.put('/api/settings', json=settings).json()
        self.assertTrue(preserved['has_key'])
        self.assertTrue(preserved['has_reviewer_key'])
        bootstrap = self.client.get('/api/bootstrap')
        self.assertNotIn(key, bootstrap.text)
        self.assertNotIn(reviewer_key, bootstrap.text)
        self.assertTrue(bootstrap.json()['settings']['configured'])

    def test_profile_materials_satisfy_real_experience_precondition(self):
        source = ('征稿主题：一次耐心的等待\n体裁：纪实散文\n字数：500-1500字\n'
                  '必须根据作者真实亲身经历创作，不得虚构。允许AI辅助润色。')
        response = self.client.put('/api/profile', json={
            'pen_name': '测试笔名', 'style': '克制具体。',
            'materials': '我昨天在公交站等车时遇到一位邻居，我们聊起了天气。这是作者提供的测试素材。',
        })
        self.assertEqual(response.status_code, 200, response.text)
        task = self.wait(self.create(source, fiction='false'))
        self.assertEqual(task['status'], 'needs_review', task)
        self.assertFalse([c for c in task['checks'] if c['label'] == '真实经历素材' and c['status'] == 'fail'])
        self.assertIn('公交站等车', task['draft'])

    def test_task_and_profile_survive_server_restart_and_can_be_deleted(self):
        task = self.ready()
        saved_profile = {'pen_name': '测试笔名', 'style': '短句，具体。', 'materials': '这是测试素材。'}
        response = self.client.put('/api/profile', json=saved_profile)
        self.assertEqual(response.status_code, 200, response.text)
        self.client.__exit__(None, None, None)
        self.client = TestClient(studio.app)
        self.client.__enter__()
        recovered = self.client.get(f"/api/tasks/{task['id']}")
        self.assertEqual(recovered.status_code, 200, recovered.text)
        self.assertEqual(recovered.json()['draft'], task['draft'])
        self.assertEqual(recovered.json()['versions'], task['versions'])
        self.assertEqual(self.client.get('/api/bootstrap').json()['profile'], saved_profile)
        removed = self.client.delete(f"/api/tasks/{task['id']}")
        self.assertEqual(removed.status_code, 200, removed.text)
        self.assertEqual(self.client.get(f"/api/tasks/{task['id']}").status_code, 404)

    def test_invalid_upload_and_cross_origin_writes_are_rejected(self):
        invalid = self.client.post('/api/tasks', data={'source_type': 'images'}, files=[
            ('images', ('fake.png', b'This is not an image.', 'image/png')),
        ])
        self.assertEqual(invalid.status_code, 422, invalid.text)
        cross_origin = self.client.put('/api/profile', json={'pen_name': 'injected'},
                                       headers={'Origin': 'https://different.example'})
        self.assertEqual(cross_origin.status_code, 403, cross_origin.text)
        self.assertEqual(self.client.get('/api/bootstrap').json()['profile']['pen_name'], '')


if __name__ == '__main__':
    unittest.main()
