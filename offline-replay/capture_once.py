#!/usr/bin/env python3
"""Capture two Argus views and one bounded SDK observation; default is plan only."""
import argparse
import concurrent.futures
import datetime
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASK = "Pick up the orange on the table."

def camera_stream_class():
    sys.path.insert(0, "/home/nvidia/wsb_ws/resources/camera_projects/argus_isp")
    import cv2
    from argus_show import Gst, SENSOR_IDS, decode_sample, pipeline_text

    Gst.init(None)

    class Stream:
        def __init__(self, channel):
            self.pipeline = Gst.parse_launch(pipeline_text(SENSOR_IDS[channel]))
            self.source = self.pipeline.get_by_name("argus_source")
            self.sink = self.pipeline.get_by_name("preview_sink")

        def start(self):
            if self.pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
                raise RuntimeError("Argus pipeline failed to start")
            result, state, _ = self.pipeline.get_state(10 * Gst.SECOND)
            if result == Gst.StateChangeReturn.FAILURE or state != Gst.State.PLAYING:
                raise RuntimeError("Argus pipeline did not reach PLAYING")
            self.playing_observed = time.monotonic()

        def settle(self):
            time.sleep(max(0, self.playing_observed + 5 - time.monotonic()))
            self.source.set_property("aelock", True)
            self.source.set_property("awblock", True)
            # Allow a new frame after the lock request; the one-buffer sink drops old frames.
            time.sleep(0.2)
            self.frame()

        def frame(self):
            sample = self.sink.emit("try-pull-sample", 3 * Gst.SECOND)
            observed = time.monotonic()
            if sample is None:
                raise TimeoutError("Argus frame timeout or pipeline error")
            return cv2.cvtColor(decode_sample(sample), cv2.COLOR_BGR2RGB), observed

        def stop(self):
            result = self.pipeline.set_state(Gst.State.NULL)
            state_result, state, _ = self.pipeline.get_state(5 * Gst.SECOND)
            if result == Gst.StateChangeReturn.FAILURE or state_result == Gst.StateChangeReturn.FAILURE or state != Gst.State.NULL:
                raise RuntimeError("Argus pipeline stop unconfirmed")

    return Stream


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({"mode": "plan_only", "device_calls": 0, "task": TASK,
                          "cameras": ["head_left", "right_wrist"],
                          "requires": "--execute --out NEW_DIRECTORY"}, indent=2))
        return
    if args.out is None:
        parser.error("--out is required with --execute")
    args.out.mkdir(parents=True, exist_ok=False)
    Stream = camera_stream_class()

    report = {"schema": "pi05_single_observation_v1", "task": TASK,
              "task_zh": "抓取桌面上的橙子", "source_time_synchronized": False,
              "images": {}, "camera_stopped": {}, "state_helper_returncode": None}
    streams = []
    process = None
    try:
        for name, channel in (("head_left", 0), ("right_wrist", 3)):
            stream = Stream(channel)
            streams.append((name, stream))
            stream.start()
        # Let both pipelines deliver frames before the short SDK session.
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            warm = [pool.submit(stream.settle) for _, stream in streams]
            for item in warm:
                item.result()
            with (args.out / "state.stdout").open("w") as stdout, (args.out / "state.stderr").open("w") as stderr:
                process = subprocess.Popen([str(HERE / "capture_state"), "--execute", str(args.out / "state.json")],
                                           stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr,
                                           text=True, bufsize=1)
                for line in process.stdout:
                    stdout.write(line)
                    if line.strip() == "PI05_READY":
                        break
                else:
                    raise RuntimeError("state helper exited before SDK was ready")
                def take(stream):
                    before_mono, before_unix = time.monotonic(), time.time()
                    image, observed = stream.frame()
                    return image, {"before_monotonic": before_mono, "observed_monotonic": observed,
                                   "after_monotonic": time.monotonic(), "before_unix": before_unix,
                                   "after_unix": time.time()}
                pending = [(name, pool.submit(take, stream)) for name, stream in streams]
                process.stdin.write("\n")
                process.stdin.flush()
                for name, future in pending:
                    image, timing = future.result()
                    height, width = image.shape[:2]
                    with (args.out / (name + ".ppm")).open("wb") as f:
                        f.write(f"P6\n{width} {height}\n255\n".encode())
                        f.write(image.tobytes())
                    report["images"][name] = {"file": name + ".ppm", "width": width, "height": height,
                                              "color": "RGB8", "pipeline": "argus_show: Argus NV12 to BGRx to BGR to RGB; AE/AWB lock requested after 5s",
                                              "orientation": "flip-method=2 (180 degrees); physical orientation unverified",
                                              "timestamp_semantics": "host monotonic time after pulling latest buffered frame; not sensor exposure time",
                                              "color_correctness_verified": False, **timing}
                remaining, _ = process.communicate()
                stdout.write(remaining)
                report["state_helper_returncode"] = process.returncode
                if (args.out / "state.json").exists():
                    state = json.loads((args.out / "state.json").read_text())
                    times = [v["observed_monotonic"] for v in report["images"].values()]
                    if "joint" in state:
                        times.extend([state["joint"]["before_monotonic"], state["joint"]["after_monotonic"]])
                    response = state.get("gripper", {}).get("response")
                    if response:
                        times.extend([response["before_monotonic"], response["after_monotonic"]])
                    if times:
                        report["host_observation_span_seconds"] = max(times) - min(times)
    except Exception as exc:
        report["error"] = str(exc)
    finally:
        if process is not None and process.poll() is None:
            if process.stdin:
                process.stdin.close()
            report["state_helper_returncode"] = process.wait()
        for name, stream in streams:
            try:
                stream.stop()
                report["camera_stopped"][name] = True
            except Exception as exc:
                report["camera_stopped"][name] = str(exc)
        report["finished_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        (args.out / "capture.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    if "error" in report or report["state_helper_returncode"] != 0:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
