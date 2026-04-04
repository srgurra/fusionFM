import inspect
from functools import wraps


def inject(func, dependencies):
    @wraps(func)
    async def wrapper(request):
        kwargs = {}

        for name, dep in dependencies.items():
            if inspect.signature(dep).parameters:
                value = dep(request)
            else:
                value = dep()

            if inspect.isawaitable(value):
                value = await value

            kwargs[name] = value

        return await func(request, **kwargs)

    return wrapper