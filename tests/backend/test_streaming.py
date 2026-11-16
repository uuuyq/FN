import asyncio

from app.agent.streaming import TurnStream


def test_snapshot_subscription_and_slow_consumer():
    channel = TurnStream('turn')
    channel.publish('message_start', 'message')
    channel.publish('text_delta', 'message', 'first')
    queue, snapshot = channel.subscribe()
    channel.publish('text_delta', 'message', 'next')
    assert snapshot['messages'][0]['text'] == 'first'
    assert queue.get_nowait()[1]['sequence'] == snapshot['sequence'] + 1
    assert channel.messages['message']['text'] == 'firstnext'
    for _ in range(257):
        channel.publish('text_delta', 'message', '.')
    assert queue not in channel.subscribers
    assert queue.get_nowait() is None
