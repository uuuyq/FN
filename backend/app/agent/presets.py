PRESETS = [
    dict(id='deepseek', label='DeepSeek', base_url='https://api.deepseek.com',
         models=['deepseek-flash', 'deepseek-v4-pro'], efforts=['none', 'low', 'high', 'max']),
    dict(id='kimi', label='Kimi', base_url='https://api.moonshot.cn/v1',
         models=['kimi-k2.5'], efforts=['none', 'high']),
    dict(id='qwen', label='阿里云百炼', base_url='https://dashscope.aliyuncs.com/compatible-mode/v1',
         models=['qwen3.5-plus'], efforts=['none', 'high']),
    dict(id='openai', label='OpenAI', base_url='https://api.openai.com/v1',
         models=['gpt-5.2'], efforts=['none', 'low', 'medium', 'high', 'xhigh']),
]


def infer_provider(config):
    for preset in PRESETS:
        if str(config.get('base_url', '')).rstrip('/') == preset['base_url'] and config.get('model') in preset['models']:
            return preset['id']
    return 'custom'
