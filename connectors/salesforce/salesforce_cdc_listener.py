"""Salesforce Change Data Capture (CDC) listener for individual tenants."""

import asyncio
import contextlib
import io
import json
from typing import Any

import avro.io
import avro.schema
import grpc
from grpc import aio

from connectors.salesforce.salesforce_artifacts import (
    SALESFORCE_OBJECT_TYPES,
    SUPPORTED_SALESFORCE_OBJECTS,
)
from connectors.salesforce.salesforce_models import SalesforceCDCEvent
from src.clients.salesforce_factory import get_salesforce_client_for_tenant
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient
from src.clients.tenant_db import tenant_db_manager
from src.generated.pubsub.pubsub_api_pb2 import (
    FetchRequest,
    ReplayPreset,
    SchemaRequest,
    TopicRequest,
)
from src.generated.pubsub.pubsub_api_pb2_grpc import PubSubStub
from src.jobs.lanes import get_salesforce_cdc_lane
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Reconnection settings
INITIAL_RECONNECT_DELAY = 1.0  # seconds
MAX_RECONNECT_DELAY = 60.0  # seconds
RECONNECT_MULTIPLIER = 2.0


class SalesforceCDCListener:
    """Manages CDC connection for a single tenant."""

    def __init__(self, tenant_id: str, ssm_client: SSMClient, sqs_client: SQSClient):
        self.tenant_id = tenant_id
        self.ssm_client = ssm_client
        self.sqs_client = sqs_client
        self.running = False
        self.reconnect_delay = INITIAL_RECONNECT_DELAY
        self._shutdown_event = asyncio.Event()
        self._connection_task: asyncio.Task[None] | None = None
        self.schema_cache: dict[str, avro.schema.Schema] = {}

    async def start(self) -> None:
        """Start the CDC listener for this tenant."""
        if self.running:
            return

        logger.info(f"Starting Salesforce CDC listener for tenant {self.tenant_id}")
        self.running = True
        self._shutdown_event.clear()

        # Run the connection loop in the background
        self._connection_task = asyncio.create_task(self._connection_loop())

    async def stop(self) -> None:
        """Stop the CDC listener."""
        if not self.running:
            return

        logger.info(f"Stopping Salesforce CDC listener for tenant {self.tenant_id}")
        self.running = False
        self._shutdown_event.set()

        if self._connection_task:
            self._connection_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._connection_task

    async def _connection_loop(self) -> None:
        """Main connection loop with automatic reconnection."""
        while self.running:
            try:
                logger.info(f"Starting CDC connection for tenant {self.tenant_id}")
                await self._connect_and_listen()

                # If we exit normally (stream ended), log and determine if we should reconnect
                logger.info(f"CDC connection completed normally for tenant {self.tenant_id}")
                self.reconnect_delay = INITIAL_RECONNECT_DELAY

                # Check if shutdown was requested during connection
                if not self.running:
                    logger.info(  # type: ignore[unreachable]
                        f"Shutdown requested, stopping CDC connection loop for tenant {self.tenant_id}"
                    )
                    break

                # Stream ended naturally - wait a bit before reconnecting to avoid tight loop
                logger.info(
                    f"CDC stream ended, reconnecting in {INITIAL_RECONNECT_DELAY}s for tenant {self.tenant_id}"
                )
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(), timeout=INITIAL_RECONNECT_DELAY
                    )
                    # If shutdown event was set, exit
                    break
                except TimeoutError:
                    pass

            except Exception as e:
                if not self.running:
                    # Shutdown was requested
                    break  # type: ignore[unreachable]

                logger.error(f"CDC connection error for tenant {self.tenant_id}: {e}")

                # Wait before reconnecting with exponential backoff
                logger.info(f"Reconnecting in {self.reconnect_delay}s for tenant {self.tenant_id}")
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(), timeout=self.reconnect_delay
                    )
                    # If shutdown event was set, exit
                    break
                except TimeoutError:
                    pass

                # Increase reconnect delay with exponential backoff
                self.reconnect_delay = min(
                    self.reconnect_delay * RECONNECT_MULTIPLIER, MAX_RECONNECT_DELAY
                )

        logger.info(f"CDC connection loop ended for tenant {self.tenant_id}")

    async def _check_cdc_enabled_channels(
        self, stub: PubSubStub, auth_metadata: tuple[tuple[str, str], ...]
    ) -> list[SUPPORTED_SALESFORCE_OBJECTS]:
        """Check which CDC channels are enabled by calling GetTopic for each object type."""

        async def check_single_channel(
            obj_type: SUPPORTED_SALESFORCE_OBJECTS,
        ) -> SUPPORTED_SALESFORCE_OBJECTS | None:
            """Check if a single CDC channel is enabled."""
            channel_name = f"/data/{obj_type}ChangeEvent"
            try:
                topic_info = await stub.GetTopic(
                    TopicRequest(topic_name=channel_name), metadata=auth_metadata
                )

                if topic_info.can_subscribe:
                    return obj_type
                else:
                    logger.warning(
                        f"CDC not enabled for {obj_type} - no subscription permission (tenant {self.tenant_id})"
                    )
                    return None

            except grpc.aio.AioRpcError as e:
                if e.code() == grpc.StatusCode.NOT_FOUND:
                    # Expected: CDC is not enabled for this object type
                    logger.warning(
                        f"CDC not configured for {obj_type} in Salesforce org (tenant {self.tenant_id})"
                    )
                else:
                    # Unexpected error - could indicate connection, auth, or other issues
                    logger.error(
                        f"Unexpected error checking CDC for {obj_type} (tenant {self.tenant_id}): "
                        f"code={e.code()}, details={e.details()}"
                    )
                    raise
                return None
            except Exception:
                raise

        # Execute all checks concurrently
        tasks = [check_single_channel(obj_type) for obj_type in SALESFORCE_OBJECT_TYPES]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        enabled_channels: list[SUPPORTED_SALESFORCE_OBJECTS] = []
        for result in results:
            if isinstance(result, Exception):
                raise result
            elif isinstance(result, str):
                enabled_channels.append(result)

        logger.info(
            f"Found {len(enabled_channels)} CDC-enabled channels out of {len(SALESFORCE_OBJECT_TYPES)} "
            f"for tenant {self.tenant_id}: {enabled_channels}"
        )
        return enabled_channels

    async def _connect_and_listen(self) -> None:
        """Establish connection and start listening for CDC events."""
        # Get Salesforce credentials for this tenant
        salesforce_client = None
        try:
            async with tenant_db_manager.acquire_pool(self.tenant_id, readonly=True) as db_pool:
                salesforce_client = await get_salesforce_client_for_tenant(
                    self.tenant_id, self.ssm_client, db_pool
                )

            # Get OAuth credentials
            access_token = salesforce_client.access_token
            instance_url = salesforce_client.instance_url
            org_id = salesforce_client.org_id

            # Cleanup the Salesforce client now that we don't need it anymore
            await salesforce_client.close()
            salesforce_client = None

            logger.info(f"Connecting to Salesforce Pub/Sub API for tenant {self.tenant_id}")

            # Create secure gRPC channel
            credentials = grpc.ssl_channel_credentials()
            channel = aio.secure_channel("api.pubsub.salesforce.com:7443", credentials)

            try:
                # Create Pub/Sub stub
                stub = PubSubStub(channel)

                # Set up authentication metadata
                # https://developer.salesforce.com/docs/platform/pub-sub-api/guide/supported-auth.html
                auth_metadata = (
                    ("accesstoken", access_token),
                    ("instanceurl", instance_url),
                    # This is the Salesforce org ID, not Grapevine's tenant_id
                    ("tenantid", org_id),
                )

                logger.info(
                    f"CDC authentication configured for tenant {self.tenant_id} with org_id {org_id}"
                )

                # Check which CDC channels are enabled before subscribing
                # We'd hope users would enable CDC for all our supported objects, but we can't guarantee they did.
                enabled_channels = await self._check_cdc_enabled_channels(stub, auth_metadata)

                if not enabled_channels:
                    logger.warning(f"No CDC-enabled channels found for tenant {self.tenant_id}.")
                    return

                # Subscribe to only the enabled CDC channels concurrently
                subscription_tasks = []
                for obj_type in enabled_channels:
                    task = asyncio.create_task(
                        self._subscribe_to_channel(
                            stub, f"/data/{obj_type}ChangeEvent", obj_type, auth_metadata
                        )
                    )
                    subscription_tasks.append(task)

                if subscription_tasks:
                    logger.info(
                        f"Started {len(subscription_tasks)} CDC subscriptions for tenant {self.tenant_id}"
                    )
                    # Wait for any subscription to complete (which indicates connection issue or shutdown)
                    done, pending = await asyncio.wait(
                        subscription_tasks, return_when=asyncio.FIRST_COMPLETED
                    )

                    # Cancel any remaining subscriptions
                    for task in pending:
                        task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await task

                    # Check if any completed task had an exception
                    for task in done:
                        try:
                            await task  # This will raise if the task had an exception
                        except Exception:
                            # Exception will be re-raised and handled by outer try/except
                            raise

            finally:
                await channel.close()

        except Exception as e:
            logger.error(f"Error in CDC connection for tenant {self.tenant_id}: {e}")
            raise

    async def _subscribe_to_channel(
        self,
        stub: PubSubStub,
        channel_name: str,
        object_type: SUPPORTED_SALESFORCE_OBJECTS,
        auth_metadata: tuple[tuple[str, str], ...],
    ) -> None:
        """Subscribe to a specific CDC channel and process events."""
        logger.info(f"Subscribing to {channel_name} for tenant {self.tenant_id}")

        def get_fetch_request() -> FetchRequest:
            return FetchRequest(
                topic_name=channel_name,
                # Technically you're supposed to store replay IDs and reuse them after e.g. disconnections / pod restarts,
                # but in practice we have good enough coverage during deploys + we're ok with losing a tiny # of events, so
                # for now we simply use LATEST.
                replay_preset=ReplayPreset.LATEST,
                num_requested=100,
            )

        try:
            # Create request queue for synchronized request/response flow
            request_queue: asyncio.Queue[FetchRequest] = asyncio.Queue(maxsize=1)

            async def request_generator():
                """Generate fetch requests synchronized with response processing."""
                while self.running:
                    try:
                        # Block until request available (with timeout for safety)
                        request = await asyncio.wait_for(request_queue.get(), timeout=90.0)
                        yield request
                        request_queue.task_done()
                    except TimeoutError:
                        # Safety: yield keepalive if queue blocked too long
                        logger.info(
                            f"Request queue timeout for {channel_name}, sending keepalive request"
                        )
                        yield get_fetch_request()

            # Queue initial request to establish subscription
            await request_queue.put(get_fetch_request())

            # Create persistent stream with synchronized request generator
            response_stream = stub.Subscribe(
                request_generator(),
                metadata=auth_metadata,
            )

            # Handler to process events streamed from Salesforce
            async def process_event(consumer_event):
                try:
                    # Decode Avro payload
                    cdc_events = await self._decode_avro_event(
                        consumer_event, object_type, stub, auth_metadata
                    )
                    if cdc_events:
                        await self._send_event(cdc_events)
                except Exception as e:
                    logger.error(f"Error processing CDC event from {channel_name}: {e}")

            # Process responses from the persistent stream
            async for response in response_stream:
                if not self.running:
                    logger.info(
                        f"Shutdown requested, stopping subscription to {channel_name} for tenant {self.tenant_id}"
                    )
                    break

                # Queue next request immediately after receiving response (before processing)
                if self.running:
                    try:
                        request_queue.put_nowait(get_fetch_request())
                    except asyncio.QueueFull:
                        # Queue already has pending request, which is fine - natural backpressure
                        logger.info(f"Request queue already full for {channel_name}")

                logger.info(
                    f"Received {len(response.events)} events from {channel_name} for tenant {self.tenant_id}"
                )

                # Process all events in parallel
                if response.events:
                    await asyncio.gather(
                        *[process_event(event) for event in response.events], return_exceptions=True
                    )

            logger.info(f"Subscription to {channel_name} ended for tenant {self.tenant_id}")

        except Exception as e:
            logger.error(f"Error subscribing to {channel_name} (tenant {self.tenant_id}): {e}")
            raise

    async def _get_or_fetch_schema(
        self, stub: PubSubStub, schema_id: str, auth_metadata: tuple[tuple[str, str], ...]
    ) -> avro.schema.Schema:
        """Get schema from cache or fetch from Salesforce."""
        # Check cache first
        if schema_id in self.schema_cache:
            return self.schema_cache[schema_id]

        # Fetch schema using GetSchema RPC call
        schema_request = SchemaRequest(schema_id=schema_id)
        schema_response = await stub.GetSchema(schema_request, metadata=auth_metadata)

        if schema_response.schema_json:
            # Cache the schema for future use
            schema = avro.schema.parse(schema_response.schema_json)
            self.schema_cache[schema_id] = schema
            logger.info(f"Fetched and cached schema {schema_id} for tenant {self.tenant_id}")
            return schema
        else:
            raise ValueError(f"Empty schema returned for schema_id {schema_id}: {schema_response}")

    async def _decode_avro_event(
        self,
        consumer_event: Any,
        object_type: SUPPORTED_SALESFORCE_OBJECTS,
        stub: PubSubStub,
        auth_metadata: tuple[tuple[str, str], ...],
    ) -> list[SalesforceCDCEvent] | None:
        """Decode Avro-encoded CDC event."""
        try:
            # The event payload is Avro-encoded binary data
            producer_event = consumer_event.event
            avro_payload = producer_event.payload
            schema_id = producer_event.schema_id

            # Get the Avro schema for this event
            avro_schema = await self._get_or_fetch_schema(stub, schema_id, auth_metadata)

            # Decode the Avro payload
            try:
                bytes_reader = io.BytesIO(avro_payload)
                decoder = avro.io.BinaryDecoder(bytes_reader)
                reader = avro.io.DatumReader(avro_schema)
                # Example event data:
                # (see details at https://resources.docs.salesforce.com/latest/latest/en-us/sfdc/pdf/salesforce_change_data_capture.pdf)
                # {
                #     "ChangeEventHeader": {
                #         "entityName": "Account",
                #         "recordIds": ["001gK00000KhBLVQA3"],
                #         "changeType": "UPDATE",
                #         "changeOrigin": "com/salesforce/api/soap/64.0;client=devconsole",
                #         "transactionKey": "0000792d-fa4e-211a-4b43-bb53f063973f",
                #         "sequenceNumber": 1,
                #         "commitTimestamp": 1758153866000,
                #         "commitNumber": 1758153866121183235,
                #         "commitUser": "005gK000007b6QbQAI",
                #         "nulledFields": [],
                #         "diffFields": [],
                #         "changedFields": ["0x400002"]
                #     },
                #     "Name": "Updated Name",
                #     ...
                # }
                event_data = reader.read(decoder)
            except Exception as e:
                logger.error(f"Error decoding Avro payload for {object_type}: {e}")
                raise

            # Extract CDC event details
            change_header = event_data.get("ChangeEventHeader", {})
            operation_type = change_header.get("changeType", "UPDATE")

            # Get record IDs. In practice, CDC events almost always only have one record ID
            record_ids = change_header.get("recordIds", [])
            if not record_ids:
                logger.warning(f"No record IDs found in CDC event for {object_type}")
                return None

            return [
                SalesforceCDCEvent(
                    record_id=record_id,
                    object_type=object_type,
                    change_event_header=change_header,
                    operation_type=operation_type,
                    record_data=event_data,
                )
                for record_id in record_ids
            ]

        except Exception as e:
            logger.error(f"Error decoding Avro event for {object_type}: {e}")
            return None

    async def _send_event(self, events: list[SalesforceCDCEvent]) -> None:
        """Send a CDC event to SQS."""
        try:
            # Create the webhook body in the format expected by SalesforceCDCWebhookBody
            cdc_body = {"events": [event.model_dump() for event in events]}

            # IMPORTANT: Generate a consistent message dedupe ID AND message group ID for this event batch.
            # This is necessary for SQS because:
            #   - we expect to have duplicates, given ALL gatekeeper pods currently listen to ALL CDC channels (for simplicity / safety during deploys).
            #   - we use HT-FIFO queues, which dedupe per message group ID.
            # We use only the first event in the batch given the 128 char limit for deduplication IDs.
            # See AIVP-569 for more details.
            batch_identifier = f"{events[0].object_type}_{events[0].record_id}_{events[0].change_event_header.get('commitNumber')}"
            message_group_id = get_salesforce_cdc_lane(self.tenant_id, batch_identifier)
            message_deduplication_id = f"sf_cdc_{self.tenant_id}_{batch_identifier}"

            # Send to ingest queue
            await self.sqs_client.send_ingest_webhook_message(
                webhook_body=json.dumps(cdc_body),
                webhook_headers={},
                tenant_id=self.tenant_id,
                source_type="salesforce",
                message_group_id=message_group_id,
                message_deduplication_id=message_deduplication_id,
            )
            logger.info(
                f"Sent CDC event batch for tenant {self.tenant_id} to lane {message_group_id} with dedupe ID {message_deduplication_id}"
            )

        except Exception as e:
            logger.error(f"Error sending CDC event batch for tenant {self.tenant_id}: {e}")
            raise
