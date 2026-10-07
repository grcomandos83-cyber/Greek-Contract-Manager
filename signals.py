import logging

class SignalManager:
    _subscribers = {}
    _logger = logging.getLogger("SignalManager")

    @classmethod
    def subscribe(cls, event_type, callback):
        if event_type not in cls._subscribers:
            cls._subscribers[event_type] = []
        cls._subscribers[event_type].append(callback)
        cls._logger.debug(f"Subscribed to {event_type}: {callback}")

    @classmethod
    def unsubscribe(cls, event_type, callback):
        if event_type in cls._subscribers:
            try:
                cls._subscribers[event_type].remove(callback)
                cls._logger.debug(f"Unsubscribed from {event_type}: {callback}")
            except ValueError:
                pass

    @classmethod
    def emit(cls, event_type, data=None):
        cls._logger.debug(f"Emitting {event_type} with data: {data}")
        if event_type in cls._subscribers:
            for callback in cls._subscribers[event_type]:
                try:
                    callback(data)
                except Exception as e:
                    cls._logger.error(f"Error in signal callback for {event_type}: {e}")

# Event Constants
class Signals:
    CONTRACT_UPSERTED = "contract_upserted" # Added or Updated
    CONTRACT_DELETED = "contract_deleted"
    CATEGORIES_UPDATED = "categories_updated"
    REFRESH_REQUESTED = "refresh_requested"
