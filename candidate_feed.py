"""Incremental candidate reads for durable/background NameMachine sessions."""

from __future__ import annotations

from sqlalchemy import select

from session_store import STORE, SessionStore, candidates


MAX_FEED_PAGE = 200


class CandidateFeedStore:
    def __init__(self, session_store=None):
        self.session_store = session_store or STORE

    @property
    def configured(self):
        return self.session_store.configured

    def since(self, session_id, token, after_seq=0, limit=100):
        engine = self.session_store._ensure_engine()
        try:
            cursor = max(0, int(after_seq or 0))
        except (TypeError, ValueError):
            cursor = 0
        try:
            page_size = max(1, min(MAX_FEED_PAGE, int(limit or 100)))
        except (TypeError, ValueError):
            page_size = 100

        with engine.connect() as conn:
            if not SessionStore._authorized(conn, session_id, token):
                return None
            rows = conn.execute(
                select(candidates.c.row, candidates.c.received_seq)
                .where(
                    (candidates.c.session_id == session_id)
                    & (candidates.c.received_seq > cursor)
                )
                .order_by(candidates.c.received_seq.asc(), candidates.c.updated_at.asc())
                .limit(page_size + 1)
            ).mappings().all()

        has_more = len(rows) > page_size
        page = rows[:page_size]
        payload_rows = [dict(item["row"] or {}) for item in page]
        next_cursor = cursor
        for item in page:
            next_cursor = max(next_cursor, int(item["received_seq"] or 0))
        return {
            "candidates": payload_rows,
            "after_seq": cursor,
            "next_after_seq": next_cursor,
            "has_more": has_more,
            "limit": page_size,
        }


CANDIDATE_FEED = CandidateFeedStore()


__all__ = ["CANDIDATE_FEED", "CandidateFeedStore", "MAX_FEED_PAGE"]
