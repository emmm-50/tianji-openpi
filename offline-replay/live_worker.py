#!/usr/bin/env python3
"""Persistent WebSocket client; length-prefixed NPZ messages on stdio."""
import io
import json
import struct
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'openpi/packages/openpi-client/src'))
from openpi_client import msgpack_numpy
from websockets.sync.client import connect


def read_exact(stream, n):
    parts = []
    while n:
        b = stream.read(n)
        if not b:
            raise EOFError('incomplete worker message')
        parts.append(b)
        n -= len(b)
    return b''.join(parts)


def send(payload):
    sys.stdout.buffer.write(struct.pack('!Q', len(payload)) + payload)
    sys.stdout.buffer.flush()


def main():
    packer = msgpack_numpy.Packer()
    with connect('ws://127.0.0.1:8000', compression=None, max_size=None,
                 open_timeout=5, close_timeout=2) as connection:
        msgpack_numpy.unpackb(connection.recv(timeout=5))
        send(b'READY')
        while True:
            header = sys.stdin.buffer.read(8)
            if not header:
                break
            if len(header) != 8:
                raise EOFError('incomplete worker header')
            payload = read_exact(sys.stdin.buffer, struct.unpack('!Q', header)[0])
            with np.load(io.BytesIO(payload), allow_pickle=False) as data:
                obs = {'observation/exterior_image_1_left': data['exterior'],
                       'observation/wrist_image_left': data['wrist'],
                       'observation/joint_position': data['joints'],
                       'observation/gripper_position': data['gripper'],
                       'prompt': str(data['prompt'].item())}
            connection.send(packer.pack(obs))
            reply = connection.recv(timeout=15)
            if isinstance(reply, str):
                raise RuntimeError(reply)
            result = msgpack_numpy.unpackb(reply)
            output = io.BytesIO()
            np.savez(output, actions=result['actions'], timing=np.asarray(json.dumps(result.get('server_timing'))))
            send(output.getvalue())



if __name__ == '__main__':
    main()
