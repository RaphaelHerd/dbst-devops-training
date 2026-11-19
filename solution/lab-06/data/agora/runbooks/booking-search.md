# booking-search: Search Problems

> service: booking-search · owner: team-search · updated: 2026-08-30 · status: current

## Slow search results
- Search results take more than 3 s to appear.
- Check the cache hit rate in Grafana. After a price import the cache is often cold.
- Warm up the cache with the job "search-cache-warmup".

## Wrong or missing results
- Check the time of the last price and timetable import.
- Clear the search cache after a failed import (INC-3908).
