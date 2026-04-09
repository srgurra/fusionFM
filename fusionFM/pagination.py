def _query_int(request, key, default):
    value = request.query.get(key, [str(default)])
    if isinstance(value, list):
        value = value[0]
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(parsed, 1)


def get_pagination_params(request, default_page=1, default_per_page=20, max_per_page=100):
    page = _query_int(request, "page", default_page)
    per_page = min(_query_int(request, "per_page", default_per_page), max_per_page)
    return {"page": page, "per_page": per_page}


def paginate(items, page=1, per_page=20):
    total = len(items)
    start = (page - 1) * per_page
    end = start + per_page
    return {
        "items": items[start:end],
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": (total + per_page - 1) // per_page if per_page else 0,
    }
