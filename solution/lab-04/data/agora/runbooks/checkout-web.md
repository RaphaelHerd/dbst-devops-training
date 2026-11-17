# checkout-web: Seats, Vouchers and Error Pages

> service: checkout-web · owner: team-checkout · updated: 2026-09-20 · status: current

## Seat selection
- The seat map does not load, or the selected seat is not saved.
- Purge the CDN cache for the seat map bundle (INC-3874).

## Vouchers
- Voucher codes are rejected: check the campaign configuration and its end date (INC-3937).

## Error pages
- Customers see an error page during checkout: check the error rate of checkout-web and of the services it calls
  (payment-api, booking-search).
