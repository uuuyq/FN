"""Process-local turn snapshots and bounded subscriber queues."""
import asyncio
import copy


class TurnStream:
    def __init__(self, turn_id):
        self.turn_id = turn_id
        self.sequence = 0
        self.messages = {}
        self.subscribers = set()

    def publish(self, kind, message_id, text=''):
        self.sequence += 1
        if kind == 'message_start':
            self.messages[message_id] = {'message_id': message_id, 'text': '', 'ended': False}
        elif kind == 'text_delta':
            self.messages[message_id]['text'] += text
        elif kind == 'message_end':
            self.messages[message_id]['ended'] = True
        payload = {'turn_id': self.turn_id, 'sequence': self.sequence,
                   'message_id': message_id, 'text': text}
        for queue in tuple(self.subscribers):
            if queue.full():
                self.subscribers.remove(queue)
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait(None)
            else:
                queue.put_nowait((kind, payload))

    def subscribe(self):
        queue = asyncio.Queue(maxsize=256)
        self.subscribers.add(queue)
        snapshot = {'turn_id': self.turn_id, 'sequence': self.sequence,
                    'messages': copy.deepcopy(list(self.messages.values()))}
        return queue, snapshot
