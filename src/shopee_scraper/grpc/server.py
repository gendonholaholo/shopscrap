"""gRPC server implementation."""

from __future__ import annotations

import asyncio
import signal
from concurrent import futures

import grpc

from shopee_scraper.utils.logging import get_logger, setup_logging


logger = get_logger(__name__)

# Default server configuration
DEFAULT_PORT = 50051
MAX_WORKERS = 10


async def serve(
    port: int = DEFAULT_PORT,
    max_workers: int = MAX_WORKERS,
) -> None:
    """
    Start the gRPC server.

    Args:
        port: Port to listen on
        max_workers: Maximum number of worker threads
    """
    setup_logging()

    # Import generated protobuf modules
    try:
        from shopee_scraper.grpc import shopee_pb2_grpc
    except ImportError as e:
        logger.error(
            "Proto files not compiled. Run: "
            "python -m grpc_tools.protoc -I./protos "
            "--python_out=./src/shopee_scraper/grpc "
            "--grpc_python_out=./src/shopee_scraper/grpc "
            "./protos/shopee.proto"
        )
        raise ImportError(
            "gRPC proto files not compiled. See logs for instructions."
        ) from e

    from shopee_scraper.grpc.servicer import ShopeeScraperServicer

    # Create server
    server = grpc.aio.server(
        futures.ThreadPoolExecutor(max_workers=max_workers),
        options=[
            ("grpc.max_send_message_length", 50 * 1024 * 1024),  # 50MB
            ("grpc.max_receive_message_length", 50 * 1024 * 1024),  # 50MB
        ],
    )

    # Create servicer
    servicer = ShopeeScraperServicer()

    # Register servicer
    shopee_pb2_grpc.add_ShopeeScraperServiceServicer_to_server(
        servicer,
        server,
    )

    # Bind to port
    listen_addr = f"[::]:{port}"
    server.add_insecure_port(listen_addr)

    logger.info(f"Starting gRPC server on {listen_addr}")
    await server.start()

    # Setup graceful shutdown
    async def shutdown(sig: signal.Signals) -> None:
        logger.info(f"Received {sig.name}, shutting down...")
        await servicer.close()
        await server.stop(grace=5)

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig,
            lambda s=sig: asyncio.create_task(shutdown(s)),
        )

    logger.info("gRPC server started. Press Ctrl+C to stop.")
    await server.wait_for_termination()


def run_server(port: int = DEFAULT_PORT) -> None:
    """Run server (sync wrapper for CLI)."""
    asyncio.run(serve(port=port))


if __name__ == "__main__":
    run_server()
