import inspect
from functools import wraps


def inject(func, dependencies):
    @wraps(func)
    async def wrapper(request):
        kwargs = {}
        cleanup = []

        try:
            for name, dep in dependencies.items():
                if inspect.signature(dep).parameters:
                    value = dep(request)
                else:
                    value = dep()

                if inspect.isawaitable(value):
                    value = await value

                # support generator/context-like dependencies
                if hasattr(value, "__enter__") and hasattr(value, "__exit__"):
                    entered = value.__enter__()
                    cleanup.append(value)
                    kwargs[name] = entered
                else:
                    kwargs[name] = value

            return await func(request, **kwargs)
        finally:
            for resource in reversed(cleanup):
                resource.__exit__(None, None, None)

    return wrapper