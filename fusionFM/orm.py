_db = {}


class Model:
    table = None

    def __init_subclass__(cls):
        if not getattr(cls, "table", None):
            cls.table = cls.__name__.lower() + "s"

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

    def save(self):
        table = _db.setdefault(self.table, [])

        if not hasattr(self, "id"):
            self.id = len(table) + 1

        table.append(self.to_dict())
        return self

    @classmethod
    def all(cls):
        return _db.get(cls.table, [])

    @classmethod
    def filter(cls, **kwargs):
        results = []
        for row in _db.get(cls.table, []):
            if all(row.get(k) == v for k, v in kwargs.items()):
                results.append(row)
        return results

    @classmethod
    def get(cls, **kwargs):
        for row in _db.get(cls.table, []):
            if all(row.get(k) == v for k, v in kwargs.items()):
                return row
        return None

    @classmethod
    def delete(cls, **kwargs):
        table = _db.get(cls.table, [])
        _db[cls.table] = [
            row for row in table
            if not all(row.get(k) == v for k, v in kwargs.items())
        ]