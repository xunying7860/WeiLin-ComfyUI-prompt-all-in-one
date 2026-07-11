"""
系统提示词 - 用于 AI 扩写提示词
"""
SYSTEM_PROMPT = """Anima是一款利用深度学习的文生图模型，支持通过使用提示词来产生新的图像，描述要包含或省略的元素。
我在这里引入Anima算法中的Prompt概念。
下面的prompt是用来指导AI绘画模型创作图像的。它们包含了图像的各种细节，如具体的主体外观、身材（身高和三围）服装、姿势、表情、背景元素、光线、摄影角度、构图、色彩搭配和整体美学风格。这些prompt的格式为越靠前的prompt权重越高。
以下是用prompt帮助AI模型生成图像的例子：masterpiece, bestquality, highlydetailed, ultra-detailed, cold, solo, detailedeyes, longliverhair, expressionless, The composition features a solitary girl with a cold, expressionless demeanor, detailed golden eyes, and long flowing hair, adorned in long puffy sleeves, white wings, a shining halo, and heavy metal jewelry with a cross-laced chain on her footwear, surrounded by white doves.

仿照例子，给出一套详细描述以下内容的prompt。禁止输入其他任何额外内容，直接输出最终prompt："""

import sys
import os

# 修复个别电脑环境会报的错
Path = os.path.dirname(__file__)
sys.path.append(Path)
from get_lang import get_lang
from get_translate_apis import unprotected_translate_api_config


def gen_openai(messages, api_config):
    import openai
    from distutils.version import LooseVersion
    api_config = unprotected_translate_api_config('chatgpt_key', api_config)
    openai.api_base = api_config.get('api_base', 'https://api.openai.com/v1')
    openai.api_key = api_config.get('api_key', '')
    model = api_config.get('model', 'gpt-3.5-turbo')
    if not openai.api_key:
        raise Exception(get_lang('is_required', {'0': 'API Key'}))
    if not messages or len(messages) == 0:
        raise Exception(get_lang('is_required', {'0': 'messages'}))
    # 注入自定义系统提示词
    injected = False
    for i, msg in enumerate(messages):
        if msg.get('role') == 'system':
            messages[i]['content'] = SYSTEM_PROMPT
            injected = True
            break
    if not injected:
        messages.insert(0, {"role": "system", "content": SYSTEM_PROMPT})
    if LooseVersion(openai.__version__) < LooseVersion('1.0.0'):
        completion = openai.ChatCompletion.create(model=model, messages=messages, timeout=60)
    else:
        from openai import OpenAI
        client = OpenAI(
            base_url=openai.api_base,
            api_key=openai.api_key,
        )
        completion = client.chat.completions.create(model=model, messages=messages, timeout=60)
    if len(completion.choices) == 0:
        raise Exception(get_lang('no_response_from', {'0': 'OpenAI'}))
    content = completion.choices[0].message.content
    return content
