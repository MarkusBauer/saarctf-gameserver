from dataclasses import dataclass
from typing import Iterable

from sqlalchemy.orm import Query


@dataclass
class Pagination:
    page: int
    pages: int
    items: list

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def prev_num(self) -> int | None:
        return self.page - 1 if self.page > 1 else None

    @property
    def has_next(self) -> bool:
        return self.page < self.pages

    @property
    def next_num(self) -> int | None:
        return self.page + 1 if self.page < self.pages else None

    def iter_pages(self) -> Iterable[int]:
        return range(1, self.pages + 1)


def paginate_query(query: Query, page: int, per_page: int) -> Pagination:
    offset = (page - 1) * per_page
    items = query[offset:offset + per_page]
    count = query.count()
    return Pagination(
        page=page,
        pages=(count + per_page - 1) // per_page,
        items=items
    )
