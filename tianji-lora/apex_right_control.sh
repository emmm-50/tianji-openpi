#!/usr/bin/env bash
set -e

usage() {
  cat <<'HELP'
Usage: bash tianji-lora/apex_right_control.sh COMMAND
  status   Read mux and Robot state
  prepare  Set mux to 0 and read Robot state
  ready    Request Ready after prepare (mux 0; Robot state [-1, -1]); read state
  position Set mux to 0, then Position; confirm [1, 1]
  vla      Set mux to 3 and confirm
  release  Set mux to 0 and confirm
  idle     Set mux to 0, then Robot Idle; read state
HELP
}

if [ "$#" -eq 0 ] || { [ "$#" -eq 1 ] && { [ "$1" = help ] || [ "$1" = --help ] || [ "$1" = -h ]; }; }; then
  usage
  exit 0
fi
if [ "$#" -ne 1 ]; then
  usage >&2
  exit 2
fi
case "$1" in
  status|prepare|ready|position|vla|release|idle) ;;
  *) usage >&2; exit 2 ;;
esac

source /etc/apex/apex_ros_env.sh

call_service() {
  local response
  response=$(ros2 service call "$@")
  printf '%s\n' "$response"
  if ! printf '%s\n' "$response" | grep -Eq 'success[=:][[:space:]]*(True|true)([^[:alnum:]_]|$)'; then
    echo 'Service did not report success=True' >&2
    return 1
  fi
}

mux_read() {
  timeout 8s ros2 topic echo --once --qos-reliability reliable \
    --qos-durability transient_local /tj/control/input_mode std_msgs/msg/Int32 "$@"
}
robot_read() {
  timeout 8s ros2 topic echo --once --qos-reliability best_effort \
    /tj/info/robot_state std_msgs/msg/Int16MultiArray "$@"
}
mux_set() {
  call_service /tj/control/set_input marvin_msgs/srv/Int "{data: $1}"
  mux_read --filter "m.data == $1"
}

case "$1" in
  status) mux_read; robot_read ;;
  prepare) mux_set 0; robot_read ;;
  ready) call_service /tj/control/set_ready std_srvs/srv/Trigger '{}'; robot_read ;;
  position) mux_set 0; call_service /tj/control/set_mode marvin_msgs/srv/Int '{data: 1}'; robot_read --filter 'list(m.data) == [1, 1]' ;;
  vla) mux_set 3 ;;
  release) mux_set 0 ;;
  idle) mux_set 0; call_service /tj/control/set_mode marvin_msgs/srv/Int '{data: 0}'; robot_read ;;
esac
