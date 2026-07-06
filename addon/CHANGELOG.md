# Changelog

## 0.1.7

- Reconnect immediately on connection loss instead of always waiting out the backoff
  delay. A one-off drop now recovers as fast as a fresh WebSocket handshake instead of
  stalling for 5+ seconds.
- Commands that were in flight when the command WebSocket died are now retried after
  reconnecting instead of being silently dropped.

## 0.1.6

- Both the status and command WebSocket connections now reconnect automatically with
  exponential backoff (up to 60s) if the connection to Larnitech drops. Previously a
  dropped connection silently stopped status updates and/or commands until the add-on
  was restarted manually.

## 0.1.5

- Split the Larnitech API2 connection into a dedicated status WebSocket (get-devices,
  status-subscribe, live events) and a dedicated command WebSocket (status-set), to
  avoid concurrent `recv()` calls on one connection.

## 0.1.3

- Use address-only MQTT object IDs so renaming items in Larnitech no longer creates
  duplicate Home Assistant entities.

## 0.1.0

- Initial MVP: connect to Larnitech API2, publish MQTT Discovery entities, forward
  commands from Home Assistant back to Larnitech.
