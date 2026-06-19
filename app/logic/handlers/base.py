import abc


class BaseHandler(abc.ABC):
    @abc.abstractmethod
    async def execute(self, *_, **__): ...
