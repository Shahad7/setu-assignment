# stack/tools/lib/utils:
 - fastAPI
 - SQLAlchemy
 - Alembic
 - Pydant
 - Pytest
 - Postgres
 - Docker

 
# plan: 
- set up project structure, dockerfile, docker compose, alembic, requirements.txt etc
- set up a dummy endpoint to read the data from db and verify docker setup is working
- move onto set up basic functional endpoints
- add scripts to seed data
- implement tests
- improve endpoint performance
- consider performance testing
- consider seeding data in docker compose
- live deployment

# progress:

## events

An event for reference (same format as the example mentioned in the assignment)

 `{
    "event_id": "b768e3a7-9eb3-4603-b21c-a54cc95661bc",
    "event_type": "payment_initiated",
    "transaction_id": "2f86e94c-239c-4302-9874-75f28e3474ee",
    "merchant_id": "merchant_2",
    "merchant_name": "FreshBasket",
    "amount": 15248.29,
    "currency": "INR",
    "timestamp": "2026-01-08T12:11:58.085567+00:00"
  }`

All types:
  > payment_initiated
  > payment_failed
  > payment_processed
  > settled

## Data model

main tables required:
 > transaction 
 > event (don't store duplicate events, but store events with invalid state transitions)
 > merchant (only few fields needed for now)

## Assumptions
 
 - Merchant entity is owned by its own separate backend service
 - API for creation for merchants are out of scope for this assignment
 - add a seeding script to add few merchants as needed (merchant_[1-5])









