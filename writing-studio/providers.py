"""Official provider presets and explicit, small account connection checks."""
import base64
from io import BytesIO
from urllib.parse import urlsplit

import httpx
from PIL import Image

import engine

PROVIDERS = [{
    'id': 'modelscope',
    'name': '魔搭 ModelScope · 每日免费额度',
    'base_url': 'https://api-inference.modelscope.cn/v1',
    'writer_model': 'Qwen/Qwen3-235B-A22B-Instruct-2507',
    'reviewer_model': 'Qwen/Qwen3-235B-A22B-Instruct-2507',
    'vision_model': 'Qwen/Qwen3-VL-8B-Instruct',
    'signup_url': 'https://modelscope.cn/my/myaccesstoken',
    'docs_url': 'https://github.com/modelscope/ms-agent/blob/fd6ea88422a399db8b303848dc6c6ec4e17daf6e/docs/zh/Projects/deep-research.md#L151',
    'free_note': '官方说明注册用户有每日免费 API 调用额度。具体额度、可用模型及认证要求以你的账号页面为准，不承诺无限或永久免费。示例模型来自官方仓库，请先测试当前账号能否使用。',
}]


def select_role(settings, role):
    if role not in {'writer', 'reviewer', 'vision'}:
        raise engine.EngineError('不支持的模型角色')
    selected = dict(settings)
    if role == 'reviewer':
        review_url = settings.get('reviewer_base_url') or settings.get('base_url')
        if settings.get('reviewer_base_url') and not settings.get('reviewer_api_key'):
            original, reviewer = urlsplit(settings['base_url']), urlsplit(review_url)
            if (original.scheme, original.netloc.lower()) != (reviewer.scheme, reviewer.netloc.lower()):
                raise engine.EngineError('独立评审服务需要自己的密钥，不会发送写作服务的密钥。')
        selected['base_url'] = review_url
        selected['api_key'] = settings.get('reviewer_api_key') or settings.get('api_key')
        selected['model'] = settings.get('reviewer_model') or settings.get('writer_model')
    else:
        selected['model'] = settings.get('vision_model' if role == 'vision' else 'writer_model')
    if not selected.get('api_key'):
        raise engine.EngineError('请先保存你从官方平台领取的 Token，再测试连接或读取模型。')
    return selected


def status_error(status):
    if status == 401:
        return '平台拒绝认证，请检查 Token 是否有效及是否具备 API 推理权限。'
    if status == 403:
        return '平台或网络代理返回 403，请核对账号权限、服务地区及网络域名规则。'
    if status == 429:
        return '平台限流或免费额度暂时不足，请查看账号控制台并稍后重试。'
    if status == 404:
        return '平台未提供兼容的模型列表接口，请从官方控制台复制模型 ID；仍可单独测试模型连接。'
    return f'平台返回 HTTP {status}，请检查 API 地址及账号状态。'


async def list_models(settings, role):
    selected = select_role(settings, role)
    endpoint = engine._endpoint(selected).removesuffix('/chat/completions') + '/models'
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(25, connect=10), follow_redirects=False) as client:
            async with client.stream('GET', endpoint, headers={'Authorization': 'Bearer ' + selected['api_key']}) as response:
                if not 200 <= response.status_code < 300:
                    raise engine.EngineError(status_error(response.status_code))
                raw = bytearray()
                async for chunk in response.aiter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 1024 * 1024:
                        raise engine.EngineError('平台模型列表过大，请直接在控制台选择模型并复制 ID。')
        import json
        try:
            payload = json.loads(raw)
            records = payload.get('data')
            if not isinstance(records, list):
                raise ValueError('Invalid model list')
            ids = sorted({row['id'] for row in records if isinstance(row, dict) and isinstance(row.get('id'), str) and 0 < len(row['id']) <= 200})
        except (TypeError, ValueError, AttributeError) as exc:
            raise engine.EngineError('平台没有返回兼容的模型列表，请从官方控制台复制模型 ID。') from exc
        return {'role': role, 'models': [{'id': item} for item in ids[:1000]],
                'message': '列表来自当前账号的模型接口，不代表所有模型都免费或都支持图像；请结合控制台说明选择。'}
    except httpx.TimeoutException as exc:
        raise engine.EngineError('读取模型列表超时，请检查网络或改用控制台中的模型 ID。') from exc
    except httpx.HTTPError as exc:
        raise engine.EngineError('无法读取模型列表，请检查 API 地址、网络及证书配置。') from exc


async def test_connection(settings, role):
    selected = select_role(settings, role)
    if not selected.get('model'):
        raise engine.EngineError('请先保存该角色的模型 ID；截图测试需要填写支持图片的视觉模型。')
    content = '这是一条 API 连通测试，请只回复 OK。'
    images = 0
    if role == 'vision':
        buffer = BytesIO()
        Image.new('RGB', (64, 64), 'white').save(buffer, format='PNG')
        content = [{'type': 'text', 'text': content},
                   {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode('ascii')}}]
        images = 1
    result = await engine._call(selected, [{'role': 'user', 'content': content}], model=selected['model'], max_tokens=64, images=images)
    if not result.strip():
        raise engine.EngineError('模型没有返回有效内容，请核对模型 ID。')
    # Never return the model's text: a compromised endpoint could echo a key.
    return {'ok': True, 'role': role, 'model': selected['model'],
            'message': '图片输入测试通过；实际截图的识别质量仍需核对。' if role == 'vision' else '真实 API 请求成功，模型已返回有效内容。'}
