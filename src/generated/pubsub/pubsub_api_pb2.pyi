from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ErrorCode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    UNKNOWN: _ClassVar[ErrorCode]
    PUBLISH: _ClassVar[ErrorCode]
    COMMIT: _ClassVar[ErrorCode]

class ReplayPreset(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    LATEST: _ClassVar[ReplayPreset]
    EARLIEST: _ClassVar[ReplayPreset]
    CUSTOM: _ClassVar[ReplayPreset]
UNKNOWN: ErrorCode
PUBLISH: ErrorCode
COMMIT: ErrorCode
LATEST: ReplayPreset
EARLIEST: ReplayPreset
CUSTOM: ReplayPreset

class TopicInfo(_message.Message):
    __slots__ = ("topic_name", "tenant_guid", "can_publish", "can_subscribe", "schema_id", "rpc_id")
    TOPIC_NAME_FIELD_NUMBER: _ClassVar[int]
    TENANT_GUID_FIELD_NUMBER: _ClassVar[int]
    CAN_PUBLISH_FIELD_NUMBER: _ClassVar[int]
    CAN_SUBSCRIBE_FIELD_NUMBER: _ClassVar[int]
    SCHEMA_ID_FIELD_NUMBER: _ClassVar[int]
    RPC_ID_FIELD_NUMBER: _ClassVar[int]
    topic_name: str
    tenant_guid: str
    can_publish: bool
    can_subscribe: bool
    schema_id: str
    rpc_id: str
    def __init__(self, topic_name: _Optional[str] = ..., tenant_guid: _Optional[str] = ..., can_publish: bool = ..., can_subscribe: bool = ..., schema_id: _Optional[str] = ..., rpc_id: _Optional[str] = ...) -> None: ...

class TopicRequest(_message.Message):
    __slots__ = ("topic_name",)
    TOPIC_NAME_FIELD_NUMBER: _ClassVar[int]
    topic_name: str
    def __init__(self, topic_name: _Optional[str] = ...) -> None: ...

class EventHeader(_message.Message):
    __slots__ = ("key", "value")
    KEY_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    key: str
    value: bytes
    def __init__(self, key: _Optional[str] = ..., value: _Optional[bytes] = ...) -> None: ...

class ProducerEvent(_message.Message):
    __slots__ = ("id", "schema_id", "payload", "headers")
    ID_FIELD_NUMBER: _ClassVar[int]
    SCHEMA_ID_FIELD_NUMBER: _ClassVar[int]
    PAYLOAD_FIELD_NUMBER: _ClassVar[int]
    HEADERS_FIELD_NUMBER: _ClassVar[int]
    id: str
    schema_id: str
    payload: bytes
    headers: _containers.RepeatedCompositeFieldContainer[EventHeader]
    def __init__(self, id: _Optional[str] = ..., schema_id: _Optional[str] = ..., payload: _Optional[bytes] = ..., headers: _Optional[_Iterable[_Union[EventHeader, _Mapping]]] = ...) -> None: ...

class ConsumerEvent(_message.Message):
    __slots__ = ("event", "replay_id")
    EVENT_FIELD_NUMBER: _ClassVar[int]
    REPLAY_ID_FIELD_NUMBER: _ClassVar[int]
    event: ProducerEvent
    replay_id: bytes
    def __init__(self, event: _Optional[_Union[ProducerEvent, _Mapping]] = ..., replay_id: _Optional[bytes] = ...) -> None: ...

class PublishResult(_message.Message):
    __slots__ = ("replay_id", "error", "correlation_key")
    REPLAY_ID_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    CORRELATION_KEY_FIELD_NUMBER: _ClassVar[int]
    replay_id: bytes
    error: Error
    correlation_key: str
    def __init__(self, replay_id: _Optional[bytes] = ..., error: _Optional[_Union[Error, _Mapping]] = ..., correlation_key: _Optional[str] = ...) -> None: ...

class Error(_message.Message):
    __slots__ = ("code", "msg")
    CODE_FIELD_NUMBER: _ClassVar[int]
    MSG_FIELD_NUMBER: _ClassVar[int]
    code: ErrorCode
    msg: str
    def __init__(self, code: _Optional[_Union[ErrorCode, str]] = ..., msg: _Optional[str] = ...) -> None: ...

class FetchRequest(_message.Message):
    __slots__ = ("topic_name", "replay_preset", "replay_id", "num_requested", "auth_refresh")
    TOPIC_NAME_FIELD_NUMBER: _ClassVar[int]
    REPLAY_PRESET_FIELD_NUMBER: _ClassVar[int]
    REPLAY_ID_FIELD_NUMBER: _ClassVar[int]
    NUM_REQUESTED_FIELD_NUMBER: _ClassVar[int]
    AUTH_REFRESH_FIELD_NUMBER: _ClassVar[int]
    topic_name: str
    replay_preset: ReplayPreset
    replay_id: bytes
    num_requested: int
    auth_refresh: str
    def __init__(self, topic_name: _Optional[str] = ..., replay_preset: _Optional[_Union[ReplayPreset, str]] = ..., replay_id: _Optional[bytes] = ..., num_requested: _Optional[int] = ..., auth_refresh: _Optional[str] = ...) -> None: ...

class FetchResponse(_message.Message):
    __slots__ = ("events", "latest_replay_id", "rpc_id", "pending_num_requested")
    EVENTS_FIELD_NUMBER: _ClassVar[int]
    LATEST_REPLAY_ID_FIELD_NUMBER: _ClassVar[int]
    RPC_ID_FIELD_NUMBER: _ClassVar[int]
    PENDING_NUM_REQUESTED_FIELD_NUMBER: _ClassVar[int]
    events: _containers.RepeatedCompositeFieldContainer[ConsumerEvent]
    latest_replay_id: bytes
    rpc_id: str
    pending_num_requested: int
    def __init__(self, events: _Optional[_Iterable[_Union[ConsumerEvent, _Mapping]]] = ..., latest_replay_id: _Optional[bytes] = ..., rpc_id: _Optional[str] = ..., pending_num_requested: _Optional[int] = ...) -> None: ...

class SchemaRequest(_message.Message):
    __slots__ = ("schema_id",)
    SCHEMA_ID_FIELD_NUMBER: _ClassVar[int]
    schema_id: str
    def __init__(self, schema_id: _Optional[str] = ...) -> None: ...

class SchemaInfo(_message.Message):
    __slots__ = ("schema_json", "schema_id", "rpc_id")
    SCHEMA_JSON_FIELD_NUMBER: _ClassVar[int]
    SCHEMA_ID_FIELD_NUMBER: _ClassVar[int]
    RPC_ID_FIELD_NUMBER: _ClassVar[int]
    schema_json: str
    schema_id: str
    rpc_id: str
    def __init__(self, schema_json: _Optional[str] = ..., schema_id: _Optional[str] = ..., rpc_id: _Optional[str] = ...) -> None: ...

class PublishRequest(_message.Message):
    __slots__ = ("topic_name", "events", "auth_refresh")
    TOPIC_NAME_FIELD_NUMBER: _ClassVar[int]
    EVENTS_FIELD_NUMBER: _ClassVar[int]
    AUTH_REFRESH_FIELD_NUMBER: _ClassVar[int]
    topic_name: str
    events: _containers.RepeatedCompositeFieldContainer[ProducerEvent]
    auth_refresh: str
    def __init__(self, topic_name: _Optional[str] = ..., events: _Optional[_Iterable[_Union[ProducerEvent, _Mapping]]] = ..., auth_refresh: _Optional[str] = ...) -> None: ...

class PublishResponse(_message.Message):
    __slots__ = ("results", "schema_id", "rpc_id")
    RESULTS_FIELD_NUMBER: _ClassVar[int]
    SCHEMA_ID_FIELD_NUMBER: _ClassVar[int]
    RPC_ID_FIELD_NUMBER: _ClassVar[int]
    results: _containers.RepeatedCompositeFieldContainer[PublishResult]
    schema_id: str
    rpc_id: str
    def __init__(self, results: _Optional[_Iterable[_Union[PublishResult, _Mapping]]] = ..., schema_id: _Optional[str] = ..., rpc_id: _Optional[str] = ...) -> None: ...

class ManagedFetchRequest(_message.Message):
    __slots__ = ("subscription_id", "developer_name", "num_requested", "auth_refresh", "commit_replay_id_request")
    SUBSCRIPTION_ID_FIELD_NUMBER: _ClassVar[int]
    DEVELOPER_NAME_FIELD_NUMBER: _ClassVar[int]
    NUM_REQUESTED_FIELD_NUMBER: _ClassVar[int]
    AUTH_REFRESH_FIELD_NUMBER: _ClassVar[int]
    COMMIT_REPLAY_ID_REQUEST_FIELD_NUMBER: _ClassVar[int]
    subscription_id: str
    developer_name: str
    num_requested: int
    auth_refresh: str
    commit_replay_id_request: CommitReplayRequest
    def __init__(self, subscription_id: _Optional[str] = ..., developer_name: _Optional[str] = ..., num_requested: _Optional[int] = ..., auth_refresh: _Optional[str] = ..., commit_replay_id_request: _Optional[_Union[CommitReplayRequest, _Mapping]] = ...) -> None: ...

class ManagedFetchResponse(_message.Message):
    __slots__ = ("events", "latest_replay_id", "rpc_id", "pending_num_requested", "commit_response")
    EVENTS_FIELD_NUMBER: _ClassVar[int]
    LATEST_REPLAY_ID_FIELD_NUMBER: _ClassVar[int]
    RPC_ID_FIELD_NUMBER: _ClassVar[int]
    PENDING_NUM_REQUESTED_FIELD_NUMBER: _ClassVar[int]
    COMMIT_RESPONSE_FIELD_NUMBER: _ClassVar[int]
    events: _containers.RepeatedCompositeFieldContainer[ConsumerEvent]
    latest_replay_id: bytes
    rpc_id: str
    pending_num_requested: int
    commit_response: CommitReplayResponse
    def __init__(self, events: _Optional[_Iterable[_Union[ConsumerEvent, _Mapping]]] = ..., latest_replay_id: _Optional[bytes] = ..., rpc_id: _Optional[str] = ..., pending_num_requested: _Optional[int] = ..., commit_response: _Optional[_Union[CommitReplayResponse, _Mapping]] = ...) -> None: ...

class CommitReplayRequest(_message.Message):
    __slots__ = ("commit_request_id", "replay_id")
    COMMIT_REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    REPLAY_ID_FIELD_NUMBER: _ClassVar[int]
    commit_request_id: str
    replay_id: bytes
    def __init__(self, commit_request_id: _Optional[str] = ..., replay_id: _Optional[bytes] = ...) -> None: ...

class CommitReplayResponse(_message.Message):
    __slots__ = ("commit_request_id", "replay_id", "error", "process_time")
    COMMIT_REQUEST_ID_FIELD_NUMBER: _ClassVar[int]
    REPLAY_ID_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    PROCESS_TIME_FIELD_NUMBER: _ClassVar[int]
    commit_request_id: str
    replay_id: bytes
    error: Error
    process_time: int
    def __init__(self, commit_request_id: _Optional[str] = ..., replay_id: _Optional[bytes] = ..., error: _Optional[_Union[Error, _Mapping]] = ..., process_time: _Optional[int] = ...) -> None: ...
