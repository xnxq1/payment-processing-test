import asyncio

import click
import uvicorn


@click.group()
def cli() -> None:
    pass


@cli.command("start-api", short_help="Запуск FastAPI приложения")
@click.option("--host", default="0.0.0.0", show_default=True)
@click.option("--port", default=8000, show_default=True, type=int)
def start_api(host: str, port: int) -> None:
    from app.di import container
    from app.main import AppBuilder

    async def run() -> None:
        async with container:
            app_builder = await container.get(AppBuilder)
            config = uvicorn.Config(
                app_builder.create_app(), host=host, port=port, reload=False, access_log=False
            )
            server = uvicorn.Server(config)
            await server.serve()

    asyncio.run(run())


@cli.command("start-consumer", short_help="Запуск FastStream RabbitMQ consumer")
def start_consumer() -> None:
    from app.consumers.app import ConsumerApp
    from app.di import container

    async def run() -> None:
        async with container:
            consumer_app = await container.get(ConsumerApp)
            app = consumer_app.create_app()
            await app.run()

    asyncio.run(run())


@cli.command("start-outbox-publisher", short_help="Запуск outbox publisher (RabbitMQ)")
def start_outbox_publisher() -> None:
    from app.di import container
    from app.workers.outbox import OutboxPublisher, install_signal_handlers

    async def run() -> None:
        async with container:
            publisher = await container.get(OutboxPublisher)
            install_signal_handlers(publisher)
            await publisher.run()

    asyncio.run(run())


if __name__ == "__main__":
    cli()
