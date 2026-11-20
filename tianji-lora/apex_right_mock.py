"""Loopback-only mock APEX server backed by a recorded holdout frame."""
from contextlib import asynccontextmanager
import json

from aiohttp import web
import cv2
import numpy as np


def fixture(work):
    source_frame = 557
    path = work / 'visual-audit/000/raw-1.png'
    quad = cv2.imread(str(path))
    if quad is None:
        raise RuntimeError(f'cannot read {path}')
    ok, jpeg = cv2.imencode('.jpg', quad)
    if not ok:
        raise RuntimeError('cannot encode fixture')
    with np.load(work / 'alignment/episode_000000.npz') as alignment:
        state = alignment['state'][source_frame]
    print(json.dumps({'fixture': str(path), 'source_episode': 0, 'source_frame': source_frame}), flush=True)
    return jpeg.tobytes(), {'joint_states': {'positions': [0.0] * 7 + state[:7].tolist()},
                            'gripper_right': {'position': float(state[7])}}


@asynccontextmanager
async def mock_server(work):
    jpeg, state = fixture(work)

    async def state_ws(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await ws.send_json(state)
        await ws.close()
        return ws

    async def stream(request):
        return web.Response(body=b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: ' + str(len(jpeg)).encode() + b'\r\n\r\n' + jpeg + b'\r\n--frame--\r\n',
                            headers={'Content-Type': 'multipart/x-mixed-replace; boundary=frame'})

    async def action_ws(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        async for message in ws:
            payload = json.loads(message.data)
            assert set(payload) == {'jointcmd_right', 'gripper_right'}
            assert len(payload['jointcmd_right']) == 7
            assert np.isfinite(payload['jointcmd_right']).all() and np.isfinite(payload['gripper_right'])
            await ws.send_json({'success': True, 'control_mode': 'joint'})
        return ws

    app = web.Application()
    app.router.add_get('/ws/state', state_ws)
    app.router.add_get('/stream/quad.mjpg', stream)
    app.router.add_get('/ws/action', action_ws)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    try:
        yield f'http://127.0.0.1:{port}'
    finally:
        await runner.cleanup()


async def send_mock_actions(session, base, actions):
    async with session.ws_connect(base + '/ws/action?ack=true') as ws:
        for action in actions:
            await ws.send_json({'jointcmd_right': action[:7].tolist(), 'gripper_right': float(action[7])})
            ack = await ws.receive_json()
            assert ack == {'success': True, 'control_mode': 'joint'}
    print(json.dumps({'mock_acked': len(actions)}), flush=True)
